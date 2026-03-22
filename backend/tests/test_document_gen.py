# ruff: noqa: INP001
"""Tests for document generation service and API endpoints."""

from __future__ import annotations

from pathlib import Path
import pytest

from app.services.document_gen import generate_simple_pdf


# ---------------------------------------------------------------------------
# Simple PDF generation (reportlab)
# ---------------------------------------------------------------------------


class TestSimplePdf:
    """reportlab-based simple PDF generation."""

    def test_basic_text_document(self):
        """Generates valid PDF bytes with text sections."""
        result = generate_simple_pdf(
            title="Test Report",
            sections=[
                {"heading": "Introduction", "content": "This is a test document."},
                {"heading": "Details", "content": "More content here.\nSecond paragraph."},
            ],
        )
        assert isinstance(result, bytes)
        assert result[:5] == b"%PDF-"
        assert len(result) > 100

    def test_table_section(self):
        """Generates PDF with table data."""
        result = generate_simple_pdf(
            title="Data Export",
            sections=[
                {
                    "heading": "Watchlist",
                    "content": [
                        {"Symbol": "AAPL", "Price": "$195.20", "Change": "+2.1%"},
                        {"Symbol": "MSFT", "Price": "$430.50", "Change": "-0.3%"},
                    ],
                },
            ],
        )
        assert result[:5] == b"%PDF-"

    def test_with_company_branding(self):
        """Includes company branding in output."""
        result = generate_simple_pdf(
            title="Branded Report",
            sections=[{"heading": "Test", "content": "Content"}],
            company={"name": "Vantage Solutions", "email": "info@vantagesolutions.ca"},
        )
        assert result[:5] == b"%PDF-"

    def test_a4_page_size(self):
        """Supports A4 page size."""
        result = generate_simple_pdf(
            title="A4 Document",
            sections=[{"heading": "Test", "content": "Content"}],
            page_size="a4",
        )
        assert result[:5] == b"%PDF-"

    def test_empty_sections(self):
        """Handles empty sections list."""
        result = generate_simple_pdf(title="Empty Doc", sections=[])
        assert result[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


class TestTemplateRendering:
    """Jinja2 HTML template rendering."""

    def test_proposal_template_renders(self):
        from app.services.document_gen import _render_html_template

        html = _render_html_template("proposal", {
            "title": "Test Proposal",
            "subtitle": "Phase 1",
            "company_name": "Test Co",
            "sections": [
                {"heading": "Overview", "content": "<p>Test content</p>"},
            ],
        })
        assert "Test Proposal" in html
        assert "Phase 1" in html
        assert "Test Co" in html
        assert "<p>Test content</p>" in html

    def test_report_template_renders(self):
        from app.services.document_gen import _render_html_template

        html = _render_html_template("report", {
            "title": "Q1 Report",
            "date": "March 2026",
            "kpis": [
                {"value": "+12%", "label": "Return", "change": "+2%", "direction": "up"},
            ],
            "sections": [],
        })
        assert "Q1 Report" in html
        assert "+12%" in html
        assert "March 2026" in html

    def test_missing_template_raises(self):
        from app.services.document_gen import _render_html_template
        from jinja2 import TemplateNotFound

        with pytest.raises(TemplateNotFound):
            _render_html_template("nonexistent_template", {})


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestSaveToWorkspace:
    """Test workspace file saving logic."""

    def _save_to_workspace(self, workspace: Path, content: bytes, filename: str, extension: str) -> str:
        """Replicate the save logic without importing the full API module."""
        from uuid import uuid4

        docs_dir = workspace / "documents"
        docs_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(filename).stem
        unique_name = f"{stem}-{uuid4().hex[:8]}{extension}"
        output_path = docs_dir / unique_name
        output_path.write_bytes(content)
        return f"documents/{unique_name}"

    def test_saves_pdf_to_documents_dir(self, tmp_path: Path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        pdf_bytes = b"%PDF-1.4 test content"
        relative_path = self._save_to_workspace(workspace, pdf_bytes, "test.pdf", ".pdf")

        assert relative_path.startswith("documents/")
        assert relative_path.endswith(".pdf")

        saved_file = workspace / relative_path
        assert saved_file.exists()
        assert saved_file.read_bytes() == pdf_bytes

    def test_creates_documents_dir(self, tmp_path: Path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        self._save_to_workspace(workspace, b"test", "file.html", ".html")
        assert (workspace / "documents").is_dir()

    def test_unique_filenames(self, tmp_path: Path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        path1 = self._save_to_workspace(workspace, b"a", "report.pdf", ".pdf")
        path2 = self._save_to_workspace(workspace, b"b", "report.pdf", ".pdf")
        assert path1 != path2


class TestComplexFallback:
    """Test that complex mode falls back to HTML without Adobe."""

    @pytest.mark.asyncio()
    async def test_html_fallback_returns_bytes(self):
        from app.services.document_gen import generate_complex_pdf_fallback

        result = await generate_complex_pdf_fallback("<html><body>Test</body></html>")
        assert result == b"<html><body>Test</body></html>"
