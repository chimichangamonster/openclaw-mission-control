"""Legal document endpoints — terms of service, privacy policy, data trust page."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.logging import get_logger
from app.models.users import CURRENT_TERMS_VERSION

logger = get_logger(__name__)
router = APIRouter(prefix="/legal", tags=["legal"])

_TEMPLATES = Path(__file__).resolve().parents[2] / "templates" / "legal"


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


@router.get("/compliance-checklist", summary="Pre-Onboarding Compliance Checklist", response_class=HTMLResponse)
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


@router.get("/version", summary="Current terms version")
async def get_terms_version() -> dict[str, str]:
    """Return the current terms version that users must accept."""
    return {"version": CURRENT_TERMS_VERSION}
