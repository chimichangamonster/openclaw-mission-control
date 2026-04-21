# ruff: noqa: INP001
"""Tests for personal bookkeeping classifier.

Regression: classifier rules must produce the same buckets the scratch
script did for the Q1 2026 calibration corpus.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.services.personal_bookkeeping.classifier import classify


class _StubScalars:
    def all(self) -> list:
        return []


class _StubResult:
    def scalars(self) -> _StubScalars:
        return _StubScalars()


@pytest.fixture
def empty_session() -> AsyncMock:
    """Session that returns zero PersonalVendorRule rows — forces seed rules."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_StubResult())
    return session


ORG_ID: UUID = uuid4()


# --- Transfers (highest priority) ---


@pytest.mark.asyncio
async def test_amex_cards_is_transfer(empty_session: AsyncMock) -> None:
    c = await classify(
        "AMEX CARDS   X9K7W7", incoming=False, source="TD",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "transfer"


@pytest.mark.asyncio
async def test_rbc_mc_is_transfer(empty_session: AsyncMock) -> None:
    c = await classify(
        "RBC MC       X9K7X2", incoming=False, source="TD",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "transfer"


@pytest.mark.asyncio
async def test_amex_payment_received_is_transfer(empty_session: AsyncMock) -> None:
    c = await classify(
        "PAYMENT RECEIVED - THANK YOU", incoming=True, source="AMEX",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "transfer"


# --- Incoming (always flagged for review) ---


@pytest.mark.asyncio
async def test_td_atm_dep_is_income_pending(empty_session: AsyncMock) -> None:
    c = await classify(
        "TD ATM DEP    007702", incoming=True, source="TD",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "income_pending"
    assert c.needs_receipt is True


@pytest.mark.asyncio
async def test_e_transfer_received_is_income_pending(empty_session: AsyncMock) -> None:
    c = await classify(
        "E-TRANSFER ***ehp", incoming=True, source="TD",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "income_pending"


# --- Business rules (SaaS stack) ---


@pytest.mark.asyncio
async def test_openrouter_is_business_mgmt_admin(empty_session: AsyncMock) -> None:
    c = await classify(
        "OPENROUTER, INC         NEW YORK", incoming=False, source="AMEX",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "business"
    assert c.t2125_line == "8871"
    assert c.category == "Mgmt/Admin"


@pytest.mark.asyncio
async def test_gallo_llp_is_legal_acct(empty_session: AsyncMock) -> None:
    c = await classify(
        "GALLO LLP               SHERWOOD PARK W", incoming=False, source="AMEX",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "business"
    assert c.t2125_line == "8860"


@pytest.mark.asyncio
async def test_squarespace_is_business(empty_session: AsyncMock) -> None:
    c = await classify(
        "SQSP* WEBSIT#225615382  NEW YORK", incoming=False, source="AMEX",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "business"
    assert c.t2125_line == "8871"


@pytest.mark.asyncio
async def test_dropbox_is_office(empty_session: AsyncMock) -> None:
    c = await classify(
        "DROPBOX*B14XRKYBVQYB    SAN FRANCISCO", incoming=False, source="AMEX",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "business"
    assert c.t2125_line == "8810"


@pytest.mark.asyncio
async def test_vercel_is_business(empty_session: AsyncMock) -> None:
    c = await classify(
        "VERCEL DOMAINS          COVINA", incoming=False, source="AMEX",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "business"


# --- Vehicle rules ---


@pytest.mark.asyncio
async def test_petro_canada_is_vehicle_fuel(empty_session: AsyncMock) -> None:
    c = await classify(
        "PETRO-CANADA 89494      EDMONTON", incoming=False, source="AMEX",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "vehicle"
    assert c.t2125_line == "9224"


@pytest.mark.asyncio
async def test_primmum_insurance_is_vehicle(empty_session: AsyncMock) -> None:
    c = await classify(
        "PRIMMUM INSURANCE COMP  MONTREAL", incoming=False, source="AMEX",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "vehicle"


@pytest.mark.asyncio
async def test_downtown_auto_is_vehicle(empty_session: AsyncMock) -> None:
    c = await classify(
        "DOWNTOWN AUTO & TIRE DE EDMONTON", incoming=False, source="AMEX",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "vehicle"


# --- TD default-personal rule ---


@pytest.mark.asyncio
async def test_td_unknown_vendor_is_personal(empty_session: AsyncMock) -> None:
    """Per Henz's rule: TD is out-of-pocket. Any TD debit not matching a
    business rule is personal — we don't flag unknown TD vendors for review.
    """
    c = await classify(
        "RANDOM RESTAURANT NAME", incoming=False, source="TD",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "personal"


@pytest.mark.asyncio
async def test_td_send_e_tfr_is_personal(empty_session: AsyncMock) -> None:
    """Per Henz's March decision: outgoing TD e-transfers are paying friends."""
    c = await classify(
        "SEND E-TFR ***9hq", incoming=False, source="TD",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "personal"


# --- AMEX ambiguous-explicit patterns ---


@pytest.mark.asyncio
async def test_ups_on_amex_is_ambiguous(empty_session: AsyncMock) -> None:
    c = await classify(
        "UPS*                    888-520-9090", incoming=False, source="AMEX",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "ambiguous"


@pytest.mark.asyncio
async def test_sandman_on_amex_is_ambiguous(empty_session: AsyncMock) -> None:
    """Hotels need per-instance decision — can't auto-tag business."""
    c = await classify(
        "SANDMAN CALGARY AIRPORT CALGARY", incoming=False, source="AMEX",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "ambiguous"


# --- AMEX personal hints ---


@pytest.mark.asyncio
async def test_uber_eats_is_personal(empty_session: AsyncMock) -> None:
    c = await classify(
        "UBER EATS               TORONTO", incoming=False, source="AMEX",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "personal"


@pytest.mark.asyncio
async def test_spotify_is_personal(empty_session: AsyncMock) -> None:
    c = await classify(
        "SPOTIFY                 STOCKHOLM", incoming=False, source="AMEX",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "personal"


# --- AMEX fallback → ambiguous ---


@pytest.mark.asyncio
async def test_amex_unknown_vendor_is_ambiguous(empty_session: AsyncMock) -> None:
    """Per Henz's rule: AMEX is business-leaning, so unknown AMEX charges
    must be surfaced for review (not auto-personal like TD)."""
    c = await classify(
        "WIDGET CORP  VANCOUVER", incoming=False, source="AMEX",
        organization_id=ORG_ID, session=empty_session,
    )
    assert c.bucket == "ambiguous"
