"""Agent memory file management — read/edit gateway workspace files."""

from __future__ import annotations

from pathlib import Path

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
        files.append(MemoryFile(
            name=f["name"],
            description=f["description"],
            content=None if not exists else f"({path.stat().st_size} bytes)",
        ))
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
