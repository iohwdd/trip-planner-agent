from __future__ import annotations

import logging
from typing import Any

from django.core.cache import cache
from django.utils import timezone


logger = logging.getLogger("planner.analytics")


class EventStore:
    RECENT_EVENTS_KEY = "planner:analytics:recent"
    MAX_RECENT_EVENTS = 200
    TTL_SECONDS = 60 * 60 * 24

    def record(
        self,
        event_type: str,
        *,
        owner_id: str | None = None,
        guest_token: str | None = None,
        session_id: str = "",
        turn_id: str = "",
        plan_id: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = {
            "event_type": event_type,
            "owner_id": owner_id or "",
            "guest_token": guest_token or "",
            "session_id": session_id,
            "turn_id": turn_id,
            "plan_id": plan_id,
            "payload": payload or {},
            "created_at": timezone.now().isoformat(),
        }
        logger.info("planner_event", extra={"planner_event": event})

        recent_events = cache.get(self.RECENT_EVENTS_KEY, [])
        cache.set(
            self.RECENT_EVENTS_KEY,
            [event, *recent_events][: self.MAX_RECENT_EVENTS],
            self.TTL_SECONDS,
        )

    def list_recent(self, *, event_type: str | None = None) -> list[dict[str, Any]]:
        events = cache.get(self.RECENT_EVENTS_KEY, [])
        if not event_type:
            return list(events)
        return [event for event in events if event.get("event_type") == event_type]

    def latest(self, event_type: str) -> dict[str, Any] | None:
        events = self.list_recent(event_type=event_type)
        return events[0] if events else None


event_store = EventStore()
