import re
from datetime import datetime, timezone
from typing import Annotated

from agent_framework import tool
from pydantic import Field

from repositories.note_repository import get_note_repository


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = slug.strip("-")
    return slug or "note"


@tool(approval_mode="never_require")
def create_note(
    title: Annotated[str, Field(description="Short title for the note.")],
    content: Annotated[str, Field(description="Main note content.")],
) -> str:
    """Store a note in Redis so it can be searched and read later."""
    title = title.strip()
    content = content.strip()
    if not title:
        return "Note title cannot be empty."
    if not content:
        return "Note content cannot be empty."
    repo = get_note_repository()
    note_id = repo.unique_id(title)
    now = datetime.now(timezone.utc).isoformat()
    data = {"id": note_id, "title": title, "content": content, "created_at": now}
    repo.save(data)
    return f"Saved note '{note_id}'."


@tool(approval_mode="never_require")
def search_notes(
    query: Annotated[str, Field(description="Keyword to search in note title and content.")],
    max_results: Annotated[
        int,
        Field(description="Maximum notes to return. Must be between 1 and 50."),
    ] = 10,
) -> str:
    """Search notes stored in Redis by keyword."""
    query = query.strip()
    if not query:
        return "Search query cannot be empty."
    max_results = max(1, min(max_results, 50))
    keyword = query.lower()
    repo = get_note_repository()
    all_ids = repo.list_ids()
    matches = []
    for nid in all_ids:
        note = repo.get(nid)
        if not note:
            continue
        if keyword in note["title"].lower() or keyword in note["content"].lower():
            matches.append(note)
        if len(matches) >= max_results:
            break
    if not matches:
        return f"No notes matched '{query}'."
    lines = [f"Found {len(matches)} note(s):"]
    for note in matches:
        preview = note["content"][:120].replace("\n", " ")
        lines.append(f"- {note['id']}: {preview}")
    return "\n".join(lines)


@tool(approval_mode="never_require")
def list_notes(
    max_results: Annotated[
        int,
        Field(description="Maximum number of notes to list. Must be between 1 and 50."),
    ] = 20,
) -> str:
    """List all notes stored in Redis ordered by creation time."""
    max_results = max(1, min(max_results, 50))
    repo = get_note_repository()
    ids = repo.list_ids(0, max_results - 1)
    if not ids:
        return "No notes found."
    lines = [f"Found {len(ids)} note(s):"]
    for nid in ids:
        note = repo.get(nid)
        if not note:
            continue
        lines.append(f"- {note['id']}: {note['title']} ({note['created_at']})")
    return "\n".join(lines)


@tool(approval_mode="never_require")
def read_note(
    note_id: Annotated[
        str,
        Field(description="Note id, typically from search_notes or list_notes results."),
    ],
) -> str:
    """Read a previously stored note by id."""
    safe_id = _slugify(note_id)
    repo = get_note_repository()
    note = repo.get(safe_id)
    if not note:
        return f"No note found with id '{safe_id}'."
    return f"Title: {note['title']}\nCreated: {note['created_at']}\n\n{note['content']}"


@tool(approval_mode="never_require")
def delete_note(
    note_id: Annotated[
        str,
        Field(description="Note id, typically from list_notes or search_notes results."),
    ],
) -> str:
    """Delete a note from Redis by id."""
    safe_id = _slugify(note_id)
    repo = get_note_repository()
    if not repo.exists(safe_id):
        return f"No note found with id '{safe_id}'."
    repo.delete(safe_id)
    return f"Deleted note '{safe_id}'."
