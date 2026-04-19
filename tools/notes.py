import re
from datetime import datetime, timezone
from typing import Annotated

from agent_framework import tool
from pydantic import Field

from db import get_connection


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = slug.strip("-")
    return slug or "note"


def _unique_id(title: str) -> str:
    base = _slugify(title)
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM notes WHERE id = ?", (base,)).fetchone() is None:
            return base
        index = 2
        while True:
            candidate = f"{base}-{index}"
            if conn.execute("SELECT 1 FROM notes WHERE id = ?", (candidate,)).fetchone() is None:
                return candidate
            index += 1


@tool(approval_mode="never_require")
def create_note(
    title: Annotated[str, Field(description="Short title for the note.")],
    content: Annotated[str, Field(description="Main note content.")],
) -> str:
    """Store a note in the local SQLite database so it can be searched and read later."""
    title = title.strip()
    content = content.strip()

    if not title:
        return "Note title cannot be empty."

    if not content:
        return "Note content cannot be empty."

    note_id = _unique_id(title)
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO notes (id, title, content, created_at) VALUES (?, ?, ?, ?)",
            (note_id, title, content, now),
        )
        conn.commit()

    return f"Saved note '{note_id}'."


@tool(approval_mode="never_require")
def search_notes(
    query: Annotated[str, Field(description="Keyword to search in note title and content.")],
    max_results: Annotated[
        int,
        Field(description="Maximum notes to return. Must be between 1 and 50."),
    ] = 10,
) -> str:
    """Search locally stored notes by keyword."""
    query = query.strip()
    if not query:
        return "Search query cannot be empty."

    max_results = max(1, min(max_results, 50))
    keyword = f"%{query.lower()}%"

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, content FROM notes
            WHERE lower(title) LIKE ? OR lower(content) LIKE ?
            ORDER BY created_at
            LIMIT ?
            """,
            (keyword, keyword, max_results),
        ).fetchall()

    if not rows:
        return f"No notes matched '{query}'."

    lines = [f"Found {len(rows)} note(s):"]
    for row in rows:
        preview = row["content"][:120].replace("\n", " ")
        lines.append(f"- {row['id']}: {preview}")

    return "\n".join(lines)


@tool(approval_mode="never_require")
def list_notes(
    max_results: Annotated[
        int,
        Field(description="Maximum number of notes to list. Must be between 1 and 50."),
    ] = 20,
) -> str:
    """List all locally stored notes with their id, title, and creation date."""
    max_results = max(1, min(max_results, 50))

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at FROM notes ORDER BY created_at LIMIT ?",
            (max_results,),
        ).fetchall()

    if not rows:
        return "No notes found."

    lines = [f"Found {len(rows)} note(s):"]
    for row in rows:
        lines.append(f"- {row['id']}: {row['title']} ({row['created_at']})")

    return "\n".join(lines)


@tool(approval_mode="never_require")
def read_note(
    note_id: Annotated[
        str,
        Field(description="Note id, typically from search_notes or list_notes results."),
    ]
) -> str:
    """Read a previously stored note by id."""
    safe_id = _slugify(note_id)

    with get_connection() as conn:
        row = conn.execute(
            "SELECT title, content, created_at FROM notes WHERE id = ?", (safe_id,)
        ).fetchone()

    if row is None:
        return f"No note found with id '{safe_id}'."

    return f"Title: {row['title']}\nCreated: {row['created_at']}\n\n{row['content']}"


@tool(approval_mode="never_require")
def delete_note(
    note_id: Annotated[
        str,
        Field(description="Note id, typically from list_notes or search_notes results."),
    ]
) -> str:
    """Delete a locally stored note by id."""
    safe_id = _slugify(note_id)

    with get_connection() as conn:
        result = conn.execute("DELETE FROM notes WHERE id = ?", (safe_id,))
        conn.commit()

    if result.rowcount == 0:
        return f"No note found with id '{safe_id}'."

    return f"Deleted note '{safe_id}'."
