"""Repository for song persistence."""

import json
import re

from db import iso_to_score
from data_access.interface import DataStore
from data_access.redis_store import get_redis_store

_SONG_KEY = "buddy:song:{id}"
_SONGS_IDX = "buddy:songs"  # sorted set, score = added_at unix ts


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-") or "song"


class SongRepository:
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

    def exists(self, song_id: str) -> bool:
        return self._s.exists(_SONG_KEY.format(id=song_id))

    def get(self, song_id: str) -> dict | None:
        raw = self._s.get(_SONG_KEY.format(id=song_id))
        return json.loads(raw) if raw else None

    def save(self, data: dict) -> None:
        """Persist song metadata and update the sorted index (score = added_at)."""
        self._s.set(_SONG_KEY.format(id=data["id"]), json.dumps(data))
        self._s.add_object(_SONGS_IDX, {data["id"]: iso_to_score(data["added_at"])})

    def delete(self, song_id: str) -> None:
        self._s.delete(_SONG_KEY.format(id=song_id))
        self._s.delete_object(_SONGS_IDX, song_id)

    def list_ids(self, start: int = 0, stop: int = -1) -> list[str]:
        return self._s.get_objects(_SONGS_IDX, start, stop)


def get_song_repository() -> SongRepository:
    return SongRepository(get_redis_store())
