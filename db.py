"""Redis connection and helpers for BuddyAgent."""

import os
from datetime import datetime, timezone

import redis

DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def get_redis_url() -> str:
    return os.getenv("BUDDY_REDIS_URL", DEFAULT_REDIS_URL).strip()


def get_client() -> redis.Redis:
    """Return a Redis client from BUDDY_REDIS_URL (or the default localhost)."""
    return redis.from_url(get_redis_url(), decode_responses=True)


def iso_to_score(iso: str) -> float:
    """Convert an ISO-8601 timestamp to a float unix timestamp for sorted set scoring."""
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return 0.0

