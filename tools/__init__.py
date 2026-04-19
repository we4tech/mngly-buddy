"""Tool modules for BuddyAgent."""

from tools.calendar import (
    create_calendar_event,
    create_reminder,
    delete_calendar_event,
    delete_reminder,
    list_reminders,
    search_calendar,
    sync_calendar,
)
from tools.date import get_current_system_time
from tools.files import get_file_content
from tools.notes import create_note, delete_note, list_notes, read_note, search_notes


def all_tools() -> list:
    """Return a list of all available tools."""
    return [
        get_current_system_time,
        create_calendar_event,
        search_calendar,
        sync_calendar,
        delete_calendar_event,
        create_reminder,
        list_reminders,
        delete_reminder,
        create_note,
        list_notes,
        search_notes,
        read_note,
        delete_note,
        get_file_content,
    ]


def all_tool_functions() -> dict:
    """Return a mapping of tool name -> raw callable for direct invocation."""
    return {t.func.__name__: t.func for t in all_tools()}
