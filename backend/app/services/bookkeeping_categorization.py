"""Expense categorization — regex-based rules for vendor and item matching."""

from __future__ import annotations

import re

# Vendor-based category rules (case-insensitive partial match)
_VENDOR_RULES: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"home\s*depot|lowes|rona|totem|building\s*supplies|lumber", re.IGNORECASE),
        "materials",
    ),
    (
        re.compile(
            r"shell|esso|petro|husky|co-op.*gas|pioneer|7-?eleven.*gas|fas\s*gas", re.IGNORECASE
        ),
        "fuel",
    ),
    (re.compile(r"canadian\s*tire|princess\s*auto|tool", re.IGNORECASE), "tools"),
    (re.compile(r"marks|work.*warehouse|safety|ppe|coverall", re.IGNORECASE), "ppe"),
    (
        re.compile(
            r"tim\s*horton|subway|mcdonald|a&w|wendy|pizza|restaurant|coffee", re.IGNORECASE
        ),
        "food",
    ),
    (re.compile(r"napa|lordco|bumper|autozone|part.*source", re.IGNORECASE), "vehicle"),
    (re.compile(r"staples|office", re.IGNORECASE), "office"),
    (re.compile(r"rent.*equip|sunbelt|hertz.*equip|united\s*rental", re.IGNORECASE), "equipment"),
    (re.compile(r"parking|impark|epark", re.IGNORECASE), "parking"),
]

# Item description-based rules (fallback when vendor doesn't match)
_ITEM_RULES: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"lumber|plywood|drywall|concrete|cement|rebar|insulation|shingle|roofing|siding|nail|screw|bolt",
            re.IGNORECASE,
        ),
        "materials",
    ),
    (re.compile(r"gasoline|diesel|fuel|propane", re.IGNORECASE), "fuel"),
    (re.compile(r"drill|saw|hammer|wrench|tape.*measure|level|bit|blade", re.IGNORECASE), "tools"),
    (
        re.compile(r"glove|hard\s*hat|helmet|vest|boot|gogg|ear.*plug|respirator", re.IGNORECASE),
        "ppe",
    ),
]


def categorize_expense(vendor: str | None, items: list[dict] | None = None) -> str:
    """Categorize an expense based on vendor name and line items.

    Args:
        vendor: Vendor/merchant name from receipt.
        items: List of receipt line items, each with a "description" key.

    Returns:
        Category string (materials, fuel, tools, ppe, food, vehicle, office,
        equipment, parking, or "other" if no match).
    """
    if vendor:
        for pattern, category in _VENDOR_RULES:
            if pattern.search(vendor):
                return category

    for item in items or []:
        desc = item.get("description", "")
        if not desc:
            continue
        for pattern, category in _ITEM_RULES:
            if pattern.search(desc):
                return category

    return "other"
