"""Repository for calendar event and reminder persistence."""

import json
import re

from db import iso_to_score
from data_access.interface import DataStore
from data_access.redis_store import get_redis_store

# ---------------------------------------------------------------------------
# Redis key templates
# ---------------------------------------------------------------------------

_EVENT_KEY   = "buddy:event:{id}"
_EVENTS_IDX  = "buddy:events"           # sorted set, score = start_at unix ts
_EVENT_DEDUP = "buddy:event:dedup:{k}"  # value = event_id  (title+start_at dedup)
_EVENT_EXTID = "buddy:event:extid:{k}"  # value = event_id  (macOS external_id dedup)

_REM_KEY   = "buddy:reminder:{id}"
_REMS_IDX  = "buddy:reminders"          # sorted set, score = end_at unix ts
_REM_DEDUP = "buddy:reminder:dedup:{k}" # value = reminder_id (title+end_at dedup)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-") or "event"


class CalendarRepository:
    def __init__(self, store: DataStore) -> None:
        self._s = store

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def unique_event_id(self, title: str) -> str:
        """Return a unique slug-based ID for the given event title."""
        base = _slugify(title)
        if not self.event_exists(base):
            return base
        index = 2
        while True:
            candidate = f"{base}-{index}"
            if not self.event_exists(candidate):
                return candidate
            index += 1

    def event_exists(self, event_id: str) -> bool:
        return self._s.exists(_EVENT_KEY.format(id=event_id))

    def get_event(self, event_id: str) -> dict | None:
        raw = self._s.get(_EVENT_KEY.format(id=event_id))
        return json.loads(raw) if raw else None

    def save_event(self, data: dict) -> None:
        """Persist an event and update the sorted index (score = start_at)."""
        self._s.set(_EVENT_KEY.format(id=data["id"]), json.dumps(data))
        self._s.add_object(_EVENTS_IDX, {data["id"]: iso_to_score(data["start_at"])})

    def delete_event(self, event_id: str) -> None:
        """Delete an event and all associated dedup/extid keys."""
        raw = self._s.get(_EVENT_KEY.format(id=event_id))
        if not raw:
            return
        ev = json.loads(raw)
        self._s.delete(_EVENT_KEY.format(id=event_id))
        self._s.delete_object(_EVENTS_IDX, event_id)
        self._s.delete(_EVENT_DEDUP.format(k=f"{ev['title']}\x00{ev['start_at']}"))
        if ev.get("external_id"):
            self._s.delete(_EVENT_EXTID.format(k=ev["external_id"]))

    def list_event_ids(self) -> list[str]:
        return self._s.get_objects(_EVENTS_IDX, 0, -1)

    def get_event_dedup(self, title: str, start_at: str) -> str | None:
        return self._s.get(_EVENT_DEDUP.format(k=f"{title}\x00{start_at}"))

    def set_event_dedup(self, title: str, start_at: str, event_id: str) -> None:
        self._s.set(_EVENT_DEDUP.format(k=f"{title}\x00{start_at}"), event_id)

    def event_extid_exists(self, external_id: str) -> bool:
        return self._s.exists(_EVENT_EXTID.format(k=external_id))

    def event_dedup_exists(self, title: str, start_at: str) -> bool:
        return self._s.exists(_EVENT_DEDUP.format(k=f"{title}\x00{start_at}"))

    def set_event_extid(self, external_id: str, event_id: str) -> None:
        self._s.set(_EVENT_EXTID.format(k=external_id), event_id)

    # ------------------------------------------------------------------
    # Reminders
    # ------------------------------------------------------------------

    def unique_reminder_id(self, title: str) -> str:
        """Return a unique slug-based ID for the given reminder title."""
        base = _slugify(title)
        if not self.reminder_exists(base):
            return base
        index = 2
        while True:
            candidate = f"{base}-{index}"
            if not self.reminder_exists(candidate):
                return candidate
            index += 1

    def reminder_exists(self, reminder_id: str) -> bool:
        return self._s.exists(_REM_KEY.format(id=reminder_id))

    def get_reminder(self, reminder_id: str) -> dict | None:
        raw = self._s.get(_REM_KEY.format(id=reminder_id))
        return json.loads(raw) if raw else None

    def save_reminder(self, data: dict) -> None:
        """Persist a reminder and update the sorted index (score = end_at)."""
        self._s.set(_REM_KEY.format(id=data["id"]), json.dumps(data))
        self._s.add_object(_REMS_IDX, {data["id"]: iso_to_score(data["end_at"])})

    def delete_reminder(self, reminder_id: str) -> None:
        """Delete a reminder and its dedup key."""
        raw = self._s.get(_REM_KEY.format(id=reminder_id))
        if not raw:
            return
        rem = json.loads(raw)
        self._s.delete(_REM_KEY.format(id=reminder_id))
        self._s.delete_object(_REMS_IDX, reminder_id)
        self._s.delete(_REM_DEDUP.format(k=f"{rem['title']}\x00{rem['end_at']}"))

    def list_reminder_ids(self, start: int = 0, stop: int = -1) -> list[str]:
        return self._s.get_objects(_REMS_IDX, start, stop)

    def get_reminder_dedup(self, title: str, end_at: str) -> str | None:
        return self._s.get(_REM_DEDUP.format(k=f"{title}\x00{end_at}"))

    def set_reminder_dedup(self, title: str, end_at: str, reminder_id: str) -> None:
        self._s.set(_REM_DEDUP.format(k=f"{title}\x00{end_at}"), reminder_id)


def get_calendar_repository() -> CalendarRepository:
    return CalendarRepository(get_redis_store())
