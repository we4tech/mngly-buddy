"""Tool modules for BuddyAgent."""

from tools.calendar import search_local_calendar
from tools.date import get_current_system_time
from tools.notes import create_note, delete_note, list_notes, read_note, search_notes


def all_tools() -> list:
    """Return a list of all available tools."""
    return [
        get_current_system_time,
        search_local_calendar,
        create_note,
        list_notes,
        search_notes,
        read_note,
        delete_note,
    ]
