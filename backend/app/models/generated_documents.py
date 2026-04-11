"""Generated document tracking — persists metadata for documents created via doc-gen."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.base import QueryModel


class GeneratedDocument(QueryModel, table=True):
    """Tracks documents produced by the doc-gen endpoints."""

    __tablename__ = "generated_documents"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID | None = Field(default=None, foreign_key="organizations.id", index=True)
    filename: str = Field(index=True)
    relative_path: str = Field(description="Path relative to gateway workspace root")
    file_size: int = Field(default=0)
    mime_type: str = Field(default="application/pdf")
    doc_type: str = Field(
        default="other",
        index=True,
        description="proposal, report, security-assessment, invoice, other",
    )
    mode: str = Field(default="simple", description="simple, complex, complex_rehydrated")
    engine: str = Field(
        default="reportlab", description="reportlab, adobe_pdf_services, html_fallback"
    )
    title: str = Field(default="")
    onedrive_url: str | None = Field(default=None)
    onedrive_edit_url: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, index=True)
