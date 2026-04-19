import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_app import load_system_prompt
from tools.calendar import create_calendar_event, create_reminder, delete_calendar_event, delete_reminder, list_reminders, search_calendar
from tools.date import get_current_system_time
from tools.notes import create_note, delete_note, list_notes, read_note, search_notes
from tools import all_tools


def test_get_current_system_time_default_format() -> None:
    current_time = get_current_system_time()
    assert isinstance(current_time, str)
    assert len(current_time) >= 10


def test_load_system_prompt_fallback_when_no_url(monkeypatch, tmp_path) -> None:
    prompt_path = tmp_path / "fallback.md"
    prompt_path.write_text("Fallback prompt", encoding="utf-8")

    monkeypatch.setenv("SYSTEM_PROMPT_URL", "")
    monkeypatch.setattr("agent_app.DEFAULT_PROMPT_PATH", prompt_path)

    prompt = load_system_prompt()
    assert prompt == "Fallback prompt"


def test_create_search_and_read_note(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_DB", str(tmp_path / "buddy.db"))

    create_result = create_note("Sprint Planning", "Discuss roadmap and blockers")
    assert "Saved note" in create_result

    search_result = search_notes("roadmap")
    assert "Found 1 note(s):" in search_result
    assert "sprint-planning" in search_result

    read_result = read_note("sprint-planning")
    assert "Title: Sprint Planning" in read_result
    assert "Discuss roadmap and blockers" in read_result


def test_list_notes(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_DB", str(tmp_path / "buddy.db"))

    assert list_notes() == "No notes found."

    create_note("Alpha", "first note")
    create_note("Beta", "second note")

    result = list_notes()
    assert "Found 2 note(s):" in result
    assert "alpha" in result
    assert "beta" in result


def test_delete_note(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_DB", str(tmp_path / "buddy.db"))

    create_note("To Delete", "some content")
    assert "Deleted note 'to-delete'." == delete_note("to-delete")
    assert read_note("to-delete") == "No note found with id 'to-delete'."
    assert delete_note("to-delete") == "No note found with id 'to-delete'."


def test_read_note_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_DB", str(tmp_path / "buddy.db"))

    result = read_note("does-not-exist")
    assert "No note found with id 'does-not-exist'." == result


def test_all_tools_contains_new_tools() -> None:
    names = {tool.name for tool in all_tools()}
    assert "get_current_system_time" in names
    assert "create_calendar_event" in names
    assert "search_calendar" in names
    assert "sync_calendar" in names
    assert "delete_calendar_event" in names
    assert "create_reminder" in names
    assert "list_reminders" in names
    assert "delete_reminder" in names
    assert "create_note" in names
    assert "search_notes" in names
    assert "read_note" in names
    assert "list_notes" in names
    assert "delete_note" in names
    assert "search_local_calendar" not in names


def test_create_and_search_calendar_event(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_DB", str(tmp_path / "buddy.db"))

    result = create_calendar_event(
        title="Team standup",
        start_at="2026-04-20T09:00:00",
        end_at="2026-04-20T09:30:00",
    )
    assert "Created event 'team-standup'" in result

    found = search_calendar(query="standup")
    assert "Found 1 event(s):" in found
    assert "team-standup" in found


def test_create_recurring_event_specific_days(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_DB", str(tmp_path / "buddy.db"))

    result = create_calendar_event(
        title="Morning run",
        start_at="2026-04-21T07:00:00",
        end_at="2026-04-21T07:30:00",
        recurrence="specific_days",
        recurrence_days="MON,WED,FRI",
    )
    assert "Created event" in result

    found = search_calendar(query="morning run")
    assert "[specific_days]" in found


def test_create_event_invalid_recurrence(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_DB", str(tmp_path / "buddy.db"))

    result = create_calendar_event(
        title="Bad event",
        start_at="2026-04-20T10:00:00",
        end_at="2026-04-20T11:00:00",
        recurrence="fortnightly",
    )
    assert "Invalid recurrence" in result


def test_create_and_list_reminder(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_DB", str(tmp_path / "buddy.db"))

    assert list_reminders() == "No reminders found."

    result = create_reminder(
        title="Buy groceries",
        start_at="2026-04-20T08:00:00",
        end_at="2026-04-20T17:00:00",
    )
    assert "Created reminder 'buy-groceries'" in result

    listed = list_reminders()
    assert "Found 1 reminder(s):" in listed
    assert "buy-groceries" in listed


def test_create_recurring_reminder(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_DB", str(tmp_path / "buddy.db"))

    result = create_reminder(
        title="Weekly review",
        start_at="2026-04-25T09:00:00",
        end_at="2026-04-25T10:00:00",
        recurrence="weekly",
    )
    assert "Created reminder" in result

    listed = list_reminders()
    assert "[weekly]" in listed


def test_duplicate_calendar_event_rejected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_DB", str(tmp_path / "buddy.db"))

    create_calendar_event(
        title="Daily standup",
        start_at="2026-04-22T09:00:00",
        end_at="2026-04-22T09:15:00",
    )
    result = create_calendar_event(
        title="Daily standup",
        start_at="2026-04-22T09:00:00",
        end_at="2026-04-22T09:15:00",
    )
    assert "Duplicate" in result


def test_duplicate_reminder_rejected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_DB", str(tmp_path / "buddy.db"))

    create_reminder(
        title="Take medicine",
        start_at="2026-04-22T08:00:00",
        end_at="2026-04-22T09:00:00",
    )
    result = create_reminder(
        title="Take medicine",
        start_at="2026-04-22T08:00:00",
        end_at="2026-04-22T09:00:00",
    )
    assert "Duplicate" in result


def test_delete_calendar_event(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_DB", str(tmp_path / "buddy.db"))

    create_calendar_event(
        title="Lunch break",
        start_at="2026-04-22T12:00:00",
        end_at="2026-04-22T13:00:00",
    )
    assert "Deleted event 'lunch-break'." == delete_calendar_event("lunch-break")
    assert "No event found with id 'lunch-break'." == delete_calendar_event("lunch-break")


def test_delete_reminder(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_DB", str(tmp_path / "buddy.db"))

    create_reminder(
        title="Call dentist",
        start_at="2026-04-22T10:00:00",
        end_at="2026-04-22T11:00:00",
    )
    assert "Deleted reminder 'call-dentist'." == delete_reminder("call-dentist")
    assert "No reminder found with id 'call-dentist'." == delete_reminder("call-dentist")

