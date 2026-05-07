"""Skill-drift audit — server-side equivalent of scripts/audit-shared-skills.sh.

Surfaces drift between the declarative `gateways/registry.yml` and the actual
skill directories deployed under `/opt/openclaw-business-platform/`.

Three categories:
- OK     — listed in registry AND present on disk
- DRIFT  — listed in registry but missing on disk
- ORPHAN — present on disk but not declared in registry (per-org orphans
           explicitly exclude shared skills, which are mounted not copied)

Pure functions where possible — the disk-walking helpers degrade gracefully
when the configured paths are missing (dev/test environments don't have the
VPS-side directories), returning empty sets so the orchestrator can flag
`available=False` rather than 500.

Mirrors the regex-based YAML parser from `scripts/audit-shared-skills.sh`
deliberately — pyyaml is a transitive dep, not declared, and the audit script
is the operator's source of truth. Drift between this code and that script
would produce inconsistent numbers across the CLI and the /platform stat card.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Registry parsing — regex-based, mirrors the shell script
# ---------------------------------------------------------------------------


def parse_registry(content: str) -> tuple[set[str], dict[str, set[str]]]:
    """Parse a gateway registry.yml string into (shared_skills, per_org_skills).

    Mirrors the parser in scripts/audit-shared-skills.sh exactly. Regex-based
    so we don't acquire a yaml dependency for a single-purpose parse.
    """
    shared: list[str] = []
    in_shared = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped == "shared_skills:":
            in_shared = True
            continue
        if in_shared:
            if stripped.startswith("- "):
                skill = stripped[2:].split("#")[0].strip()
                if skill:
                    shared.append(skill)
            elif stripped and not stripped.startswith("#") and not stripped.startswith("-"):
                in_shared = False

    orgs: dict[str, list[str]] = {}
    current_org: str | None = None
    in_org_skills = False
    in_gateways = False
    for line in content.split("\n"):
        if line.startswith("gateways:"):
            in_gateways = True
            continue
        if not in_gateways:
            continue
        if re.match(r"^[a-z][a-z0-9-]*:\s*$", line):
            # Top-level key — out of gateways block
            in_gateways = False
            continue
        m = re.match(r"^  ([a-z][a-z0-9-]+):\s*$", line)
        if m:
            current_org = m.group(1)
            orgs[current_org] = []
            in_org_skills = False
            continue
        if current_org and line.strip() == "org_skills:":
            in_org_skills = True
            continue
        if in_org_skills:
            s = line.strip()
            if s.startswith("- "):
                skill = s[2:].split("#")[0].strip()
                if skill:
                    orgs[current_org].append(skill)
            elif s and not s.startswith("#") and current_org:
                in_org_skills = False

    return set(shared), {slug: set(skills) for slug, skills in orgs.items()}


# ---------------------------------------------------------------------------
# Disk reads — degrade gracefully on missing paths
# ---------------------------------------------------------------------------


def list_directory_names(directory: Path) -> set[str]:
    """List immediate-child directory names. Returns empty set if missing."""
    if not directory.exists() or not directory.is_dir():
        return set()
    try:
        return {entry.name for entry in directory.iterdir() if entry.is_dir()}
    except OSError as exc:
        logger.warning(
            "skill_drift.dir_list_failed",
            extra={"path": str(directory), "error": str(exc)},
        )
        return set()


def list_gateway_workspace_skills(workspaces_root: Path) -> dict[str, set[str]]:
    """For each gateway slug, list skills present in its workspace/skills/ dir.

    Path layout (per CLAUDE.md "Workspace resolution"):
      {workspaces_root}/{slug}/.openclaw/workspace/skills/{skill_name}/
    """
    result: dict[str, set[str]] = {}
    if not workspaces_root.exists() or not workspaces_root.is_dir():
        return result
    try:
        slug_dirs = [d for d in workspaces_root.iterdir() if d.is_dir()]
    except OSError as exc:
        logger.warning(
            "skill_drift.workspaces_root_unreadable",
            extra={"path": str(workspaces_root), "error": str(exc)},
        )
        return result

    for slug_dir in slug_dirs:
        skills_dir = slug_dir / ".openclaw" / "workspace" / "skills"
        result[slug_dir.name] = list_directory_names(skills_dir)
    return result


# ---------------------------------------------------------------------------
# Pure drift computation
# ---------------------------------------------------------------------------


def compute_drift(
    *,
    registry_shared: set[str],
    registry_orgs: dict[str, set[str]],
    vps_shared: set[str],
    vps_orgs: dict[str, set[str]],
) -> dict[str, object]:
    """Compute drift + orphan counts. Per-org orphans exclude shared skills.

    Shared skills are mounted read-only into every gateway, so their presence
    in a per-org workspace would be a registry-config quirk, not an orphan
    deploy. Mirror the audit script's `actual - expected - reg_shared` formula.
    """
    shared_ok = sorted(registry_shared & vps_shared)
    shared_drift = sorted(registry_shared - vps_shared)
    shared_orphan = sorted(vps_shared - registry_shared)

    all_slugs = sorted(set(registry_orgs.keys()) | set(vps_orgs.keys()))
    per_org: list[dict[str, object]] = []
    total_org_drift = 0
    total_org_orphan = 0
    for slug in all_slugs:
        expected = registry_orgs.get(slug, set())
        actual = vps_orgs.get(slug, set())
        ok = sorted(expected & actual)
        drift = sorted(expected - actual)
        # Orphan = on VPS but not in registry — minus shared (mounted, not copied).
        orphan = sorted(actual - expected - registry_shared)
        per_org.append(
            {
                "slug": slug,
                "ok": ok,
                "drift": drift,
                "orphan": orphan,
                "ok_count": len(ok),
                "drift_count": len(drift),
                "orphan_count": len(orphan),
            }
        )
        total_org_drift += len(drift)
        total_org_orphan += len(orphan)

    return {
        "shared": {
            "ok": shared_ok,
            "drift": shared_drift,
            "orphan": shared_orphan,
            "ok_count": len(shared_ok),
            "drift_count": len(shared_drift),
            "orphan_count": len(shared_orphan),
        },
        "by_org": per_org,
        "total_drift": len(shared_drift) + total_org_drift,
        "total_orphan": len(shared_orphan) + total_org_orphan,
    }


# ---------------------------------------------------------------------------
# Orchestrator — reads disk + computes drift
# ---------------------------------------------------------------------------


def audit_skill_drift(
    *,
    registry_path: Path | None = None,
    shared_skills_root: Path | None = None,
    workspaces_root: Path | None = None,
) -> dict[str, object]:
    """Run the full drift audit. Resolves paths from env if not supplied.

    Env vars:
      SKILL_REGISTRY_PATH   — defaults to /app/registry.yml (mounted from
                              gateways/registry.yml on VPS)
      SHARED_SKILLS_ROOT    — defaults to /app/shared-skills (mounted from
                              /opt/openclaw-business-platform/shared-skills)
      GATEWAY_WORKSPACES_ROOT — already required for resolve_org_workspace;
                                used here to enumerate per-org skill dirs.

    Returns a result dict with `available` indicating whether each substrate
    was readable. Missing substrates produce empty sets, not 500s, so the
    /platform stat card degrades gracefully on dev/test boxes.
    """
    if registry_path is None:
        registry_path = Path(
            os.environ.get("SKILL_REGISTRY_PATH", "/app/registry.yml")
        )
    if shared_skills_root is None:
        shared_skills_root = Path(
            os.environ.get("SHARED_SKILLS_ROOT", "/app/shared-skills")
        )
    if workspaces_root is None:
        workspaces_root_env = os.environ.get("GATEWAY_WORKSPACES_ROOT")
        workspaces_root = Path(workspaces_root_env) if workspaces_root_env else None

    registry_available = registry_path.exists() and registry_path.is_file()
    shared_available = shared_skills_root.exists() and shared_skills_root.is_dir()
    workspaces_available = (
        workspaces_root is not None
        and workspaces_root.exists()
        and workspaces_root.is_dir()
    )

    if registry_available:
        try:
            registry_content = registry_path.read_text(encoding="utf-8")
            registry_shared, registry_orgs = parse_registry(registry_content)
        except OSError as exc:
            logger.warning(
                "skill_drift.registry_read_failed",
                extra={"path": str(registry_path), "error": str(exc)},
            )
            registry_available = False
            registry_shared = set()
            registry_orgs = {}
    else:
        registry_shared = set()
        registry_orgs = {}

    vps_shared = list_directory_names(shared_skills_root) if shared_available else set()
    vps_orgs = (
        list_gateway_workspace_skills(workspaces_root)
        if workspaces_available and workspaces_root is not None
        else {}
    )

    drift = compute_drift(
        registry_shared=registry_shared,
        registry_orgs=registry_orgs,
        vps_shared=vps_shared,
        vps_orgs=vps_orgs,
    )

    fully_available = registry_available and shared_available and workspaces_available

    return {
        "available": fully_available,
        "sources": {
            "registry": {
                "path": str(registry_path),
                "available": registry_available,
                "shared_skill_count": len(registry_shared),
                "org_count": len(registry_orgs),
            },
            "shared_skills_dir": {
                "path": str(shared_skills_root),
                "available": shared_available,
                "skill_count": len(vps_shared),
            },
            "workspaces_dir": {
                "path": str(workspaces_root) if workspaces_root else None,
                "available": workspaces_available,
                "gateway_count": len(vps_orgs),
            },
        },
        **drift,
    }
