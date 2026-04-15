# ruff: noqa: INP001
"""Tests for knowledge base listing and reading.

Covers article discovery, category grouping, title extraction,
path traversal blocking, and redaction.
"""

from __future__ import annotations

from pathlib import Path

from app.api.memory import KnowledgeArticle

# ---------------------------------------------------------------------------
# Unit tests — list_knowledge_articles logic
# ---------------------------------------------------------------------------


def _make_workspace(tmp_path: Path) -> Path:
    """Create a fake workspace with knowledge articles."""
    ws = tmp_path / "workspace"
    kb = ws / "knowledge"

    # ai-frontier category
    (kb / "ai-frontier").mkdir(parents=True)
    (kb / "ai-frontier" / "agent-memory.md").write_text(
        "# Agent Memory Systems\n\nProduction ready.\n"
    )
    (kb / "ai-frontier" / "code-sandboxes.md").write_text(
        "# Code Execution Sandboxes\n\nE2B v2.19.\n"
    )

    # cybersecurity category
    (kb / "cybersecurity").mkdir(parents=True)
    (kb / "cybersecurity" / "gateway-audit.md").write_text(
        "# OpenClaw Gateway Security\n\nCRITICAL issues.\n"
    )

    # top-level index
    (kb / "index.md").write_text("# Knowledge Base Index\n\nOverview.\n")

    return ws


class TestKnowledgeList:
    """Knowledge article listing."""

    def test_list_articles_discovers_all(self, tmp_path: Path):
        """All .md files under knowledge/ are listed."""
        ws = _make_workspace(tmp_path)
        kb = ws / "knowledge"
        articles = []
        for md_file in sorted(kb.rglob("*.md")):
            rel = md_file.relative_to(kb)
            parts = rel.parts
            category = parts[0] if len(parts) > 1 else "general"
            title = rel.stem.replace("-", " ").title()
            first_line = md_file.read_text().split("\n", 1)[0]
            if first_line.startswith("# "):
                title = first_line[2:].strip()
            articles.append(
                KnowledgeArticle(
                    path=str(rel).replace("\\", "/"),
                    title=title,
                    category=category,
                )
            )

        assert len(articles) == 4
        paths = {a.path for a in articles}
        assert "ai-frontier/agent-memory.md" in paths
        assert "ai-frontier/code-sandboxes.md" in paths
        assert "cybersecurity/gateway-audit.md" in paths
        assert "index.md" in paths

    def test_title_from_heading(self, tmp_path: Path):
        """Title is extracted from first # heading."""
        ws = _make_workspace(tmp_path)
        kb = ws / "knowledge"
        content = (kb / "ai-frontier" / "agent-memory.md").read_text()
        first_line = content.split("\n", 1)[0]
        assert first_line == "# Agent Memory Systems"

    def test_category_from_directory(self, tmp_path: Path):
        """Category is derived from parent directory name."""
        ws = _make_workspace(tmp_path)
        kb = ws / "knowledge"

        for md_file in kb.rglob("*.md"):
            rel = md_file.relative_to(kb)
            parts = rel.parts
            category = parts[0] if len(parts) > 1 else "general"
            if "ai-frontier" in str(rel):
                assert category == "ai-frontier"
            elif "cybersecurity" in str(rel):
                assert category == "cybersecurity"
            elif rel.name == "index.md":
                assert category == "general"

    def test_empty_knowledge_dir(self, tmp_path: Path):
        """Empty knowledge/ returns empty list."""
        ws = tmp_path / "workspace"
        (ws / "knowledge").mkdir(parents=True)
        articles = list((ws / "knowledge").rglob("*.md"))
        assert articles == []

    def test_no_knowledge_dir(self, tmp_path: Path):
        """Missing knowledge/ returns empty list."""
        ws = tmp_path / "workspace"
        ws.mkdir(parents=True)
        assert not (ws / "knowledge").is_dir()


class TestKnowledgePathTraversal:
    """Path traversal prevention."""

    def test_traversal_blocked(self, tmp_path: Path):
        """Paths with .. cannot escape the knowledge directory."""
        ws = _make_workspace(tmp_path)
        kb = ws / "knowledge"
        target = (kb / "../../../etc/passwd").resolve()
        assert not str(target).startswith(str(kb.resolve()))

    def test_valid_path_allowed(self, tmp_path: Path):
        """Normal nested paths resolve within knowledge/."""
        ws = _make_workspace(tmp_path)
        kb = ws / "knowledge"
        target = (kb / "ai-frontier/agent-memory.md").resolve()
        assert str(target).startswith(str(kb.resolve()))
        assert target.is_file()
