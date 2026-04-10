"""Per-org gateway workspace resolution.

Resolves the correct gateway workspace directory for an organization
using per-org gateways (GATEWAY_WORKSPACES_ROOT).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from app.models.organizations import Organization


def resolve_org_workspace(org: Organization) -> Path:
    """Return the gateway workspace path for an organization.

    ``{GATEWAY_WORKSPACES_ROOT}/{slug}/.openclaw/workspace``
    """
    root = settings.gateway_workspaces_root
    if not root:
        raise RuntimeError(
            "GATEWAY_WORKSPACES_ROOT is not configured. "
            "Set it to the parent directory of per-org gateway workspaces."
        )
    if not org.slug:
        raise ValueError(f"Organization {org.id} has no slug — cannot resolve workspace.")
    return Path(root) / org.slug / ".openclaw" / "workspace"
