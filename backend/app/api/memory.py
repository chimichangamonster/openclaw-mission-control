"""Agent memory file management — read/edit gateway workspace files."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import ORG_MEMBER_DEP
from app.core.logging import get_logger
from app.core.redact import redact_sensitive
from app.core.workspace import resolve_org_workspace
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)
router = APIRouter(prefix="/memory", tags=["memory"])

MEMORY_FILES = [
    {"name": "IDENTITY.md", "description": "Who The Claw is — name, role, personality"},
    {"name": "SOUL.md", "description": "Core values, behavior guidelines, boundaries"},
    {"name": "USER.md", "description": "Information about you — preferences, businesses, contacts"},
    {"name": "TOOLS.md", "description": "Available tools, API keys, endpoints"},
    {"name": "HEARTBEAT.md", "description": "Periodic health check configuration"},
    {"name": "AGENTS.md", "description": "Agent definitions and capabilities"},
]


class MemoryFile(BaseModel):
    name: str
    description: str
    content: str | None = None


class MemoryFileUpdate(BaseModel):
    content: str


@router.get("/files", summary="List all memory files")
async def list_memory_files(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> list[MemoryFile]:
    workspace = resolve_org_workspace(ctx.organization)
    files = []
    for f in MEMORY_FILES:
        path = workspace / f["name"]
        exists = path.exists()
        files.append(
            MemoryFile(
                name=f["name"],
                description=f["description"],
                content=None if not exists else f"({path.stat().st_size} bytes)",
            )
        )
    return files


@router.get("/files/{filename}", summary="Read a memory file")
async def read_memory_file(
    filename: str,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> MemoryFile:
    valid_files = {f["name"] for f in MEMORY_FILES}
    if filename not in valid_files:
        raise HTTPException(status_code=404, detail=f"Unknown memory file: {filename}")

    desc = next(f["description"] for f in MEMORY_FILES if f["name"] == filename)
    workspace = resolve_org_workspace(ctx.organization)
    path = workspace / filename

    if not path.exists():
        return MemoryFile(name=filename, description=desc, content="")

    content = path.read_text(encoding="utf-8")
    # Strip credentials/tokens before serving to browser
    result = redact_sensitive(content)
    if result.redaction_count > 0:
        logger.warning(
            "memory.file.credentials_redacted",
            extra={
                "filename": filename,
                "redaction_count": result.redaction_count,
                "categories": sorted(result.categories),
            },
        )
    return MemoryFile(name=filename, description=desc, content=result.text)


@router.put("/files/{filename}", summary="Update a memory file")
async def update_memory_file(
    filename: str,
    body: MemoryFileUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> MemoryFile:
    valid_files = {f["name"] for f in MEMORY_FILES}
    if filename not in valid_files:
        raise HTTPException(status_code=404, detail=f"Unknown memory file: {filename}")

    desc = next(f["description"] for f in MEMORY_FILES if f["name"] == filename)
    workspace = resolve_org_workspace(ctx.organization)
    path = workspace / filename

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.content, encoding="utf-8")
    logger.info("memory.file.updated", extra={"filename": filename})

    return MemoryFile(name=filename, description=desc, content=body.content)


# ── Knowledge base (read-only, compiled by knowledge-compile skill) ──


class KnowledgeArticle(BaseModel):
    path: str
    title: str
    category: str


@router.get("/knowledge", summary="List knowledge base articles")
async def list_knowledge_articles(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> list[KnowledgeArticle]:
    """List compiled knowledge articles under workspace/knowledge/."""
    workspace = resolve_org_workspace(ctx.organization)
    kb_dir = workspace / "knowledge"
    if not kb_dir.is_dir():
        return []

    articles: list[KnowledgeArticle] = []
    for md_file in sorted(kb_dir.rglob("*.md")):
        rel = md_file.relative_to(kb_dir)
        parts = rel.parts
        category = parts[0] if len(parts) > 1 else "general"
        # Derive title from first heading or filename
        title = rel.stem.replace("-", " ").title()
        try:
            first_line = md_file.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
            if first_line.startswith("# "):
                title = first_line[2:].strip()
        except OSError:
            pass
        articles.append(
            KnowledgeArticle(
                path=str(rel).replace("\\", "/"),
                title=title,
                category=category,
            )
        )
    return articles


@router.get("/knowledge/{article_path:path}", summary="Read a knowledge article")
async def read_knowledge_article(
    article_path: str,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> MemoryFile:
    """Read a single knowledge base article. Path is relative to knowledge/."""
    workspace = resolve_org_workspace(ctx.organization)
    kb_dir = workspace / "knowledge"
    target = (kb_dir / article_path).resolve()

    # Path traversal guard
    if not str(target).startswith(str(kb_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Article not found")

    content = target.read_text(encoding="utf-8", errors="replace")
    result = redact_sensitive(content)
    return MemoryFile(
        name=article_path,
        description="Knowledge base article",
        content=result.text,
    )


# ── Cron reports (read-only, written by cron skills to workspace/reports/) ──

_DATE_SUFFIX_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def _report_category(stem: str) -> str:
    """Derive category from report filename stem.

    ``competitor-scan-2026-04-13`` → ``Competitor Scan``
    """
    name = _DATE_SUFFIX_RE.sub("", stem)
    return name.replace("-", " ").title()


class Report(BaseModel):
    path: str
    title: str
    category: str
    file_size: int
    created_at: str


@router.get("/reports", summary="List cron-generated reports")
async def list_reports(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> list[Report]:
    """List cron-generated markdown reports under workspace/reports/."""
    workspace = resolve_org_workspace(ctx.organization)
    reports_dir = workspace / "reports"
    if not reports_dir.is_dir():
        return []

    reports: list[Report] = []
    for md_file in sorted(reports_dir.glob("*.md"), reverse=True):
        stat = md_file.stat()
        title = md_file.stem.replace("-", " ").title()
        try:
            first_line = md_file.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
            if first_line.startswith("# "):
                title = first_line[2:].strip()
        except OSError:
            pass
        reports.append(
            Report(
                path=md_file.name,
                title=title,
                category=_report_category(md_file.stem),
                file_size=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            )
        )
    return reports


@router.get("/reports/{report_path:path}", summary="Read a cron-generated report")
async def read_report(
    report_path: str,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> MemoryFile:
    """Read a single cron report. Path is relative to reports/."""
    workspace = resolve_org_workspace(ctx.organization)
    reports_dir = workspace / "reports"
    target = (reports_dir / report_path).resolve()

    # Path traversal guard
    if not str(target).startswith(str(reports_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Report not found")

    content = target.read_text(encoding="utf-8", errors="replace")
    result = redact_sensitive(content)
    return MemoryFile(
        name=report_path,
        description="Cron-generated report",
        content=result.text,
    )
