"""Statement-line classifier with DB-backed vendor rules + seed fallbacks.

Deterministic (regex match) — not LLM-backed. Identical rules to
.claude/bookkeeping-draft/reconcile_month.py, extended with DB lookup for
learned rules that Henz confirms over time.

Classification order (first match wins):
    1. Transfers (internal money movement — never an expense)
    2. Incoming money (credit column / negative AMEX amount) → income_pending
    3. DB-stored PersonalVendorRule rows for this org
    4. Seed business rules (SaaS, vehicle, etc.)
    5. TD-source default → personal (Henz's rule: TD is out-of-pocket)
    6. Seed ambiguous-explicit patterns (UPS*, PayPal, unknown vendors)
    7. Seed personal hints (restaurants, groceries, streaming, etc.)
    8. Fallback → ambiguous (needs Henz's review)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.personal_bookkeeping import PersonalVendorRule


@dataclass(frozen=True)
class Classification:
    """Result of classifying a statement line."""

    bucket: str
    t2125_line: str | None
    category: str | None
    needs_receipt: bool
    note: str


# Seed rules — lifted verbatim from reconcile_month.py. Tuple of
# (pattern, bucket, t2125_line, category, needs_receipt, note).
SEED_BUSINESS_RULES: tuple[tuple[str, str, str | None, str, bool, str], ...] = (
    (r"GALLO LLP", "business", "8860", "Legal/Acct", True, "Accountant invoice"),
    (r"VERCEL", "business", "8871", "Mgmt/Admin", True, "Hosting"),
    (r"SQSP\*", "business", "8871", "Mgmt/Admin", True, "Squarespace"),
    (r"DROPBOX", "business", "8810", "Office", True, "Cloud storage"),
    (r"GOOGLE.*ONE|GOOGLE \*ONE", "business", "8810", "Office", True, "Google One"),
    (r"GOOGLE.*CLOUD|GOOGLE\*CLOUD", "business", "8871", "Mgmt/Admin", True, "Google Cloud"),
    (r"GOOGLE.*WORKSPACE", "business", "8810", "Office", True, "Google Workspace"),
    (r"INTUIT|QUICKBOOKS", "business", "8871", "Mgmt/Admin", True, "Accounting software"),
    (r"MSBILL\.INFO", "business", "8810", "Office", True, "Microsoft 365"),
    (r"ZOHO", "business", "8810", "Office", True, "Zoho"),
    (r"GITKRAKEN", "business", "8810", "Office", True, "GitKraken"),
    (r"MIDJOURNEY", "business", "8521", "Advertising", True, "Midjourney"),
    (r"HIGGSFIELD", "business", "8521", "Advertising", True, "Higgsfield"),
    (r"KLING", "business", "8521", "Advertising", True, "KlingAI"),
    (r"CAPCUT", "business", "8521", "Advertising", True, "CapCut"),
    (r"INVIDEO", "business", "8521", "Advertising", True, "InVideo"),
    (r"GODADDY", "business", "8760", "Fees/Licenses", True, "Domain"),
    (r"ASME", "business", "8760", "Fees/Licenses", True, "Professional dues"),
    (r"PROTON", "business", "8810", "Office", True, "Encrypted email"),
    (r"OPENROUTER", "business", "8871", "Mgmt/Admin", True, "LLM infrastructure"),
    (r"MEMORY EXPRESS", "business", "8871", "Mgmt/Admin", True, "IT hardware"),
    (r"PETRO-CANADA|SHELL|ESSO|HUSKY|CO-OP GAS", "vehicle", "9224", "Fuel", False, "Vehicle % — track km"),
    (r"PRIMMUM INSURANCE", "vehicle", None, "Auto Insurance", True, "Vehicle % — insurance"),
    (r"DOWNTOWN AUTO", "vehicle", None, "Maintenance", True, "Vehicle % — mechanic"),
)

SEED_PERSONAL_HINTS: tuple[str, ...] = (
    r"UBER EATS", r"MCDONALD", r"A&W", r"PIZZA", r"PHO ", r"SQ \*", r"SOBEYS", r"LOBLAWS",
    r"REAL CDN SUPERS", r"EL-SAFADI", r"LUCKY SUPERMARK", r"T&T SUPERMARKET", r"H & W PRODUCE",
    r"ITALIAN CENTRE", r"COBS", r"DRIP N DIP", r"SUNBAKE", r"DQ GRILL", r"BOSTON PIZZA",
    r"YMCA", r"JUNO", r"VALUE BUDS", r"CANNABIS", r"SPOTIFY", r"YOUTUBE", r"YOGALIFE",
    r"SHOPPERS DRUG", r"SDM ", r"AESOP", r"WHITEPOUCHES", r"UBER ONE",
    r"7-ELEVEN", r"BAEKJEONG", r"KITCHEN KING", r"BULGOGI", r"NUMO", r"TST-", r"ROYAL PIZZA",
    r"CO DO HUE", r"BERNARDO", r"SKILOUISE", r"BROOK", r"SWISS DONAIR", r"KAHVE", r"ROCKIN ROBYNS",
    r"MR\. & MRS\.", r"TOUCH OF THAI", r"XING WANG", r"COFFEE BURE",
    r"AMAZON", r"AMZN",
)

SEED_TRANSFER_HINTS: tuple[str, ...] = (
    r"AMEX CARDS", r"RBC MC", r"TD ATM W/D", r"TFR-TO", r"TO:\d",
    r"WITHDRAWAL FEES", r"MONTHLY ACCOUNT FEE", r"PAYMENT RECEIVED",
    r"MEMBERSHIP FEE INSTALLMENT", r"INTEREST$",
)

SEED_INCOME_HINTS: tuple[str, ...] = (r"E-TRANSFER \*\*\*", r"TD ATM DEP")

SEED_AMBIGUOUS_EXPLICIT: tuple[str, ...] = (
    r"UPS\*", r"MSSM", r"PAYPAL", r"SANDMAN",
)


async def classify(
    description: str,
    incoming: bool,
    source: str,
    organization_id: UUID,
    session: AsyncSession,
) -> Classification:
    """Classify one statement line.

    Args:
        description: raw merchant/description text from the statement
        incoming: True if this is a credit/incoming amount
        source: "TD" or "AMEX"
        organization_id: Personal org UUID (used to load learned rules)
        session: async DB session for vendor-rule lookup

    Returns:
        Classification with bucket + metadata. Never raises on unknown
        vendors — falls back to "ambiguous".
    """
    desc_upper = description.upper()

    # 1. Transfers — always short-circuit, never expense
    for pat in SEED_TRANSFER_HINTS:
        if re.search(pat, desc_upper):
            return Classification(
                bucket="transfer",
                t2125_line=None,
                category=None,
                needs_receipt=False,
                note="Internal transfer",
            )

    # 2. Incoming money — always surface for classification
    if incoming:
        for pat in SEED_INCOME_HINTS:
            if re.search(pat, desc_upper):
                return Classification(
                    bucket="income_pending",
                    t2125_line=None,
                    category=None,
                    needs_receipt=True,
                    note="NEEDS CLASSIFICATION — client payment or gift?",
                )
        return Classification(
            bucket="income_pending",
            t2125_line=None,
            category=None,
            needs_receipt=True,
            note="Incoming — classify",
        )

    # 3. DB-stored learned rules for this org
    db_rules = (
        await session.execute(
            select(PersonalVendorRule).where(
                PersonalVendorRule.organization_id == organization_id,
                PersonalVendorRule.active == True,  # noqa: E712
            )
        )
    ).scalars().all()

    for rule in db_rules:
        if rule.applies_to_source and rule.applies_to_source != source:
            continue
        try:
            if re.search(rule.pattern, desc_upper, re.IGNORECASE):
                return Classification(
                    bucket=rule.bucket,
                    t2125_line=rule.t2125_line,
                    category=rule.category,
                    needs_receipt=rule.needs_receipt,
                    note=rule.note or "",
                )
        except re.error:
            # Bad user regex — skip, don't crash the whole classification
            continue

    # 4. Seed business rules
    for pat, bucket, line, category, needs_receipt, note in SEED_BUSINESS_RULES:
        if re.search(pat, desc_upper, re.IGNORECASE):
            return Classification(
                bucket=bucket,
                t2125_line=line,
                category=category,
                needs_receipt=needs_receipt,
                note=note,
            )

    # 5. TD source default is personal (Henz's rule)
    if source == "TD":
        return Classification(
            bucket="personal",
            t2125_line=None,
            category=None,
            needs_receipt=False,
            note="",
        )

    # 6. AMEX-only ambiguous-explicit patterns
    for pat in SEED_AMBIGUOUS_EXPLICIT:
        if re.search(pat, desc_upper):
            return Classification(
                bucket="ambiguous",
                t2125_line=None,
                category=None,
                needs_receipt=True,
                note="NEEDS YOU — could be business",
            )

    # 7. AMEX personal hints
    for pat in SEED_PERSONAL_HINTS:
        if re.search(pat, desc_upper, re.IGNORECASE):
            return Classification(
                bucket="personal",
                t2125_line=None,
                category=None,
                needs_receipt=False,
                note="",
            )

    # 8. Fallback — needs Henz's review
    return Classification(
        bucket="ambiguous",
        t2125_line=None,
        category=None,
        needs_receipt=True,
        note="NEEDS YOU — unknown vendor",
    )
