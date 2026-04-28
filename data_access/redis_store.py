"""Redis-backed implementation of the DataStore interface."""

from typing import cast

import redis

from db import get_client
from .interface import DataStore


class RedisStore(DataStore):
    """Thin adapter that maps DataStore operations onto a redis-py client."""

    def __init__(self, client: redis.Redis) -> None:
        self._r = client

    def get(self, key: str) -> str | None:
        return cast(str | None, self._r.get(key))

    def set(self, key: str, value: str) -> None:
        self._r.set(key, value)

    def delete(self, *keys: str) -> None:
        if keys:
            self._r.delete(*keys)

    def exists(self, key: str) -> bool:
        return bool(self._r.exists(key))

    def add_object(self, key: str, mapping: dict[str, float]) -> None:
        self._r.zadd(key, mapping)

    def get_objects(self, key: str, start: int, stop: int) -> list[str]:
        return cast(list[str] | None, self._r.zrange(key, start, stop)) or []

    def delete_object(self, key: str, *members: str) -> None:
        if members:
            self._r.zrem(key, *members)


def get_redis_store() -> RedisStore:
    """Return a RedisStore connected via BUDDY_REDIS_URL (or the default localhost)."""
    return RedisStore(get_client())
