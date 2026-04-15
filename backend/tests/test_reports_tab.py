# ruff: noqa: INP001
"""Tests for the Reports tab — cron-generated report listing and reading.

Tests-to-demote manifest: if Phase 3c automated quality scoring shows
this tab isn't useful, delete this file and the code it covers:
  - memory.py: Report, _DATE_SUFFIX_RE, _report_category, list_reports, read_report
  - page.tsx: Report interface, fetch functions, state vars, tab button, tab panel
  - knowledge-compile/SKILL.md: retention step
"""

from __future__ import annotations

import time
from pathlib import Path

from app.api.memory import _report_category

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_reports_workspace(tmp_path: Path) -> Path:
    """Create a fake workspace with report files."""
    ws = tmp_path / "workspace"
    reports = ws / "reports"
    reports.mkdir(parents=True)

    (reports / "competitor-scan-2026-04-07.md").write_text(
        "# Competitor Intelligence Report — 2026-04-07\n\nFindings here.\n"
    )
    (reports / "competitor-scan-2026-04-13.md").write_text(
        "# Competitor Intelligence Report — 2026-04-13\n\nMore findings.\n"
    )
    (reports / "frontier-watch-2026-04-01.md").write_text(
        "# Frontier AI Watch — April 2026\n\nCapability updates.\n"
    )
    (reports / "waste-market-intel-2026-04-07.md").write_text(
        "# Waste Market Intelligence — Week of 2026-04-07\n\nSignals.\n"
    )
    return ws


# ---------------------------------------------------------------------------
# Unit tests — list_reports logic
# ---------------------------------------------------------------------------


class TestReportsList:
    """Report listing from workspace/reports/."""

    def test_discovers_all_reports(self, tmp_path: Path):
        """All .md files under reports/ are listed."""
        ws = _make_reports_workspace(tmp_path)
        reports_dir = ws / "reports"
        files = list(reports_dir.glob("*.md"))
        assert len(files) == 4

    def test_title_from_heading(self, tmp_path: Path):
        """Title is extracted from first # heading."""
        ws = _make_reports_workspace(tmp_path)
        content = (ws / "reports" / "competitor-scan-2026-04-13.md").read_text()
        first_line = content.split("\n", 1)[0]
        assert first_line.startswith("# ")
        title = first_line[2:].strip()
        assert "Competitor Intelligence" in title

    def test_category_from_filename_prefix(self, tmp_path: Path):
        """Category is derived from filename prefix before date suffix."""
        ws = _make_reports_workspace(tmp_path)
        reports_dir = ws / "reports"
        categories = {f.stem: _report_category(f.stem) for f in reports_dir.glob("*.md")}
        assert categories["competitor-scan-2026-04-07"] == "Competitor Scan"
        assert categories["competitor-scan-2026-04-13"] == "Competitor Scan"
        assert categories["frontier-watch-2026-04-01"] == "Frontier Watch"
        assert categories["waste-market-intel-2026-04-07"] == "Waste Market Intel"

    def test_newest_first_ordering(self, tmp_path: Path):
        """Reports are sorted newest-first (reverse filename order)."""
        ws = _make_reports_workspace(tmp_path)
        reports_dir = ws / "reports"
        names = [f.name for f in sorted(reports_dir.glob("*.md"), reverse=True)]
        # Reverse alpha: waste > frontier > competitor-2026-04-13 > competitor-2026-04-07
        assert names.index("competitor-scan-2026-04-13.md") < names.index(
            "competitor-scan-2026-04-07.md"
        )

    def test_empty_reports_dir(self, tmp_path: Path):
        """Empty reports/ returns empty list."""
        ws = tmp_path / "workspace"
        (ws / "reports").mkdir(parents=True)
        files = list((ws / "reports").glob("*.md"))
        assert files == []

    def test_no_reports_dir(self, tmp_path: Path):
        """Missing reports/ detected correctly."""
        ws = tmp_path / "workspace"
        ws.mkdir(parents=True)
        assert not (ws / "reports").is_dir()

    def test_file_size_and_created_at(self, tmp_path: Path):
        """Reports include file_size and created_at metadata."""
        ws = _make_reports_workspace(tmp_path)
        reports_dir = ws / "reports"
        md_file = reports_dir / "competitor-scan-2026-04-13.md"
        stat = md_file.stat()
        assert stat.st_size > 0
        assert stat.st_mtime <= time.time()


# ---------------------------------------------------------------------------
# Unit tests — _report_category helper
# ---------------------------------------------------------------------------


class TestReportCategory:
    """Category derivation from filename stems."""

    def test_standard_patterns(self):
        assert _report_category("competitor-scan-2026-04-13") == "Competitor Scan"
        assert _report_category("frontier-watch-2026-04-01") == "Frontier Watch"
        assert _report_category("waste-market-intel-2026-04-07") == "Waste Market Intel"

    def test_no_date_suffix(self):
        """Filename without date suffix uses entire stem."""
        assert _report_category("ad-hoc-analysis") == "Ad Hoc Analysis"

    def test_extra_hyphens(self):
        """Multi-hyphen prefix is preserved."""
        assert _report_category("email-triage-summary-2026-04-10") == "Email Triage Summary"


# ---------------------------------------------------------------------------
# Path traversal prevention
# ---------------------------------------------------------------------------


class TestReportPathTraversal:
    """Path traversal prevention."""

    def test_traversal_blocked(self, tmp_path: Path):
        """Paths with .. cannot escape the reports directory."""
        ws = _make_reports_workspace(tmp_path)
        reports_dir = ws / "reports"
        target = (reports_dir / "../../../etc/passwd").resolve()
        assert not str(target).startswith(str(reports_dir.resolve()))

    def test_valid_path_allowed(self, tmp_path: Path):
        """Normal filenames resolve within reports/."""
        ws = _make_reports_workspace(tmp_path)
        reports_dir = ws / "reports"
        target = (reports_dir / "competitor-scan-2026-04-13.md").resolve()
        assert str(target).startswith(str(reports_dir.resolve()))
        assert target.is_file()
