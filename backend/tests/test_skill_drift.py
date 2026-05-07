# ruff: noqa: INP001
"""Tests for skill_drift service — pure parser + drift math + filesystem walks.

Mirrors the test_platform_cron_failures.py pattern. Re-implements the parser
locally for the hot loop tests, and exercises the real service for the disk +
orchestrator paths via tmp_path fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.skill_drift import (
    audit_skill_drift,
    compute_drift,
    list_directory_names,
    list_gateway_workspace_skills,
    parse_registry,
)

# ---------------------------------------------------------------------------
# Registry parser — must match the regex parser in audit-shared-skills.sh
# ---------------------------------------------------------------------------


SAMPLE_REGISTRY = """\
# header comment
shared_skills:
  - bookkeeping
  - cron-manager      # (*)
  - doc-gen
  - notifications

gateways:
  vantage-solutions:
    name: "Vantage Solutions"
    org_skills:
      - ble-scan
      - hash-crack
      - dns-enum
    notes: "primary"
  waste-gurus:
    name: "Waste Gurus"
    org_skills:
      - rfp-scan
  personal:
    name: "Personal"
"""


class TestParseRegistry:
    def test_parses_shared_skills(self) -> None:
        shared, _orgs = parse_registry(SAMPLE_REGISTRY)
        assert shared == {"bookkeeping", "cron-manager", "doc-gen", "notifications"}

    def test_parses_per_org_skills(self) -> None:
        _shared, orgs = parse_registry(SAMPLE_REGISTRY)
        assert orgs["vantage-solutions"] == {"ble-scan", "hash-crack", "dns-enum"}
        assert orgs["waste-gurus"] == {"rfp-scan"}

    def test_strips_inline_comments(self) -> None:
        # `cron-manager      # (*)` should parse to `cron-manager`, not include the comment
        shared, _orgs = parse_registry(SAMPLE_REGISTRY)
        assert "cron-manager" in shared
        assert not any("#" in s or "*" in s for s in shared)

    def test_org_with_no_skills_block_yields_empty_set(self) -> None:
        _shared, orgs = parse_registry(SAMPLE_REGISTRY)
        # `personal:` has no `org_skills:` line — should appear with empty set
        assert orgs["personal"] == set()

    def test_empty_registry(self) -> None:
        shared, orgs = parse_registry("# just comments\n")
        assert shared == set()
        assert orgs == {}

    def test_registry_with_only_shared(self) -> None:
        content = "shared_skills:\n  - foo\n  - bar\n"
        shared, orgs = parse_registry(content)
        assert shared == {"foo", "bar"}
        assert orgs == {}


# ---------------------------------------------------------------------------
# Drift math — set arithmetic with the orphan-minus-shared rule
# ---------------------------------------------------------------------------


class TestComputeDrift:
    def test_all_in_sync(self) -> None:
        result = compute_drift(
            registry_shared={"a", "b"},
            registry_orgs={"vs": {"x", "y"}},
            vps_shared={"a", "b"},
            vps_orgs={"vs": {"x", "y"}},
        )
        assert result["total_drift"] == 0
        assert result["total_orphan"] == 0
        assert result["shared"]["ok_count"] == 2

    def test_shared_drift(self) -> None:
        # `b` is in registry but not on VPS — drift
        result = compute_drift(
            registry_shared={"a", "b"},
            registry_orgs={},
            vps_shared={"a"},
            vps_orgs={},
        )
        assert result["total_drift"] == 1
        assert result["shared"]["drift"] == ["b"]

    def test_shared_orphan(self) -> None:
        # `c` is on VPS but not in registry — orphan
        result = compute_drift(
            registry_shared={"a"},
            registry_orgs={},
            vps_shared={"a", "c"},
            vps_orgs={},
        )
        assert result["total_orphan"] == 1
        assert result["shared"]["orphan"] == ["c"]

    def test_per_org_drift(self) -> None:
        result = compute_drift(
            registry_shared=set(),
            registry_orgs={"vs": {"x", "y"}},
            vps_shared=set(),
            vps_orgs={"vs": {"x"}},
        )
        assert result["total_drift"] == 1
        assert result["by_org"][0]["drift"] == ["y"]

    def test_per_org_orphan_excludes_shared(self) -> None:
        # `bookkeeping` is shared (mounted, not copied) — must NOT count as
        # orphan when found in a per-org workspace.
        result = compute_drift(
            registry_shared={"bookkeeping"},
            registry_orgs={"vs": {"hash-crack"}},
            vps_shared={"bookkeeping"},
            vps_orgs={"vs": {"hash-crack", "bookkeeping"}},
        )
        assert result["total_orphan"] == 0
        assert result["by_org"][0]["orphan"] == []

    def test_per_org_orphan_genuine(self) -> None:
        # `accidental-skill` is NOT in registry shared OR org_skills — orphan.
        result = compute_drift(
            registry_shared={"bookkeeping"},
            registry_orgs={"vs": set()},
            vps_shared={"bookkeeping"},
            vps_orgs={"vs": {"accidental-skill"}},
        )
        assert result["total_orphan"] == 1
        assert result["by_org"][0]["orphan"] == ["accidental-skill"]

    def test_org_only_in_vps_shows_up(self) -> None:
        # Gateway exists on disk but not in registry — slug appears with all-orphan
        result = compute_drift(
            registry_shared=set(),
            registry_orgs={},
            vps_shared=set(),
            vps_orgs={"rogue-org": {"foo"}},
        )
        slugs = [o["slug"] for o in result["by_org"]]
        assert "rogue-org" in slugs

    def test_org_only_in_registry_shows_up(self) -> None:
        # Gateway in registry but not yet provisioned on disk — all-drift
        result = compute_drift(
            registry_shared=set(),
            registry_orgs={"future-org": {"foo"}},
            vps_shared=set(),
            vps_orgs={},
        )
        future = next(o for o in result["by_org"] if o["slug"] == "future-org")
        assert future["drift"] == ["foo"]


# ---------------------------------------------------------------------------
# Filesystem walks — degrade gracefully on missing paths
# ---------------------------------------------------------------------------


class TestListDirectoryNames:
    def test_lists_subdirs(self, tmp_path: Path) -> None:
        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()
        (tmp_path / "afile.txt").write_text("ignored")
        result = list_directory_names(tmp_path)
        assert result == {"alpha", "beta"}

    def test_returns_empty_for_missing_path(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist"
        assert list_directory_names(missing) == set()

    def test_returns_empty_for_file_path(self, tmp_path: Path) -> None:
        f = tmp_path / "notadir"
        f.write_text("x")
        assert list_directory_names(f) == set()


class TestListGatewayWorkspaceSkills:
    def test_walks_gateway_workspace_layout(self, tmp_path: Path) -> None:
        # Mirror the real layout: {root}/{slug}/.openclaw/workspace/skills/{skill}
        for slug, skills in [("vs", ["a", "b"]), ("wg", ["c"])]:
            base = tmp_path / slug / ".openclaw" / "workspace" / "skills"
            base.mkdir(parents=True)
            for skill in skills:
                (base / skill).mkdir()

        result = list_gateway_workspace_skills(tmp_path)
        assert result == {"vs": {"a", "b"}, "wg": {"c"}}

    def test_handles_gateway_with_no_skills_dir(self, tmp_path: Path) -> None:
        # Slug exists but no .openclaw/workspace/skills inside — return empty set
        (tmp_path / "fresh-org").mkdir()
        result = list_gateway_workspace_skills(tmp_path)
        assert result == {"fresh-org": set()}

    def test_returns_empty_for_missing_root(self, tmp_path: Path) -> None:
        missing = tmp_path / "no-such-dir"
        assert list_gateway_workspace_skills(missing) == {}


# ---------------------------------------------------------------------------
# Orchestrator — full audit with all substrates available, and degraded modes
# ---------------------------------------------------------------------------


class TestAuditSkillDrift:
    @pytest.fixture
    def workspace_root(self, tmp_path: Path) -> Path:
        # Fully provisioned: registry says 2 shared + 1 per-org, VPS has same.
        registry = tmp_path / "registry.yml"
        registry.write_text(
            "shared_skills:\n"
            "  - bookkeeping\n"
            "  - doc-gen\n"
            "\n"
            "gateways:\n"
            "  vs:\n"
            "    org_skills:\n"
            "      - hash-crack\n"
        )
        shared_skills = tmp_path / "shared-skills"
        shared_skills.mkdir()
        (shared_skills / "bookkeeping").mkdir()
        (shared_skills / "doc-gen").mkdir()

        workspaces = tmp_path / "workspaces"
        skills_dir = workspaces / "vs" / ".openclaw" / "workspace" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "hash-crack").mkdir()

        return tmp_path

    def test_all_synced(self, workspace_root: Path) -> None:
        result = audit_skill_drift(
            registry_path=workspace_root / "registry.yml",
            shared_skills_root=workspace_root / "shared-skills",
            workspaces_root=workspace_root / "workspaces",
        )
        assert result["available"] is True
        assert result["total_drift"] == 0
        assert result["total_orphan"] == 0

    def test_detects_shared_drift(self, workspace_root: Path) -> None:
        # Remove a shared skill from VPS — registry expects it, drift = 1
        (workspace_root / "shared-skills" / "doc-gen").rmdir()
        result = audit_skill_drift(
            registry_path=workspace_root / "registry.yml",
            shared_skills_root=workspace_root / "shared-skills",
            workspaces_root=workspace_root / "workspaces",
        )
        assert result["total_drift"] == 1
        assert "doc-gen" in result["shared"]["drift"]

    def test_detects_orphan(self, workspace_root: Path) -> None:
        # Add a skill to VPS that isn't in registry
        (workspace_root / "shared-skills" / "rogue").mkdir()
        result = audit_skill_drift(
            registry_path=workspace_root / "registry.yml",
            shared_skills_root=workspace_root / "shared-skills",
            workspaces_root=workspace_root / "workspaces",
        )
        assert result["total_orphan"] == 1
        assert "rogue" in result["shared"]["orphan"]

    def test_missing_registry_degrades_gracefully(self, tmp_path: Path) -> None:
        result = audit_skill_drift(
            registry_path=tmp_path / "missing.yml",
            shared_skills_root=tmp_path / "missing-shared",
            workspaces_root=tmp_path / "missing-ws",
        )
        assert result["available"] is False
        assert result["total_drift"] == 0
        assert result["total_orphan"] == 0
        assert result["sources"]["registry"]["available"] is False
        assert result["sources"]["shared_skills_dir"]["available"] is False
        assert result["sources"]["workspaces_dir"]["available"] is False

    def test_partial_availability_flagged(self, workspace_root: Path) -> None:
        # Registry exists, shared-skills doesn't — partial
        result = audit_skill_drift(
            registry_path=workspace_root / "registry.yml",
            shared_skills_root=workspace_root / "missing-shared",
            workspaces_root=workspace_root / "workspaces",
        )
        assert result["available"] is False  # not fully available
        assert result["sources"]["registry"]["available"] is True
        assert result["sources"]["shared_skills_dir"]["available"] is False
