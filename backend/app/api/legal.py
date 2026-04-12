"""Legal document endpoints — terms of service, privacy policy, data trust page."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

from app.core.logging import get_logger
from app.models.users import CURRENT_TERMS_VERSION

logger = get_logger(__name__)
router = APIRouter(prefix="/legal", tags=["legal"])

_TEMPLATES = Path(__file__).resolve().parents[2] / "templates" / "legal"
_DOC_TEMPLATES = Path(__file__).resolve().parents[2] / "templates" / "documents"


@router.get("/terms", summary="Terms of Service", response_class=HTMLResponse)
async def get_terms() -> HTMLResponse:
    """Serve the Terms of Service page. No auth required."""
    html = (_TEMPLATES / "terms-of-service.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/privacy", summary="Privacy Policy", response_class=HTMLResponse)
async def get_privacy() -> HTMLResponse:
    """Serve the Privacy Policy page. No auth required."""
    html = (_TEMPLATES / "privacy-policy.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get(
    "/compliance-checklist",
    summary="Pre-Onboarding Compliance Checklist",
    response_class=HTMLResponse,
)
async def get_compliance_checklist() -> HTMLResponse:
    """Serve a standalone compliance checklist for prospective clients. No auth required."""
    # Extract the checklist section from the ToS
    tos = (_TEMPLATES / "terms-of-service.html").read_text(encoding="utf-8")
    # Serve the full ToS — the checklist is in section 5.4
    # Prospective clients should see the full context
    return HTMLResponse(content=tos)


@router.get("/dpa", summary="Data Processing Agreement", response_class=HTMLResponse)
async def get_dpa() -> HTMLResponse:
    """Serve the Data Processing Agreement template. No auth required."""
    html = (_TEMPLATES / "data-processing-agreement.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get(
    "/onboarding-checklist",
    summary="Client Onboarding Preparation Checklist",
    response_class=HTMLResponse,
)
async def get_onboarding_checklist() -> HTMLResponse:
    """Serve the client onboarding preparation checklist. No auth required.

    This is sent to prospective clients before their onboarding session
    so they can prepare the necessary information in advance.
    """
    html = (_DOC_TEMPLATES / "onboarding-checklist.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/onboarding-checklist.pdf", summary="Client Onboarding Checklist (PDF)")
async def get_onboarding_checklist_pdf(industry: str | None = None) -> Response:
    """Generate a branded onboarding checklist PDF. No auth required.

    Optional query param `industry` (e.g. `construction`, `waste_management`)
    adds industry-specific preparation items from the template system.
    Without it, generates a generic checklist applicable to all verticals.
    """
    from app.services.document_gen import generate_simple_pdf
    from app.services.industry_templates import get_template

    template = get_template(industry) if industry else None
    title = "Client Onboarding Preparation Checklist"
    if template:
        title = f"{template.name} — Onboarding Preparation Checklist"

    # --- Generic sections (all verticals) ---
    sections: list[dict[str, Any]] = [
        {
            "heading": "1. Team & Access",
            "content": (
                "- Names and email addresses of everyone who needs access\n"
                "- Role for each person: Owner, Admin, Operator, Member, or Viewer\n"
                "- Who should be the primary org owner (manages settings and billing)"
            ),
        },
        {
            "heading": "2. Roles & Permissions",
            "content": [
                {
                    "Role": "Owner",
                    "Access": "Full control — settings, billing, API keys",
                    "Typical": "Business owner, CEO",
                },
                {
                    "Role": "Admin",
                    "Access": "Settings, members, integrations",
                    "Typical": "Office manager, ops lead",
                },
                {
                    "Role": "Operator",
                    "Access": "Workflows, invoices, documents",
                    "Typical": "Project manager, dispatcher",
                },
                {
                    "Role": "Member",
                    "Access": "Chat, uploads, dashboards",
                    "Typical": "Field crew, team members",
                },
                {
                    "Role": "Viewer",
                    "Access": "Read-only dashboards and reports",
                    "Typical": "Accountant, advisor",
                },
            ],
        },
        {
            "heading": "3. Sample Documents",
            "content": (
                "- 1 week's worth of typical documents your team processes\n"
                "- Invoices, reports, timesheets, receipts — whatever is part of your daily workflow\n"
                "- These samples configure the AI document extraction for your specific formats\n"
                "- Digital copies preferred (PDF, photos, scans)"
            ),
        },
        {
            "heading": "4. Current Tools & Processes",
            "content": (
                "- How do you currently track work? (Spreadsheets, paper, software — which?)\n"
                "- How do you handle invoicing? (QuickBooks, Xero, manual, other)\n"
                "- How does your team communicate? (WhatsApp, Slack, Teams, email)\n"
                "- Do you use Microsoft 365 or Google Workspace?"
            ),
        },
        {
            "heading": "5. Integrations (optional)",
            "content": (
                "- Email: Outlook or Zoho account credentials for email triage\n"
                "- Calendar: Google Calendar or Outlook Calendar for scheduling\n"
                "- Messaging: Discord, Slack, or Microsoft Teams for agent channels\n"
                "- Leave blank if not needed — these can be added later"
            ),
        },
    ]

    # --- Industry-specific sections ---
    if template:
        step_num = len(sections) + 1

        # Add config categories as preparation items
        if template.default_config:
            config_items = []
            for category, items in template.default_config.items():
                label = category.replace("_", " ").title()
                examples = ", ".join(item.label for item in items[:4])
                if len(items) > 4:
                    examples += f" (+{len(items) - 4} more)"
                config_items.append(f"- {label}: review defaults ({examples})")

            sections.append(
                {
                    "heading": f"{step_num}. {template.name} — Review Default Configuration",
                    "content": (
                        "We'll pre-load industry defaults. Review and adjust to match your business:\n\n"
                        + "\n".join(config_items)
                    ),
                }
            )
            step_num += 1

        # Add onboarding steps as a checklist
        if template.onboarding_steps:
            step_lines = [
                f"- {step.label}: {step.description}" for step in template.onboarding_steps
            ]
            sections.append(
                {
                    "heading": f"{step_num}. {template.name} — Setup Steps",
                    "content": (
                        "These will be completed during or after onboarding:\n\n"
                        + "\n".join(step_lines)
                    ),
                }
            )
            step_num += 1

    # --- AI access (always last before onboarding session) ---
    ai_step = len(sections) + 1
    sections.append(
        {
            "heading": f"{ai_step}. AI Access Setup",
            "content": (
                "The platform uses AI models to process documents, run agents, and generate reports.\n\n"
                "- Create an OpenRouter account at openrouter.ai and add a $5-20 deposit\n"
                "- Typical monthly cost: $5-50 depending on usage\n"
                "- Personal AI subscriptions (Claude Max, ChatGPT Pro) do NOT cover platform use\n"
                "- For compliance requirements: direct provider API key with BAA, or self-hosted model"
            ),
        }
    )

    session_step = len(sections) + 1
    sections.append(
        {
            "heading": f"{session_step}. What Happens at the Onboarding Session",
            "content": (
                "1. Review your sample documents and configure AI extraction templates\n"
                "2. Set up your org configuration and industry-specific defaults\n"
                "3. Configure integrations (email, calendar, messaging) if applicable\n"
                "4. Set up user accounts with appropriate access levels\n"
                "5. Run a test: upload a document and verify the AI processes it correctly\n"
                "6. Walk through the dashboard and train your team\n\n"
                "Typical onboarding: 1-2 sessions, 2-4 hours total."
            ),
        }
    )

    pdf_bytes = generate_simple_pdf(
        title=title,
        sections=sections,
        company={"name": "VantageClaw", "email": "support@vantageclaw.ai"},
    )

    filename = "vantageclaw-onboarding-checklist"
    if template:
        filename += f"-{template.id}"
    filename += ".pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/version", summary="Current terms version")
async def get_terms_version() -> dict[str, str]:
    """Return the current terms version that users must accept."""
    return {"version": CURRENT_TERMS_VERSION}
