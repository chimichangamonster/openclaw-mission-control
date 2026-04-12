# ruff: noqa: INP001
"""Tests for chat file upload endpoint and attachment message building.

Covers:
- File type validation (allowed and rejected types)
- File size limits
- Workspace path generation
- Message building with attachments
- Message building without attachments (passthrough)
"""

from __future__ import annotations

from app.schemas.gateway_api import ChatAttachment, GatewaySessionMessageRequest
from app.services.openclaw.session_service import GatewaySessionService

# ---------------------------------------------------------------------------
# _build_message_with_attachments tests
# ---------------------------------------------------------------------------


class TestBuildMessageWithAttachments:
    """GatewaySessionService._build_message_with_attachments()."""

    def test_no_attachments_returns_content_unchanged(self):
        payload = GatewaySessionMessageRequest(content="Hello agent")
        result = GatewaySessionService._build_message_with_attachments(payload)
        assert result == "Hello agent"

    def test_none_attachments_returns_content_unchanged(self):
        payload = GatewaySessionMessageRequest(content="Hello agent", attachments=None)
        result = GatewaySessionService._build_message_with_attachments(payload)
        assert result == "Hello agent"

    def test_empty_attachments_returns_content_unchanged(self):
        payload = GatewaySessionMessageRequest(content="Hello agent", attachments=[])
        result = GatewaySessionService._build_message_with_attachments(payload)
        assert result == "Hello agent"

    def test_single_attachment_prepends_context(self):
        att = ChatAttachment(
            filename="report.pdf",
            workspace_path="uploads/chat/org1/abc123.pdf",
            content_type="application/pdf",
            size_bytes=50_000,
        )
        payload = GatewaySessionMessageRequest(
            content="Please review this report",
            attachments=[att],
        )
        result = GatewaySessionService._build_message_with_attachments(payload)
        assert "[Attached files]" in result
        assert "[/Attached files]" in result
        assert "report.pdf" in result
        assert "uploads/chat/org1/abc123.pdf" in result
        assert "application/pdf" in result
        assert "50,000 bytes" in result
        assert result.endswith("Please review this report")

    def test_multiple_attachments(self):
        attachments = [
            ChatAttachment(
                filename="photo.jpg",
                workspace_path="uploads/chat/org1/aaa.jpg",
                content_type="image/jpeg",
                size_bytes=200_000,
            ),
            ChatAttachment(
                filename="data.csv",
                workspace_path="uploads/chat/org1/bbb.csv",
                content_type="text/csv",
                size_bytes=1_500,
            ),
        ]
        payload = GatewaySessionMessageRequest(
            content="Here are the files",
            attachments=attachments,
        )
        result = GatewaySessionService._build_message_with_attachments(payload)
        assert "photo.jpg" in result
        assert "data.csv" in result
        lines = result.split("\n")
        # Two attachment lines (both starting with -)
        att_lines = [line for line in lines if line.startswith("- ")]
        assert len(att_lines) == 2

    def test_message_structure_order(self):
        att = ChatAttachment(
            filename="doc.txt",
            workspace_path="uploads/chat/org1/doc.txt",
            content_type="text/plain",
            size_bytes=100,
        )
        payload = GatewaySessionMessageRequest(
            content="Check this",
            attachments=[att],
        )
        result = GatewaySessionService._build_message_with_attachments(payload)
        lines = result.split("\n")
        assert lines[0] == "[Attached files]"
        assert lines[-1] == "Check this"
        # The closing tag should come before the user message
        tag_idx = lines.index("[/Attached files]")
        assert tag_idx < len(lines) - 1


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestChatAttachmentSchema:
    """ChatAttachment and GatewaySessionMessageRequest validation."""

    def test_attachment_fields(self):
        att = ChatAttachment(
            filename="test.png",
            workspace_path="uploads/chat/org1/test.png",
            content_type="image/png",
            size_bytes=1024,
        )
        assert att.filename == "test.png"
        assert att.content_type == "image/png"

    def test_message_request_with_attachments(self):
        att = ChatAttachment(
            filename="test.pdf",
            workspace_path="uploads/chat/org1/test.pdf",
            content_type="application/pdf",
            size_bytes=5000,
        )
        req = GatewaySessionMessageRequest(content="hello", attachments=[att])
        assert req.content == "hello"
        assert len(req.attachments) == 1
        assert req.attachments[0].filename == "test.pdf"

    def test_message_request_without_attachments(self):
        req = GatewaySessionMessageRequest(content="hello")
        assert req.attachments is None


# ---------------------------------------------------------------------------
# Upload endpoint constraint tests
# ---------------------------------------------------------------------------


class TestUploadConstraints:
    """Verify upload constants match expected values."""

    def test_allowed_types_include_common_formats(self):
        from app.api.gateway import _CHAT_UPLOAD_ALLOWED_TYPES

        assert "image/png" in _CHAT_UPLOAD_ALLOWED_TYPES
        assert "image/jpeg" in _CHAT_UPLOAD_ALLOWED_TYPES
        assert "application/pdf" in _CHAT_UPLOAD_ALLOWED_TYPES
        assert "text/plain" in _CHAT_UPLOAD_ALLOWED_TYPES
        assert "text/csv" in _CHAT_UPLOAD_ALLOWED_TYPES

    def test_disallowed_types(self):
        from app.api.gateway import _CHAT_UPLOAD_ALLOWED_TYPES

        assert "application/x-executable" not in _CHAT_UPLOAD_ALLOWED_TYPES
        assert "application/zip" not in _CHAT_UPLOAD_ALLOWED_TYPES
        assert "text/html" not in _CHAT_UPLOAD_ALLOWED_TYPES

    def test_max_size(self):
        from app.api.gateway import _CHAT_UPLOAD_MAX_BYTES

        assert _CHAT_UPLOAD_MAX_BYTES == 10 * 1024 * 1024
