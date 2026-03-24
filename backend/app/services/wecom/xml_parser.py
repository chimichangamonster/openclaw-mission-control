"""WeCom XML message parsing and building.

WeCom uses XML for all callback payloads — both inbound messages and
passive replies. This module handles parsing and building those payloads.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass(frozen=True)
class WeComMessage:
    """Parsed inbound WeCom message."""

    to_user: str
    from_user: str
    create_time: str
    msg_type: str
    content: str  # text content (empty for non-text)
    msg_id: str
    agent_id: str
    encrypt: str  # encrypted payload (when using encrypted mode)


def parse_inbound_message(xml_bytes: bytes) -> WeComMessage:
    """Parse an inbound WeCom XML message.

    Handles both plaintext and encrypted message formats.
    """
    root = ET.fromstring(xml_bytes)

    def _text(tag: str) -> str:
        el = root.find(tag)
        return (el.text or "") if el is not None else ""

    return WeComMessage(
        to_user=_text("ToUserName"),
        from_user=_text("FromUserName"),
        create_time=_text("CreateTime"),
        msg_type=_text("MsgType"),
        content=_text("Content"),
        msg_id=_text("MsgId"),
        agent_id=_text("AgentID"),
        encrypt=_text("Encrypt"),
    )


def build_reply_xml(
    *,
    to_user: str,
    from_user: str,
    content: str,
    encrypt: str = "",
    nonce: str = "",
    timestamp: str = "",
) -> str:
    """Build a WeCom XML reply.

    If encrypt is provided, builds an encrypted reply envelope.
    Otherwise builds a plaintext text reply.
    """
    if encrypt:
        # Encrypted reply envelope
        ts = timestamp or str(int(time.time()))
        return (
            "<xml>"
            f"<Encrypt><![CDATA[{encrypt}]]></Encrypt>"
            f"<MsgSignature><![CDATA[]]></MsgSignature>"
            f"<TimeStamp>{ts}</TimeStamp>"
            f"<Nonce><![CDATA[{nonce}]]></Nonce>"
            "</xml>"
        )

    # Plaintext text reply
    ts = timestamp or str(int(time.time()))
    return (
        "<xml>"
        f"<ToUserName><![CDATA[{to_user}]]></ToUserName>"
        f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
        f"<CreateTime>{ts}</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{content}]]></Content>"
        "</xml>"
    )


def build_encrypted_reply_xml(
    *,
    encrypt: str,
    signature: str,
    timestamp: str,
    nonce: str,
) -> str:
    """Build a signed encrypted reply envelope."""
    return (
        "<xml>"
        f"<Encrypt><![CDATA[{encrypt}]]></Encrypt>"
        f"<MsgSignature><![CDATA[{signature}]]></MsgSignature>"
        f"<TimeStamp>{timestamp}</TimeStamp>"
        f"<Nonce><![CDATA[{nonce}]]></Nonce>"
        "</xml>"
    )
