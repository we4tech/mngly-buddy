"""Abstract data-access interface used by all repositories.

Concrete implementations (e.g. RedisStore) satisfy this contract so that
repositories never depend on any specific storage technology.
"""

from abc import ABC, abstractmethod


class DataStore(ABC):
    """Minimal key-value + sorted-set interface required by BuddyAgent repositories."""

    @abstractmethod
    def get(self, key: str) -> str | None:
        """Return the string value stored at *key*, or ``None`` if absent."""

    @abstractmethod
    def set(self, key: str, value: str) -> None:
        """Store *value* at *key*, overwriting any previous value."""

    @abstractmethod
    def delete(self, *keys: str) -> None:
        """Remove one or more keys. Missing keys are silently ignored."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return ``True`` if *key* exists in the store."""

    @abstractmethod
    def add_object(self, key: str, mapping: dict[str, float]) -> None:
        """Add members with their scores to the sorted set at *key*."""

    @abstractmethod
    def get_objects(self, key: str, start: int, stop: int) -> list[str]:
        """Return members of the sorted set at *key* ordered by score (ascending).

        *start* and *stop* are zero-based inclusive indices; ``-1`` means the
        last element.
        """

    @abstractmethod
    def delete_object(self, key: str, *members: str) -> None:
        """Remove *members* from the sorted set at *key*. Missing members are ignored."""
