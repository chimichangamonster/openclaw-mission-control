# ruff: noqa: INP001
"""Tests for WeCom outbound message delivery — news cards, file send, wecom_send service."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

from app.models.wecom_connection import WeComConnection

# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


def _make_connection(**overrides) -> WeComConnection:
    defaults = {
        "id": uuid4(),
        "organization_id": uuid4(),
        "user_id": uuid4(),
        "corp_id": "wx_test_corp",
        "agent_id": "1000001",
        "callback_token": "test_token",
        "encoding_aes_key": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        "is_active": True,
        "label": "Test Connection",
    }
    defaults.update(overrides)
    return WeComConnection(**defaults)


# ---------------------------------------------------------------------------
# send_news_message tests
# ---------------------------------------------------------------------------


class TestSendNewsMessage:
    @pytest.mark.asyncio()
    async def test_sends_news_payload(self):
        """News message sends correct payload to WeCom API."""
        from app.services.wecom.reply import send_news_message

        conn = _make_connection()
        session = AsyncMock()

        with patch(
            "app.services.wecom.access_token.get_access_token", new_callable=AsyncMock
        ) as mock_token:
            mock_token.return_value = "test_access_token"
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}
                mock_client.post.return_value = mock_resp

                result = await send_news_message(
                    to_user="test_user",
                    title="Invoice #001",
                    description="Amount: $500.00",
                    url="https://example.com/download?token=abc",
                    connection=conn,
                    session=session,
                )

                assert result is True
                call_kwargs = mock_client.post.call_args
                payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
                assert payload["msgtype"] == "news"
                assert payload["touser"] == "test_user"
                assert payload["agentid"] == 1000001
                assert len(payload["news"]["articles"]) == 1
                article = payload["news"]["articles"][0]
                assert article["title"] == "Invoice #001"
                assert article["url"] == "https://example.com/download?token=abc"

    @pytest.mark.asyncio()
    async def test_includes_pic_url_when_provided(self):
        """News article includes picurl when provided."""
        from app.services.wecom.reply import send_news_message

        conn = _make_connection()
        session = AsyncMock()

        with patch(
            "app.services.wecom.access_token.get_access_token", new_callable=AsyncMock
        ) as mock_token:
            mock_token.return_value = "tok"
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"errcode": 0}
                mock_client.post.return_value = mock_resp

                await send_news_message(
                    to_user="u1",
                    title="Doc",
                    description="desc",
                    url="https://example.com",
                    pic_url="https://example.com/thumb.png",
                    connection=conn,
                    session=session,
                )

                payload = (
                    mock_client.post.call_args.kwargs.get("json")
                    or mock_client.post.call_args[1]["json"]
                )
                assert payload["news"]["articles"][0]["picurl"] == "https://example.com/thumb.png"

    @pytest.mark.asyncio()
    async def test_omits_pic_url_when_empty(self):
        """News article omits picurl when not provided."""
        from app.services.wecom.reply import send_news_message

        conn = _make_connection()
        session = AsyncMock()

        with patch(
            "app.services.wecom.access_token.get_access_token", new_callable=AsyncMock
        ) as mock_token:
            mock_token.return_value = "tok"
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"errcode": 0}
                mock_client.post.return_value = mock_resp

                await send_news_message(
                    to_user="u1",
                    title="T",
                    description="D",
                    url="https://example.com",
                    connection=conn,
                    session=session,
                )

                payload = (
                    mock_client.post.call_args.kwargs.get("json")
                    or mock_client.post.call_args[1]["json"]
                )
                assert "picurl" not in payload["news"]["articles"][0]

    @pytest.mark.asyncio()
    async def test_returns_false_on_api_error(self):
        """Returns False when WeCom API returns errcode != 0."""
        from app.services.wecom.reply import send_news_message

        conn = _make_connection()
        session = AsyncMock()

        with patch(
            "app.services.wecom.access_token.get_access_token", new_callable=AsyncMock
        ) as mock_token:
            mock_token.return_value = "tok"
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"errcode": 40001, "errmsg": "invalid credential"}
                mock_client.post.return_value = mock_resp

                result = await send_news_message(
                    to_user="u1",
                    title="T",
                    description="D",
                    url="https://example.com",
                    connection=conn,
                    session=session,
                )
                assert result is False

    @pytest.mark.asyncio()
    async def test_returns_false_on_token_error(self):
        """Returns False when access token retrieval fails."""
        from app.services.wecom.access_token import WeComTokenError
        from app.services.wecom.reply import send_news_message

        conn = _make_connection()
        session = AsyncMock()

        with patch(
            "app.services.wecom.access_token.get_access_token", new_callable=AsyncMock
        ) as mock_token:
            mock_token.side_effect = WeComTokenError("Token expired")
            result = await send_news_message(
                to_user="u1",
                title="T",
                description="D",
                url="https://example.com",
                connection=conn,
                session=session,
            )
            assert result is False


# ---------------------------------------------------------------------------
# send_file_message tests
# ---------------------------------------------------------------------------


class TestSendFileMessage:
    @pytest.mark.asyncio()
    async def test_uploads_then_sends(self):
        """File message: uploads to media library, then sends with media_id."""
        from app.services.wecom.reply import send_file_message

        conn = _make_connection()
        session = AsyncMock()

        with patch(
            "app.services.wecom.access_token.get_access_token", new_callable=AsyncMock
        ) as mock_token:
            mock_token.return_value = "tok"
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                # First call: upload → media_id
                upload_resp = MagicMock()
                upload_resp.json.return_value = {"errcode": 0, "media_id": "MEDIA_123"}
                # Second call: send → success
                send_resp = MagicMock()
                send_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}
                mock_client.post.side_effect = [upload_resp, send_resp]

                result = await send_file_message(
                    to_user="u1",
                    file_bytes=b"PDF content",
                    filename="invoice.pdf",
                    connection=conn,
                    session=session,
                )

                assert result is True
                assert mock_client.post.call_count == 2

                # Verify upload call
                upload_call = mock_client.post.call_args_list[0]
                assert "media/upload" in str(upload_call)

                # Verify send call
                send_call = mock_client.post.call_args_list[1]
                send_payload = send_call.kwargs.get("json") or send_call[1].get("json")
                assert send_payload["msgtype"] == "file"
                assert send_payload["file"]["media_id"] == "MEDIA_123"

    @pytest.mark.asyncio()
    async def test_returns_false_on_upload_error(self):
        """Returns False when media upload fails."""
        from app.services.wecom.reply import send_file_message

        conn = _make_connection()
        session = AsyncMock()

        with patch(
            "app.services.wecom.access_token.get_access_token", new_callable=AsyncMock
        ) as mock_token:
            mock_token.return_value = "tok"
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                upload_resp = MagicMock()
                upload_resp.json.return_value = {"errcode": 40004, "errmsg": "invalid media type"}
                mock_client.post.return_value = upload_resp

                result = await send_file_message(
                    to_user="u1",
                    file_bytes=b"data",
                    filename="f.pdf",
                    connection=conn,
                    session=session,
                )
                assert result is False


# ---------------------------------------------------------------------------
# wecom_send service tests
# ---------------------------------------------------------------------------


class TestWeComSendService:
    @pytest.mark.asyncio()
    async def test_get_org_wecom_connection_returns_active(self, db_session):
        """Returns the active WeCom connection for the org."""
        from app.services.wecom_send import get_org_wecom_connection

        org_id = uuid4()
        conn = _make_connection(organization_id=org_id, is_active=True)
        db_session.add(conn)
        await db_session.flush()

        result = await get_org_wecom_connection(db_session, org_id)
        assert result.id == conn.id

    @pytest.mark.asyncio()
    async def test_get_org_wecom_connection_skips_inactive(self, db_session):
        """Skips inactive WeCom connections."""
        from app.services.wecom_send import NoWeComConnectionError, get_org_wecom_connection

        org_id = uuid4()
        conn = _make_connection(organization_id=org_id, is_active=False)
        db_session.add(conn)
        await db_session.flush()

        with pytest.raises(NoWeComConnectionError):
            await get_org_wecom_connection(db_session, org_id)

    @pytest.mark.asyncio()
    async def test_get_org_wecom_connection_no_connections(self, db_session):
        """Raises when no WeCom connections exist."""
        from app.services.wecom_send import NoWeComConnectionError, get_org_wecom_connection

        with pytest.raises(NoWeComConnectionError):
            await get_org_wecom_connection(db_session, uuid4())


# ---------------------------------------------------------------------------
# Invoice delivery mode tests
# ---------------------------------------------------------------------------


class TestInvoiceDeliveryMode:
    def test_invoice_send_request_defaults_to_email(self):
        """InvoiceSendRequest defaults to email delivery."""
        from app.api.bookkeeping.invoices import InvoiceSendRequest

        req = InvoiceSendRequest()
        assert req.delivery == "email"
        assert req.wecom_user_id is None

    def test_invoice_send_request_wecom_mode(self):
        """InvoiceSendRequest accepts wecom delivery with user_id."""
        from app.api.bookkeeping.invoices import InvoiceSendRequest

        req = InvoiceSendRequest(delivery="wecom", wecom_user_id="user123")
        assert req.delivery == "wecom"
        assert req.wecom_user_id == "user123"

    def test_invoice_send_request_both_mode(self):
        """InvoiceSendRequest accepts both delivery channels."""
        from app.api.bookkeeping.invoices import InvoiceSendRequest

        req = InvoiceSendRequest(delivery="both", wecom_user_id="user123")
        assert req.delivery == "both"
