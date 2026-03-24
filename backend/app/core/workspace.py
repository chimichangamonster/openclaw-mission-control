"""Per-org gateway workspace resolution.

Resolves the correct gateway workspace directory for an organization,
supporting both per-org gateways (GATEWAY_WORKSPACES_ROOT) and the
legacy single-workspace mode (GATEWAY_WORKSPACE_PATH).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from app.models.organizations import Organization


def resolve_org_workspace(org: Organization) -> Path:
    """Return the gateway workspace path for an organization.

    Per-org mode: ``{GATEWAY_WORKSPACES_ROOT}/{slug}/.openclaw/workspace``
    Legacy mode:  ``{GATEWAY_WORKSPACE_PATH}`` (shared by all orgs)
    """
    root = settings.gateway_workspaces_root
    if root and org.slug:
        return Path(root) / org.slug / ".openclaw" / "workspace"
    # Fallback to legacy single-workspace
    wp = settings.gateway_workspace_path
    if wp:
        return Path(wp)
    return Path("/app/gateway-workspace")
