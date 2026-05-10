"""Repository for voice recording persistence."""

import json

from db import iso_to_score
from data_access.interface import DataStore
from data_access.redis_store import get_redis_store

_VOICE_KEY = "buddy:voice:{id}"
_VOICES_IDX = "buddy:voices"  # sorted set, score = recorded_at unix ts


class VoiceRepository:
    def __init__(self, store: DataStore) -> None:
        self._s = store

    def exists(self, voice_id: str) -> bool:
        return self._s.exists(_VOICE_KEY.format(id=voice_id))

    def get(self, voice_id: str) -> dict | None:
        raw = self._s.get(_VOICE_KEY.format(id=voice_id))
        return json.loads(raw) if raw else None

    def save(self, data: dict) -> None:
        """Persist voice metadata and update the sorted index (score = recorded_at)."""
        self._s.set(_VOICE_KEY.format(id=data["id"]), json.dumps(data))
        self._s.add_object(_VOICES_IDX, {data["id"]: iso_to_score(data["recorded_at"])})

    def delete(self, voice_id: str) -> None:
        self._s.delete(_VOICE_KEY.format(id=voice_id))
        self._s.delete_object(_VOICES_IDX, voice_id)

    def list_ids(self, start: int = 0, stop: int = -1) -> list[str]:
        return self._s.get_objects(_VOICES_IDX, start, stop)


def get_voice_repository() -> VoiceRepository:
    return VoiceRepository(get_redis_store())
