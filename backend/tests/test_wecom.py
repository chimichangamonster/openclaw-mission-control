# ruff: noqa: INP001
"""Tests for WeCom (Enterprise WeChat) integration — crypto, XML, model, CRUD, callback."""

from __future__ import annotations

import hashlib
import json
import time
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.services.wecom.crypto import (
    WeComCryptoError,
    check_timestamp,
    decrypt_message,
    encrypt_message,
    verify_signature,
)
from app.services.wecom.xml_parser import (
    build_encrypted_reply_xml,
    build_reply_xml,
    parse_inbound_message,
)

# Test constants
_TEST_AES_KEY = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
_TEST_CORP_ID = "wx12345678"
_TEST_TOKEN = "test_token_123"


# ---------------------------------------------------------------------------
# Crypto tests (pure unit, no DB)
# ---------------------------------------------------------------------------


class TestVerifySignature:
    def test_valid_signature(self) -> None:
        timestamp = "1234567890"
        nonce = "abc"
        msg_encrypt = "encrypted_data"
        parts = sorted([_TEST_TOKEN, timestamp, nonce, msg_encrypt])
        expected = hashlib.sha1("".join(parts).encode()).hexdigest()
        verify_signature(
            _TEST_TOKEN,
            timestamp,
            nonce,
            msg_encrypt=msg_encrypt,
            signature=expected,
        )

    def test_invalid_signature_raises(self) -> None:
        with pytest.raises(WeComCryptoError, match="Signature verification failed"):
            verify_signature(
                _TEST_TOKEN,
                "1234567890",
                "abc",
                msg_encrypt="data",
                signature="bad",
            )

    def test_empty_msg_encrypt(self) -> None:
        timestamp = "1234567890"
        nonce = "abc"
        parts = sorted([_TEST_TOKEN, timestamp, nonce, ""])
        expected = hashlib.sha1("".join(parts).encode()).hexdigest()
        verify_signature(
            _TEST_TOKEN,
            timestamp,
            nonce,
            msg_encrypt="",
            signature=expected,
        )


class TestCheckTimestamp:
    def test_current_passes(self) -> None:
        check_timestamp(str(int(time.time())))

    def test_old_raises(self) -> None:
        with pytest.raises(WeComCryptoError, match="Timestamp too old"):
            check_timestamp(str(int(time.time()) - 600), max_age_seconds=300)

    def test_invalid_raises(self) -> None:
        with pytest.raises(WeComCryptoError, match="Invalid timestamp"):
            check_timestamp("not_a_number")


class TestEncryptDecrypt:
    def test_roundtrip(self) -> None:
        original = "Hello, 你好世界! Test message."
        encrypted = encrypt_message(_TEST_AES_KEY, _TEST_CORP_ID, original)
        assert decrypt_message(_TEST_AES_KEY, encrypted, _TEST_CORP_ID) == original

    def test_unicode_roundtrip(self) -> None:
        original = "WeChat消息 🎉 日本語テスト"
        encrypted = encrypt_message(_TEST_AES_KEY, _TEST_CORP_ID, original)
        assert decrypt_message(_TEST_AES_KEY, encrypted, _TEST_CORP_ID) == original

    def test_wrong_corp_id_raises(self) -> None:
        encrypted = encrypt_message(_TEST_AES_KEY, _TEST_CORP_ID, "test")
        with pytest.raises(WeComCryptoError, match="Corp ID mismatch"):
            decrypt_message(_TEST_AES_KEY, encrypted, "wrong_corp")

    def test_wrong_key_raises(self) -> None:
        encrypted = encrypt_message(_TEST_AES_KEY, _TEST_CORP_ID, "test")
        wrong = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefg"
        with pytest.raises(Exception):
            decrypt_message(wrong, encrypted, _TEST_CORP_ID)

    def test_empty_message(self) -> None:
        encrypted = encrypt_message(_TEST_AES_KEY, _TEST_CORP_ID, "")
        assert decrypt_message(_TEST_AES_KEY, encrypted, _TEST_CORP_ID) == ""


# ---------------------------------------------------------------------------
# XML parser tests (pure unit)
# ---------------------------------------------------------------------------


