# ruff: noqa: SLF001

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from app.core import auth
from app.models.users import User


@dataclass
class _FakeSession:
    added: list[Any] = field(default_factory=list)
    committed: int = 0
    refreshed: list[Any] = field(default_factory=list)
    deleted: list[Any] = field(default_factory=list)

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.committed += 1

    async def refresh(self, value: Any) -> None:
        self.refreshed.append(value)

    async def delete(self, value: Any) -> None:
        self.deleted.append(value)


def test_extract_claim_email_prefers_direct_email() -> None:
    claims: dict[str, object] = {
        "email": " User@Example.com ",
        "primary_email_address": "ignored@example.com",
    }
    assert auth._extract_claim_email(claims) == "user@example.com"


def test_extract_claim_email_from_primary_id() -> None:
    claims: dict[str, object] = {
        "primary_email_address_id": "id-2",
        "email_addresses": [
            {"id": "id-1", "email_address": "first@example.com"},
            {"id": "id-2", "email_address": "chosen@example.com"},
        ],
    }
    assert auth._extract_claim_email(claims) == "chosen@example.com"


def test_extract_claim_email_falls_back_to_first_address() -> None:
    claims: dict[str, object] = {
        "email_addresses": [
            {"id": "id-1", "email_address": "first@example.com"},
            {"id": "id-2", "email_address": "second@example.com"},
        ],
    }
    assert auth._extract_claim_email(claims) == "first@example.com"


def test_extract_claim_name_from_parts() -> None:
    claims: dict[str, object] = {
        "given_name": "Alex",
        "family_name": "Morgan",
    }
    assert auth._extract_claim_name(claims) == "Alex Morgan"


def test_extract_clerk_profile_prefers_primary_email() -> None:
    profile = SimpleNamespace(
        primary_email_address_id="e2",
        email_addresses=[
            SimpleNamespace(id="e1", email_address="first@example.com"),
            SimpleNamespace(id="e2", email_address="primary@example.com"),
        ],
        first_name="Asha",
        last_name="Rao",
    )
    email, name = auth._extract_clerk_profile(profile)
    assert email == "primary@example.com"
    assert name == "Asha"


