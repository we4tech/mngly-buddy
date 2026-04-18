import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_app import load_system_prompt
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
    monkeypatch.setenv("BUDDY_NOTES_DIR", str(tmp_path))

    create_result = create_note("Sprint Planning", "Discuss roadmap and blockers")
    assert "Saved note" in create_result

    search_result = search_notes("roadmap")
    assert "Found 1 note(s):" in search_result
    assert "sprint-planning" in search_result

    read_result = read_note("sprint-planning")
    assert "Title: Sprint Planning" in read_result
    assert "Discuss roadmap and blockers" in read_result


def test_list_notes(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_NOTES_DIR", str(tmp_path))

    assert list_notes() == "No notes found."

    create_note("Alpha", "first note")
    create_note("Beta", "second note")

    result = list_notes()
    assert "Found 2 note(s):" in result
    assert "alpha" in result
    assert "beta" in result


def test_delete_note(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_NOTES_DIR", str(tmp_path))

    create_note("To Delete", "some content")
    assert "Deleted note 'to-delete'." == delete_note("to-delete")
    assert read_note("to-delete") == "No note found with id 'to-delete'."
    assert delete_note("to-delete") == "No note found with id 'to-delete'."


def test_read_note_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUDDY_NOTES_DIR", str(tmp_path))

    result = read_note("does-not-exist")
    assert "No note found with id 'does-not-exist'." == result


def test_all_tools_contains_new_tools() -> None:
    names = {tool.name for tool in all_tools()}
    assert "get_current_system_time" in names
    assert "search_local_calendar" in names
    assert "create_note" in names
    assert "search_notes" in names
    assert "read_note" in names
    assert "list_notes" in names
    assert "delete_note" in names


