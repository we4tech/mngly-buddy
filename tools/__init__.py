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
from tools.songs import list_songs, search_songs, store_song
from tools.voice import delete_all_voices, delete_voice, list_available_voices, list_voices, play_voice, record_voice, speak


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
        store_song,
        list_songs,
        search_songs,
        record_voice,
        list_voices,
        play_voice,
        speak,
        list_available_voices,
        delete_voice,
        delete_all_voices,
    ]


def all_tool_functions() -> dict:
    """Return a mapping of tool name -> raw callable for direct invocation."""
    return {t.func.__name__: t.func for t in all_tools()}