@pytest.mark.asyncio
async def test_get_or_sync_user_updates_email_and_name(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = User(clerk_user_id="user_123", email="old@example.com", name=None)

    async def _fake_get_or_create(*_args: Any, **_kwargs: Any) -> tuple[User, bool]:
        return existing, False

    async def _fake_fetch(_clerk_user_id: str) -> tuple[str | None, str | None]:
        return "new@example.com", "New Name"

    monkeypatch.setattr(auth.crud, "get_or_create", _fake_get_or_create)
    monkeypatch.setattr(auth, "_fetch_clerk_profile", _fake_fetch)

    session = _FakeSession()
    out = await auth._get_or_sync_user(
        session,  # type: ignore[arg-type]
        clerk_user_id="user_123",
        claims={},
    )

    assert out is existing
    assert existing.email == "new@example.com"
    assert existing.name == "New Name"
    assert session.committed == 1
    assert session.refreshed == [existing]


@pytest.mark.asyncio
async def test_get_or_sync_user_uses_clerk_profile_when_claims_are_minimal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = User(clerk_user_id="user_123", email=None, name=None)

    async def _fake_get_or_create(*_args: Any, **_kwargs: Any) -> tuple[User, bool]:
        return existing, False

    async def _fake_fetch(_clerk_user_id: str) -> tuple[str | None, str | None]:
        return "from-clerk@example.com", "From Clerk"

    monkeypatch.setattr(auth.crud, "get_or_create", _fake_get_or_create)
    monkeypatch.setattr(auth, "_fetch_clerk_profile", _fake_fetch)

    session = _FakeSession()
    out = await auth._get_or_sync_user(
        session,  # type: ignore[arg-type]
        clerk_user_id="user_123",
        claims={"sub": "user_123"},
    )

    assert out is existing
    assert existing.email == "from-clerk@example.com"
    assert existing.name == "From Clerk"
    assert session.committed == 1
    assert session.refreshed == [existing]


@pytest.mark.asyncio
async def test_get_or_sync_user_skips_commit_when_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = User(clerk_user_id="user_123", email="same@example.com", name="Name")

    async def _fake_get_or_create(*_args: Any, **_kwargs: Any) -> tuple[User, bool]:
        return existing, False

    async def _fake_fetch(_clerk_user_id: str) -> tuple[str | None, str | None]:
        return "same@example.com", "Different Name"

    monkeypatch.setattr(auth.crud, "get_or_create", _fake_get_or_create)
    monkeypatch.setattr(auth, "_fetch_clerk_profile", _fake_fetch)

    session = _FakeSession()
    out = await auth._get_or_sync_user(
        session,  # type: ignore[arg-type]
        clerk_user_id="user_123",
        claims={},
    )

    assert out is existing
    assert existing.email == "same@example.com"
    assert existing.name == "Name"
    assert session.committed == 0
    assert session.refreshed == []


@pytest.mark.asyncio
async def test_get_or_sync_user_allowlist_uses_clerk_profile_when_jwt_lacks_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: Clerk session JWTs typically only carry `sub`. The allowlist
    check must consult the Clerk profile API (not the JWT claims) before
    rejecting a new user, otherwise every Clerk-mode invitee with a sub-only
    token gets blocked even when their email is on the allowlist.
    Origin: 2026-05-02 — Samir (samir@wastegurus.ca) blocked despite being
    allowlisted because session JWT had no email claim.
    """
    new_user = User(clerk_user_id="user_abc", email=None, name=None)

    async def _fake_get_or_create(*_args: Any, **_kwargs: Any) -> tuple[User, bool]:
        return new_user, True  # newly created — triggers allowlist branch

    async def _fake_fetch(_clerk_user_id: str) -> tuple[str | None, str | None]:
        return "samir@wastegurus.ca", "Samir"

    monkeypatch.setattr(auth.crud, "get_or_create", _fake_get_or_create)
    monkeypatch.setattr(auth, "_fetch_clerk_profile", _fake_fetch)
    monkeypatch.setattr(
        auth.settings,
        "allowed_signup_emails",
        "samir@wastegurus.ca,henry@vantageclaw.ai",
    )

    session = _FakeSession()
    out = await auth._get_or_sync_user(
        session,  # type: ignore[arg-type]
        clerk_user_id="user_abc",
        claims={"sub": "user_abc"},  # JWT with only `sub` — no email claim
    )

    assert out is new_user
    assert new_user.email == "samir@wastegurus.ca"
    assert new_user.name == "Samir"
    assert session.deleted == []  # user was NOT rolled back


@pytest.mark.asyncio
async def test_get_or_sync_user_allowlist_blocks_when_clerk_profile_email_not_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allowlist still rejects when the resolved email (claim or profile) is
    not on the list. Confirms the fix doesn't accidentally open the gate."""
    new_user = User(clerk_user_id="user_xyz", email=None, name=None)

    async def _fake_get_or_create(*_args: Any, **_kwargs: Any) -> tuple[User, bool]:
        return new_user, True

    async def _fake_fetch(_clerk_user_id: str) -> tuple[str | None, str | None]:
        return "intruder@example.com", "Intruder"

    monkeypatch.setattr(auth.crud, "get_or_create", _fake_get_or_create)
    monkeypatch.setattr(auth, "_fetch_clerk_profile", _fake_fetch)
    monkeypatch.setattr(
        auth.settings,
        "allowed_signup_emails",
        "samir@wastegurus.ca,henry@vantageclaw.ai",
    )

    session = _FakeSession()

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await auth._get_or_sync_user(
            session,  # type: ignore[arg-type]
            clerk_user_id="user_xyz",
            claims={"sub": "user_xyz"},
        )

    assert exc_info.value.status_code == 403
    assert session.deleted == [new_user]  # user was rolled back
