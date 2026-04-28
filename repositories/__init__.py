"""Repository layer — encapsulates all Redis persistence for BuddyAgent."""

from .calendar_repository import CalendarRepository, get_calendar_repository
from .note_repository import NoteRepository, get_note_repository

__all__ = [
    "NoteRepository",
    "get_note_repository",
    "CalendarRepository",
    "get_calendar_repository",
]
