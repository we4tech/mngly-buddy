"""Repository for note persistence."""

import json
import re

from db import iso_to_score
from data_access.interface import DataStore
from data_access.redis_store import get_redis_store

_NOTE_KEY = "buddy:note:{id}"
_NOTES_IDX = "buddy:notes"  # sorted set, score = created_at unix ts


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-") or "note"


class NoteRepository:
    def __init__(self, store: DataStore) -> None:
        self._s = store

    def unique_id(self, title: str) -> str:
        """Return a unique slug-based ID for the given title."""
        base = _slugify(title)
        if not self.exists(base):
            return base
        index = 2
        while True:
            candidate = f"{base}-{index}"
            if not self.exists(candidate):
                return candidate
            index += 1

    def exists(self, note_id: str) -> bool:
        return self._s.exists(_NOTE_KEY.format(id=note_id))

    def get(self, note_id: str) -> dict | None:
        raw = self._s.get(_NOTE_KEY.format(id=note_id))
        return json.loads(raw) if raw else None

    def save(self, data: dict) -> None:
        """Persist a note and update the sorted index (score = created_at)."""
        self._s.set(_NOTE_KEY.format(id=data["id"]), json.dumps(data))
        self._s.add_object(_NOTES_IDX, {data["id"]: iso_to_score(data["created_at"])})

    def delete(self, note_id: str) -> None:
        self._s.delete(_NOTE_KEY.format(id=note_id))
        self._s.delete_object(_NOTES_IDX, note_id)

    def list_ids(self, start: int = 0, stop: int = -1) -> list[str]:
        return self._s.get_objects(_NOTES_IDX, start, stop)


def get_note_repository() -> NoteRepository:
    return NoteRepository(get_redis_store())
