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


# ---------------------------------------------------------------------------
# RedactionVault tests
# ---------------------------------------------------------------------------


class TestRedactionVault:
    """Reversible redaction for security assessment reports."""

    def test_redacts_ipv4_addresses(self):
        from app.core.redact import RedactionVault

        vault = RedactionVault()
        result = vault.redact("Found open port on 192.168.1.50")
        assert "192.168.1.50" not in result
        assert "[IP_ADDRESS_" in result
        assert vault.entry_count >= 1

    def test_rehydrates_placeholders(self):
        from app.core.redact import RedactionVault

        vault = RedactionVault()
        redacted = vault.redact("Host 10.0.0.1 has FTP on port 21")
        assert "10.0.0.1" not in redacted

        # Simulate LLM generating text with placeholders
        llm_output = f"The server at {redacted.split('Host ')[1].split(' has')[0]} is vulnerable."
        rehydrated = vault.rehydrate(llm_output)
        assert "10.0.0.1" in rehydrated

    def test_deduplicates_same_value(self):
        from app.core.redact import RedactionVault

        vault = RedactionVault()
        result = vault.redact("Server 10.0.0.5 responds. Confirmed 10.0.0.5 is alive.")
        # Same IP should get the same tag
        tags = [e["tag"] for e in vault.entries if e["original"] == "10.0.0.5"]
        assert len(tags) == 1  # one entry, reused

    def test_redacts_mac_addresses(self):
        from app.core.redact import RedactionVault

        vault = RedactionVault()
        result = vault.redact("Device MAC: AA:BB:CC:DD:EE:FF")
        assert "AA:BB:CC:DD:EE:FF" not in result
        categories = {e["label"] for e in vault.entries}
        assert "MAC address" in categories

    def test_redacts_hostnames(self):
        from app.core.redact import RedactionVault

        vault = RedactionVault()
        result = vault.redact("DNS points to mail.example.corp.com")
        assert "mail.example.corp.com" not in result

    def test_redacts_internal_hosts(self):
        from app.core.redact import RedactionVault

        vault = RedactionVault()
        result = vault.redact("Found dc01.corp.local on the network")
        assert "dc01.corp.local" not in result

    def test_redacts_file_paths(self):
        from app.core.redact import RedactionVault

        vault = RedactionVault()
        result = vault.redact("Config at /etc/nginx/sites-enabled/default")
        assert "/etc/nginx/sites-enabled/default" not in result

    def test_redacts_windows_paths(self):
        from app.core.redact import RedactionVault

        vault = RedactionVault()
        result = vault.redact("Found file at C:\\Users\\admin\\Desktop\\passwords.txt")
        assert "C:\\Users\\admin\\Desktop\\passwords.txt" not in result

    def test_redacts_domain_users(self):
        from app.core.redact import RedactionVault

        vault = RedactionVault()
        result = vault.redact("Login as CONTOSO\\jsmith succeeded")
        assert "CONTOSO\\jsmith" not in result

    def test_vault_serialization_roundtrip(self):
        from app.core.redact import RedactionVault

        vault = RedactionVault()
        redacted = vault.redact("Host 172.16.0.100 is running SSH")

        # Serialize and reconstruct
        data = vault.to_dict()
        vault2 = RedactionVault.from_dict(data)

        rehydrated = vault2.rehydrate(redacted)
        assert "172.16.0.100" in rehydrated

    def test_entries_for_review(self):
        from app.core.redact import RedactionVault

        vault = RedactionVault()
        vault.redact("Server 10.0.0.1 with MAC AA:BB:CC:DD:EE:FF")

        entries = vault.entries
        assert len(entries) >= 2
        for entry in entries:
            assert "tag" in entry
            assert "original" in entry
            assert "label" in entry

    def test_recursive_redact(self):
        from app.api.document_gen import _redact_recursive
        from app.core.redact import RedactionVault

        vault = RedactionVault()
        data = {
            "findings": [
                {
                    "title": "Open SSH on 10.0.0.5",
                    "affected_nodes": [
                        {"address": "10.0.0.5", "hostname": "web01.corp.local"}
                    ],
                }
            ],
            "count": 1,
        }
        result = _redact_recursive(data, vault)
        # IPs and hostnames should be redacted in nested structures
        assert "10.0.0.5" not in str(result)
        assert "web01.corp.local" not in str(result)
        # Non-string values preserved
        assert result["count"] == 1

    def test_recursive_rehydrate(self):
        from app.api.document_gen import _redact_recursive, _rehydrate_recursive
        from app.core.redact import RedactionVault

        vault = RedactionVault()
        original = {
            "observation": "Port 22 open on 192.168.10.1",
            "nodes": [{"ip": "192.168.10.1"}],
        }
        redacted = _redact_recursive(original, vault)
        assert "192.168.10.1" not in str(redacted)

        rehydrated = _rehydrate_recursive(redacted, vault)
        assert "192.168.10.1" in str(rehydrated)

    def test_security_assessment_template_renders(self):
        from app.services.document_gen import _render_html_template

        html = _render_html_template("security-assessment", {
            "client_name": "Test Corp",
            "assessment_date": "March 15, 2026",
            "report_date": "March 20, 2026",
            "date": "March 20, 2026",
            "engagement_type_label": "External Network Penetration Test",
            "scope_summary": "external-facing infrastructure",
            "overall_severity": "Medium",
            "total_findings": 2,
            "counts": {"critical": 0, "high": 0, "medium": 2, "low": 0, "info": 0},
            "findings": [
                {
                    "id": "VS-2026-001",
                    "title": "Insecure FTP Service",
                    "severity": "medium",
                    "category": "Insecure Protocols",
                    "cvss_score": "5.3",
                    "cvss_vector": "AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:N/A:N",
                    "observation": "FTP service running without encryption.",
                    "security_impact": "Credentials exposed in cleartext.",
                    "affected_count": 1,
                    "affected_nodes": [{"address": "10.0.0.1", "port": "21/tcp"}],
                    "recommendation": "<p>Disable FTP or switch to SFTP.</p>",
                    "remediation_timeline": "Within 30 days",
                    "mitre_ids": ["T1046"],
                    "reproduction_steps": ["Connect via ftp 10.0.0.1"],
                    "evidence": [{"type": "text", "content": "220 ProFTPD Server ready"}],
                    "references": [{"url": "https://example.com", "title": "FTP RFC"}],
                },
            ],
        })
        assert "Test Corp" in html
        assert "VS-2026-001" in html
        assert "Insecure FTP Service" in html
        assert "CONFIDENTIAL" in html


class TestComplexFallback:
    """Test that complex mode falls back to HTML without Adobe."""

    @pytest.mark.asyncio()
    async def test_html_fallback_returns_bytes(self):
        from app.services.document_gen import generate_complex_pdf_fallback

        result = await generate_complex_pdf_fallback("<html><body>Test</body></html>")
        assert result == b"<html><body>Test</body></html>"
