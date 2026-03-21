"""In-memory asyncio pub/sub for real-time activity events.

Subscribers (SSE endpoints) get an asyncio.Queue that receives events
published by the gateway event listener.  Queues are bounded; slow
consumers silently drop the oldest events.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass
class LiveActivityEvent:
    """A normalised activity event for the real-time feed."""

    id: str = field(default_factory=lambda: uuid4().hex[:12])
    event_type: str = ""
    agent_name: str = ""
    channel: str = ""
    message: str = ""
    model: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "agent_name": self.agent_name,
            "channel": self.channel,
            "message": self.message,
            "model": self.model,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


MAX_QUEUE_SIZE = 100


class EventBroadcast:
    """Broadcast hub: one publisher, many subscribers."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[LiveActivityEvent]] = set()

    def subscribe(self) -> asyncio.Queue[LiveActivityEvent]:
        q: asyncio.Queue[LiveActivityEvent] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[LiveActivityEvent]) -> None:
        self._subscribers.discard(q)

    def publish(self, event: LiveActivityEvent) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest and retry so slow consumers don't block.
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Module-level singleton — imported by SSE endpoint and listener.
broadcast = EventBroadcast()
