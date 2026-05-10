"""Redis-backed conversation history provider for agent_framework."""

from __future__ import annotations

from typing import Any, Sequence

from agent_framework import HistoryProvider, Message

from db import get_client

_HISTORY_KEY = "buddy:history:{session_id}"
_DEFAULT_MAX_MESSAGES = 200  # cap per session to avoid unbounded growth


class RedisHistoryProvider(HistoryProvider):
    """Stores conversation history in Redis, keyed by session_id.

    Each exchange is appended as a JSON-serialized Message to a Redis list.
    On load, up to *max_messages* most-recent entries are returned so the
    context window stays manageable.
    """

    DEFAULT_SOURCE_ID = "redis_history"

    def __init__(
        self,
        source_id: str | None = None,
        *,
        max_messages: int = _DEFAULT_MAX_MESSAGES,
        load_messages: bool = True,
        store_inputs: bool = True,
        store_context_messages: bool = False,
        store_context_from: set[str] | None = None,
        store_outputs: bool = True,
    ) -> None:
        super().__init__(
            source_id=source_id or self.DEFAULT_SOURCE_ID,
            load_messages=load_messages,
            store_inputs=store_inputs,
            store_context_messages=store_context_messages,
            store_context_from=store_context_from,
            store_outputs=store_outputs,
        )
        self._max_messages = max_messages

    def _key(self, session_id: str | None) -> str:
        return _HISTORY_KEY.format(session_id=session_id or "default")

    async def get_messages(
        self,
        session_id: str | None,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Message]:
        """Load conversation history from Redis."""
        client = get_client()
        key = self._key(session_id)
        # Fetch the most recent max_messages entries from the end of the list
        raw_entries: list[str] = client.lrange(key, -self._max_messages, -1)  # type: ignore[assignment]
        messages: list[Message] = []
        for raw in raw_entries:
            try:
                messages.append(Message.from_json(raw))
            except Exception:
                pass  # skip corrupted entries
        return messages

    async def save_messages(
        self,
        session_id: str | None,
        messages: Sequence[Message],
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Append new messages to the Redis list for this session."""
        if not messages:
            return
        client = get_client()
        key = self._key(session_id)
        serialized = [m.to_json() for m in messages]
        client.rpush(key, *serialized)
        # Trim to cap to avoid unbounded growth
        client.ltrim(key, -self._max_messages, -1)
