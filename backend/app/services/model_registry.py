"""Model registry — tracks OpenRouter models, versions, and deprecation status.

Provides a centralized catalog for model version pinning and deprecation
alerting.  Backed by an in-memory cache with JSON-file persistence so it
survives restarts without requiring a DB table.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

# Regex to detect date-based version suffixes (e.g. "-20260514", "-20260101")
_DATE_SUFFIX_RE = re.compile(r"-\d{8}$")
# Also match version-style suffixes like "-4-5", "-v3.2" for family grouping
_VERSION_SUFFIX_RE = re.compile(r"-v?\d+[\.\d]*$")


def _extract_family(model_id: str) -> str:
    """Extract the model family from an OpenRouter model ID.

    Examples:
        "anthropic/claude-sonnet-4-20260514" → "anthropic/claude-sonnet-4"
        "anthropic/claude-sonnet-4"          → "anthropic/claude-sonnet-4"
        "deepseek/deepseek-v3.2"             → "deepseek/deepseek-v3.2"
        "openai/gpt-5-nano"                  → "openai/gpt-5-nano"
    """
    # Only strip date suffixes (YYYYMMDD) — these are the version identifiers
    # on OpenRouter.  Keep model-name suffixes like "-v3.2" or "-nano" intact.
    return _DATE_SUFFIX_RE.sub("", model_id)


def _classify_tier(prompt_per_m: float) -> int:
    """Classify model into tier 1-4 based on prompt price per 1M tokens."""
    if prompt_per_m <= 0.3:
        return 1
    if prompt_per_m <= 1.0:
        return 2
    if prompt_per_m <= 5.0:
        return 3
    return 4


@dataclass
class ModelEntry:
    """A single model version in the registry."""

    model_id: str  # Full OpenRouter ID, e.g. "anthropic/claude-sonnet-4-20260514"
    family: str  # Family grouping, e.g. "anthropic/claude-sonnet-4"
    provider: str  # e.g. "anthropic"
    name: str  # Human-readable name from OpenRouter
    context_window: int = 0
    prompt_price_per_m: float = 0.0
    completion_price_per_m: float = 0.0
    tier: int = 2
    status: str = "active"  # "active", "deprecated", "removed"
    first_seen: float = 0.0  # Unix timestamp
    last_seen: float = 0.0  # Unix timestamp


@dataclass
class DeprecationWarning:
    """Warning for a pinned model that is no longer available."""

    pinned_model_id: str
    pin_key: str  # Which pin role this was (e.g. "primary")
    status: str  # "deprecated" or "removed"
    suggested_replacement: str | None = None


@dataclass
class RefreshResult:
    """Result of a registry refresh operation."""

    total_models: int = 0
    new_models: int = 0
    deprecated_models: int = 0
    refresh_time_ms: int = 0


class ModelRegistry:
    """In-memory model catalog with JSON-file persistence."""

    def __init__(self) -> None:
        self._entries: dict[str, ModelEntry] = {}
        self._last_refresh: float = 0.0
        self._persistence_path: Path | None = None

    def set_persistence_path(self, path: Path) -> None:
        """Set the JSON file path for persistence."""
        self._persistence_path = path
        self._load_from_file()

    def _load_from_file(self) -> None:
        """Load cached entries from the JSON persistence file."""
        if not self._persistence_path or not self._persistence_path.exists():
            return
        try:
            data = json.loads(self._persistence_path.read_text())
            for entry_dict in data.get("entries", []):
                entry = ModelEntry(**entry_dict)
                self._entries[entry.model_id] = entry
            self._last_refresh = data.get("last_refresh", 0.0)
            logger.info(
                "model_registry.loaded_from_file",
                extra={"count": len(self._entries), "path": str(self._persistence_path)},
            )
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.warning("model_registry.load_failed", extra={"error": str(exc)})

    def _save_to_file(self) -> None:
        """Persist current entries to the JSON file."""
        if not self._persistence_path:
            return
        try:
            self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "last_refresh": self._last_refresh,
                "entries": [asdict(e) for e in self._entries.values()],
            }
            self._persistence_path.write_text(json.dumps(data, indent=2))
        except OSError as exc:
            logger.warning("model_registry.save_failed", extra={"error": str(exc)})

    async def refresh(self, api_key: str | None = None) -> RefreshResult:
        """Fetch models from OpenRouter and update the registry.

        Models that were previously known but are no longer returned by
        OpenRouter are marked as ``deprecated``.
        """
        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = {}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                resp = await client.get("https://openrouter.ai/api/v1/models", headers=headers)
                resp.raise_for_status()
                raw_models = resp.json().get("data", [])
        except Exception as exc:
            logger.warning("model_registry.refresh_failed", extra={"error": str(exc)})
            return RefreshResult()

        now = time.time()
        seen_ids: set[str] = set()
        new_count = 0

        for m in raw_models:
            model_id: str = m.get("id", "")
            if not model_id:
                continue
            seen_ids.add(model_id)

            pricing = m.get("pricing", {})
            prompt_price = float(pricing.get("prompt", 0)) * 1_000_000
            completion_price = float(pricing.get("completion", 0)) * 1_000_000
            provider = model_id.split("/")[0] if "/" in model_id else ""

            if model_id in self._entries:
                # Update existing entry
                entry = self._entries[model_id]
                entry.name = m.get("name", model_id)
                entry.context_window = m.get("context_length", 0) or 0
                entry.prompt_price_per_m = round(prompt_price, 4)
                entry.completion_price_per_m = round(completion_price, 4)
                entry.tier = _classify_tier(prompt_price)
                entry.status = "active"
                entry.last_seen = now
            else:
                # New model
                self._entries[model_id] = ModelEntry(
                    model_id=model_id,
                    family=_extract_family(model_id),
                    provider=provider,
                    name=m.get("name", model_id),
                    context_window=m.get("context_length", 0) or 0,
                    prompt_price_per_m=round(prompt_price, 4),
                    completion_price_per_m=round(completion_price, 4),
                    tier=_classify_tier(prompt_price),
                    status="active",
                    first_seen=now,
                    last_seen=now,
                )
                new_count += 1

        # Mark previously-known models that disappeared as deprecated
        deprecated_count = 0
        for model_id, entry in self._entries.items():
            if model_id not in seen_ids and entry.status == "active":
                entry.status = "deprecated"
                deprecated_count += 1

        self._last_refresh = now
        self._save_to_file()

        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "model_registry.refreshed",
            extra={
                "total": len(seen_ids),
                "new": new_count,
                "deprecated": deprecated_count,
                "elapsed_ms": elapsed_ms,
            },
        )
        return RefreshResult(
            total_models=len(seen_ids),
            new_models=new_count,
            deprecated_models=deprecated_count,
            refresh_time_ms=elapsed_ms,
        )

    @property
    def last_refresh(self) -> float:
        return self._last_refresh

    def list_models(self, *, status: str | None = None) -> list[ModelEntry]:
        """List all known models, optionally filtered by status."""
        entries = list(self._entries.values())
        if status:
            entries = [e for e in entries if e.status == status]
        entries.sort(key=lambda e: (e.provider, e.family, e.model_id))
        return entries

    def get_model(self, model_id: str) -> ModelEntry | None:
        """Get a specific model by ID."""
        return self._entries.get(model_id)

    def get_family_versions(self, family: str) -> list[ModelEntry]:
        """Get all versions of a model family, sorted newest first."""
        entries = [e for e in self._entries.values() if e.family == family]
        entries.sort(key=lambda e: e.last_seen, reverse=True)
        return entries

    def list_families(self) -> list[str]:
        """List all unique model families."""
        families = sorted({e.family for e in self._entries.values()})
        return families

    def check_pins(self, pins: dict[str, str]) -> list[DeprecationWarning]:
        """Check pinned model IDs for deprecation or removal.

        Args:
            pins: Mapping of pin key (e.g. "primary") to model ID.

        Returns:
            List of warnings for pinned models that are deprecated or removed.
        """
        warnings: list[DeprecationWarning] = []
        for pin_key, model_id in pins.items():
            entry = self._entries.get(model_id)
            if entry is None:
                # Model not in registry at all — might have been removed
                # or never seen.  Only warn if registry has been populated.
                if self._entries:
                    # Try to find a replacement in the same family
                    family = _extract_family(model_id)
                    versions = self.get_family_versions(family)
                    replacement = versions[0].model_id if versions else None
                    warnings.append(
                        DeprecationWarning(
                            pinned_model_id=model_id,
                            pin_key=pin_key,
                            status="removed",
                            suggested_replacement=replacement,
                        )
                    )
            elif entry.status == "deprecated":
                family_versions = self.get_family_versions(entry.family)
                active_versions = [v for v in family_versions if v.status == "active"]
                replacement = active_versions[0].model_id if active_versions else None
                warnings.append(
                    DeprecationWarning(
                        pinned_model_id=model_id,
                        pin_key=pin_key,
                        status="deprecated",
                        suggested_replacement=replacement,
                    )
                )
        return warnings

    def get_context_window(self, model_name: str) -> int | None:
        """Look up context window for a model by short name or full ID.

        Useful for the budget monitor to replace hardcoded lookups.
        """
        # Try exact match first
        entry = self._entries.get(model_name)
        if entry:
            return entry.context_window

        # Try matching by short name (without provider prefix)
        for entry in self._entries.values():
            short = entry.model_id.split("/")[-1] if "/" in entry.model_id else entry.model_id
            if short == model_name and entry.status == "active":
                return entry.context_window

        return None


# Module-level singleton
_registry = ModelRegistry()


def get_registry() -> ModelRegistry:
    """Get the module-level model registry singleton."""
    return _registry
