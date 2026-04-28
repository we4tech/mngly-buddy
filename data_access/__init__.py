"""Data-access layer — abstracts storage from repository logic."""

from .interface import DataStore
from .redis_store import RedisStore, get_redis_store

__all__ = [
    "DataStore",
    "RedisStore",
    "get_redis_store",
]