class TestParseInbound:
    def test_text_message(self) -> None:
        xml = (
            b"<xml>"
            b"<ToUserName><![CDATA[corp123]]></ToUserName>"
            b"<FromUserName><![CDATA[user456]]></FromUserName>"
            b"<CreateTime>1609459200</CreateTime>"
            b"<MsgType><![CDATA[text]]></MsgType>"
            b"<Content><![CDATA[Hello World]]></Content>"
            b"<MsgId>12345</MsgId>"
            b"<AgentID>1000002</AgentID>"
            b"<Encrypt><![CDATA[]]></Encrypt>"
            b"</xml>"
        )
        msg = parse_inbound_message(xml)
        assert msg.to_user == "corp123"
        assert msg.from_user == "user456"
        assert msg.msg_type == "text"
        assert msg.content == "Hello World"
        assert msg.msg_id == "12345"
        assert msg.agent_id == "1000002"

    def test_encrypted_message(self) -> None:
        xml = (
            b"<xml>"
            b"<ToUserName><![CDATA[corp]]></ToUserName>"
            b"<Encrypt><![CDATA[enc_payload]]></Encrypt>"
            b"</xml>"
        )
        msg = parse_inbound_message(xml)
        assert msg.encrypt == "enc_payload"

    def test_non_text_type(self) -> None:
        xml = b"<xml>" b"<MsgType><![CDATA[image]]></MsgType>" b"<Content></Content>" b"</xml>"
        msg = parse_inbound_message(xml)
        assert msg.msg_type == "image"
        assert msg.content == ""


class TestBuildReply:
    def test_plaintext(self) -> None:
        xml = build_reply_xml(
            to_user="user",
            from_user="corp",
            content="Hi there",
            timestamp="1609459200",
        )
        assert "<Content><![CDATA[Hi there]]></Content>" in xml
        assert "<MsgType><![CDATA[text]]></MsgType>" in xml

    def test_encrypted(self) -> None:
        xml = build_encrypted_reply_xml(
            encrypt="enc",
            signature="sig",
            timestamp="1609459200",
            nonce="n1",
        )
        assert "<Encrypt><![CDATA[enc]]></Encrypt>" in xml
        assert "<MsgSignature><![CDATA[sig]]></MsgSignature>" in xml


# ---------------------------------------------------------------------------
# Model tests (unit)
# ---------------------------------------------------------------------------


class TestWeComConnectionModel:
    def test_defaults(self) -> None:
        from app.models.wecom_connection import WeComConnection

        conn = WeComConnection(
            organization_id=uuid4(),
            user_id=uuid4(),
            corp_id="wx_test",
        )
        assert conn.is_active is True
        assert conn.target_agent_id == "the-claw"
        assert conn.target_channel == "general"
        assert conn.corp_secret_encrypted is None
        assert conn.access_token_encrypted is None


# ---------------------------------------------------------------------------
# Feature flag test
# ---------------------------------------------------------------------------


class TestWeComFeatureFlag:
    def test_wechat_default_off(self) -> None:
        from app.models.organization_settings import DEFAULT_FEATURE_FLAGS

        assert "wechat" in DEFAULT_FEATURE_FLAGS
        assert DEFAULT_FEATURE_FLAGS["wechat"] is False


# ---------------------------------------------------------------------------
# CRUD endpoint tests (async, in-memory DB)
# ---------------------------------------------------------------------------

ORG_ID = uuid4()
USER_ID = uuid4()


from app.models.gateways import Gateway  # noqa: E402
from app.models.organization_members import OrganizationMember  # noqa: E402
from app.models.organization_settings import OrganizationSettings  # noqa: E402

# Import all models so SQLModel.metadata knows about the tables
from app.models.organizations import Organization  # noqa: E402
from app.models.users import User  # noqa: E402
from app.models.wecom_connection import WeComConnection  # noqa: E402
from app.services.organizations import OrganizationContext  # noqa: E402


async def _make_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


