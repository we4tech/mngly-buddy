import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fakeredis
import pytest

from data_access.redis_store import RedisStore
from repositories.note_repository import NoteRepository
from repositories.calendar_repository import CalendarRepository


@pytest.fixture
def redis_store(monkeypatch):
    """Shared in-memory DataStore per test — patches repository factories."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    store = RedisStore(fake)
    note_repo = NoteRepository(store)
    cal_repo = CalendarRepository(store)
    monkeypatch.setattr("tools.notes.get_note_repository", lambda: note_repo)
    monkeypatch.setattr("tools.calendar.get_calendar_repository", lambda: cal_repo)
    return fake
