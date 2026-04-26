"""Org-scope filter for the SSE /activity/live/stream endpoint.

Regression test for the cross-org event leak: the broadcast hub is global,
so without filtering every SSE subscriber would see every gateway event
(Org A could observe Org B activity in real time). Must ship before any
F&F or paying user joins a non-Vantage org.
"""

from __future__ import annotations

from app.api.activity import _should_deliver_event


def test_same_org_event_is_delivered() -> None:
    assert _should_deliver_event("org-a", "org-a") is True


def test_different_org_event_is_dropped() -> None:
    assert _should_deliver_event("org-a", "org-b") is False


def test_untagged_event_is_never_delivered() -> None:
    """Empty organization_id means we don't know the source — never leak."""
    assert _should_deliver_event("", "org-a") is False
    assert _should_deliver_event("", "") is False


def test_uuid_string_comparison() -> None:
    """Real org IDs are UUID strings; compare exact match."""
    org_a = "11111111-1111-1111-1111-111111111111"
    org_b = "22222222-2222-2222-2222-222222222222"
    assert _should_deliver_event(org_a, org_a) is True
    assert _should_deliver_event(org_a, org_b) is False
    assert _should_deliver_event(org_b, org_a) is False