@pytest_asyncio.fixture
async def wecom_app(monkeypatch):
    """FastAPI test app with WeCom router and org context overrides."""
    # Ensure encryption key is available
    import app.core.encryption as enc_mod

    enc_mod.reset_cache()
    monkeypatch.setattr(
        "app.core.encryption.settings",
        type(
            "S",
            (),
            {"encryption_key": "test-wecom-encryption-key", "email_token_encryption_key": ""},
        )(),
    )

    engine = await _make_engine()
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Seed org + settings with wechat enabled
    async with session_maker() as session:
        org = Organization(id=ORG_ID, name="Test Org", slug="test-org")
        session.add(org)
        await session.flush()

        user = User(
            id=USER_ID, email="test@test.com", name="Test User", clerk_user_id="clerk_test_wecom"
        )
        session.add(user)
        await session.flush()

        org_settings = OrganizationSettings(
            organization_id=ORG_ID,
            feature_flags_json=json.dumps(
                {
                    "wechat": True,
                    "paper_trading": True,
                }
            ),
        )
        session.add(org_settings)
        await session.commit()

    async def override_session():
        async with session_maker() as session:
            yield session

    member = OrganizationMember(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=USER_ID,
        role="owner",
    )
    org_ctx = OrganizationContext(organization=org, member=member)

    from fastapi import APIRouter, FastAPI

    from app.api.deps import check_org_rate_limit, get_session, require_org_member
    from app.api.wecom import router as wecom_router

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app = FastAPI(lifespan=noop_lifespan)
    api = APIRouter(prefix="/api/v1")
    api.include_router(wecom_router)
    app.include_router(api)

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_org_member] = lambda: org_ctx
    app.dependency_overrides[check_org_rate_limit] = lambda: None

    yield app


@pytest.mark.asyncio
async def test_create_connection(wecom_app):
    async with AsyncClient(transport=ASGITransport(app=wecom_app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/wecom/connections",
            json={
                "corp_id": "wx_test_corp",
                "callback_token": "tok123",
                "encoding_aes_key": _TEST_AES_KEY,
                "corp_secret": "secret123",
                "label": "Test WeCom",
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["corp_id"] == "wx_test_corp"
    assert data["has_corp_secret"] is True
    assert data["label"] == "Test WeCom"
    assert data["is_active"] is True
    assert "/callback" in data["callback_url"]


@pytest.mark.asyncio
async def test_list_connections(wecom_app):
    async with AsyncClient(transport=ASGITransport(app=wecom_app), base_url="http://test") as c:
        await c.post(
            "/api/v1/wecom/connections",
            json={
                "corp_id": "wx_list_test",
                "callback_token": "tok",
                "encoding_aes_key": _TEST_AES_KEY,
            },
        )
        resp = await c.get("/api/v1/wecom/connections")
    assert resp.status_code == 200
    conns = resp.json()
    assert len(conns) >= 1
    assert any(c["corp_id"] == "wx_list_test" for c in conns)


@pytest.mark.asyncio
async def test_update_connection(wecom_app):
    async with AsyncClient(transport=ASGITransport(app=wecom_app), base_url="http://test") as c:
        create = await c.post(
            "/api/v1/wecom/connections",
            json={
                "corp_id": "wx_upd",
                "callback_token": "tok",
                "encoding_aes_key": _TEST_AES_KEY,
            },
        )
        conn_id = create.json()["id"]
        resp = await c.patch(
            f"/api/v1/wecom/connections/{conn_id}",
            json={"label": "Updated", "target_agent_id": "stock-analyst"},
        )
    assert resp.status_code == 200
    assert resp.json()["label"] == "Updated"
    assert resp.json()["target_agent_id"] == "stock-analyst"


@pytest.mark.asyncio
async def test_delete_connection(wecom_app):
    async with AsyncClient(transport=ASGITransport(app=wecom_app), base_url="http://test") as c:
        create = await c.post(
            "/api/v1/wecom/connections",
            json={
                "corp_id": "wx_del",
                "callback_token": "tok",
                "encoding_aes_key": _TEST_AES_KEY,
            },
        )
        conn_id = create.json()["id"]
        resp = await c.delete(f"/api/v1/wecom/connections/{conn_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_callback_unknown_org_404(wecom_app):
    async with AsyncClient(transport=ASGITransport(app=wecom_app), base_url="http://test") as c:
        resp = await c.get(
            "/api/v1/wecom/nonexistent-org/callback",
            params={
                "msg_signature": "fake",
                "timestamp": str(int(time.time())),
                "nonce": "n",
                "echostr": "e",
            },
        )
    assert resp.status_code == 404
