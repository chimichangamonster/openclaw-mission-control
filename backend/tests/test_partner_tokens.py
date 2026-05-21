# ruff: noqa: INP001
"""Unit tests for partner API token helpers and scope vocabulary.

Covers `app/core/partner_tokens.py`. No DB; pure helpers.
"""

from __future__ import annotations

import pytest

from app.core import partner_tokens
from app.core.partner_tokens import (
    PREFIX,
    REAL_SCOPES,
    RESERVED_SCOPES,
    ReservedScopeError,
    UnknownScopeError,
    generate_partner_token,
    hash_partner_secret,
    parse_partner_token,
    validate_scopes,
    verify_partner_secret,
)


# === Token generation =====================================================


def test_generate_partner_token_returns_three_values() -> None:
    full, key_id, secret = generate_partner_token()
    assert full.startswith(PREFIX)
    assert key_id
    assert secret
    assert full == f"{PREFIX}{key_id}.{secret}"


def test_generated_tokens_are_unique() -> None:
    """Each call returns a fresh token. 50 iterations is overkill but cheap."""
    seen: set[str] = set()
    for _ in range(50):
        full, key_id, secret = generate_partner_token()
        assert full not in seen
        seen.add(full)


def test_generate_partner_token_has_sufficient_entropy() -> None:
    """key_id is ~32 url-safe chars (24 bytes); secret ~43 chars (32 bytes)."""
    _, key_id, secret = generate_partner_token()
    # token_urlsafe base64-encodes to ceil(bytes * 4/3) chars, no padding
    assert len(key_id) >= 30, f"key_id too short: {key_id!r}"
    assert len(secret) >= 40, f"secret too short: {secret!r}"


# === Token parsing ========================================================


def test_parse_partner_token_round_trip() -> None:
    full, key_id, secret = generate_partner_token()
    parsed = parse_partner_token(full)
    assert parsed is not None
    parsed_key_id, parsed_secret = parsed
    assert parsed_key_id == key_id
    assert parsed_secret == secret


@pytest.mark.parametrize(
    "bad_token",
    [
        "",  # empty
        "not-a-token",
        "Bearer foo",
        "pak_legacy.token",  # wrong prefix (old scope doc used pak_)
        "vck_nodotinbody",  # missing . separator in body
        "vck_",  # prefix only
        "vck_.no_kid",  # empty key_id (nothing before separator)
        "vck_kid.",  # empty secret (nothing after separator)
        "VCK_uppercase.secret",  # case-sensitive prefix
        # The old wire format using ``_`` as separator must NOT parse,
        # so legacy clients fail loudly instead of silently mis-parsing.
        "vck_keyid_secret",
    ],
)
def test_parse_partner_token_rejects_malformed(bad_token: str) -> None:
    assert parse_partner_token(bad_token) is None


def test_parse_partner_token_round_trip_robust_to_special_chars() -> None:
    """Regression guard: ``secrets.token_urlsafe`` emits ``_`` and ``-``.

    If the wire-format separator were ``_``, ~45% of generated tokens would
    fail the round-trip because ``key_id`` can naturally contain ``_``.
    This bug was caught during Step 2 partner-auth tests (session #68).
    Run 100 iterations to make any future regression statistically certain
    to trip the test.
    """
    for _ in range(100):
        full, key_id, secret = generate_partner_token()
        parsed = parse_partner_token(full)
        assert parsed is not None, f"failed to parse: {full!r}"
        parsed_kid, parsed_sec = parsed
        assert parsed_kid == key_id, (
            f"key_id round-trip failed: gen={key_id!r} parsed={parsed_kid!r}"
        )
        assert parsed_sec == secret, (
            f"secret round-trip failed: gen={secret[:8]!r}... parsed={parsed_sec[:8]!r}..."
        )


# === Hashing + verification ==============================================


def test_hash_partner_secret_format() -> None:
    """Stored hash uses pbkdf2_sha256$iter$salt$digest format."""
    hashed = hash_partner_secret("any-secret-string")
    parts = hashed.split("$")
    assert len(parts) == 4
    assert parts[0] == "pbkdf2_sha256"
    assert int(parts[1]) == partner_tokens.ITERATIONS
    assert parts[2]  # salt non-empty
    assert parts[3]  # digest non-empty


def test_hash_is_salted_each_call() -> None:
    """Same secret hashed twice produces different stored values (random salt)."""
    secret = "shared-secret"
    hash_a = hash_partner_secret(secret)
    hash_b = hash_partner_secret(secret)
    assert hash_a != hash_b


def test_verify_partner_secret_accepts_correct_secret() -> None:
    _, _, secret = generate_partner_token()
    hashed = hash_partner_secret(secret)
    assert verify_partner_secret(secret, hashed) is True


def test_verify_partner_secret_rejects_wrong_secret() -> None:
    _, _, secret = generate_partner_token()
    hashed = hash_partner_secret(secret)
    assert verify_partner_secret("not-the-real-secret", hashed) is False


@pytest.mark.parametrize(
    "garbage_hash",
    [
        "",
        "not-a-hash",
        "pbkdf2_sha256$200000$wrong-salt-format",  # not enough segments
        "bcrypt$12$saltvalue$digestvalue",  # wrong algorithm
        "pbkdf2_sha256$abc$salt$digest",  # iterations not int
    ],
)
def test_verify_partner_secret_rejects_garbage_hash(garbage_hash: str) -> None:
    assert verify_partner_secret("any-secret", garbage_hash) is False


# === Scope vocabulary ====================================================


def test_real_and_reserved_scopes_are_disjoint() -> None:
    """The module's assert guards this at import time; this test re-checks at runtime."""
    assert REAL_SCOPES.isdisjoint(RESERVED_SCOPES)


def test_validate_scopes_accepts_real_scopes() -> None:
    result = validate_scopes(["webhooks:manage", "identity:read"])
    assert result == ["identity:read", "webhooks:manage"]  # sorted, deduplicated


def test_validate_scopes_deduplicates() -> None:
    result = validate_scopes(
        ["webhooks:manage", "webhooks:manage", "identity:read"]
    )
    assert result == ["identity:read", "webhooks:manage"]


def test_validate_scopes_rejects_reserved_scope() -> None:
    """Reserved scopes (leads, intakes, records, skills, agents, tenants) raise ReservedScopeError."""
    with pytest.raises(ReservedScopeError) as exc_info:
        validate_scopes(["webhooks:manage", "leads:read"])
    assert exc_info.value.scope == "leads:read"


def test_validate_scopes_rejects_skill_authoring_scopes() -> None:
    """skills:* is reserved (deferred per project_skill_authoring_deferred.md)."""
    for scope in ("skills:read", "skills:author", "skills:execute"):
        with pytest.raises(ReservedScopeError) as exc_info:
            validate_scopes([scope])
        assert exc_info.value.scope == scope


def test_validate_scopes_rejects_unknown_scope() -> None:
    """Scopes outside the union of real + reserved raise UnknownScopeError."""
    with pytest.raises(UnknownScopeError) as exc_info:
        validate_scopes(["webhooks:manage", "made-up:scope"])
    assert exc_info.value.scope == "made-up:scope"


def test_validate_empty_scopes_list_is_allowed() -> None:
    """An empty scope list is a valid (if useless) key configuration."""
    assert validate_scopes([]) == []


def test_validate_scopes_error_message_mentions_v1() -> None:
    """ReservedScopeError message hints at the v1-vs-future framing."""
    with pytest.raises(ReservedScopeError) as exc_info:
        validate_scopes(["intakes:write"])
    assert "v1" in str(exc_info.value)
