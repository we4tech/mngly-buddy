import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from agent_framework import tool
from pydantic import Field

DEFAULT_NOTES_DIR = Path(__file__).resolve().parents[1] / "data" / "notes"


def _get_notes_dir() -> Path:
    raw_dir = os.getenv("BUDDY_NOTES_DIR", "").strip()
    notes_dir = Path(raw_dir).expanduser() if raw_dir else DEFAULT_NOTES_DIR
    notes_dir.mkdir(parents=True, exist_ok=True)
    return notes_dir


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = slug.strip("-")
    return slug or "note"


def _create_unique_note_path(title: str) -> Path:
    notes_dir = _get_notes_dir()
    base = _slugify(title)
    candidate = notes_dir / f"{base}.md"
    index = 2

    while candidate.exists():
        candidate = notes_dir / f"{base}-{index}.md"
        index += 1

    return candidate


@tool(approval_mode="never_require")
def create_note(
    title: Annotated[str, Field(description="Short title for the note.")],
    content: Annotated[str, Field(description="Main note content.")],
) -> str:
    """Store a note locally so it can be searched and read later."""
    title = title.strip()
    content = content.strip()

    if not title:
        return "Note title cannot be empty."

    if not content:
        return "Note content cannot be empty."

    now = datetime.now(timezone.utc).isoformat()
    path = _create_unique_note_path(title)
    note_id = path.stem

    body = "\n".join(
        [
            f"Title: {title}",
            f"Created: {now}",
            "",
            content,
            "",
        ]
    )
    path.write_text(body, encoding="utf-8")

    return f"Saved note '{note_id}' at {path}."


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
    keyword = query.lower()
    matches: list[tuple[str, str]] = []

    for path in sorted(_get_notes_dir().glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if keyword not in text.lower():
            continue

        preview = text.splitlines()[-1].strip() if text.splitlines() else ""
        if not preview:
            preview = "(empty note body)"

        matches.append((path.stem, preview))

    if not matches:
        return f"No notes matched '{query}'."

    lines = [f"Found {min(len(matches), max_results)} note(s):"]
    for note_id, preview in matches[:max_results]:
        lines.append(f"- {note_id}: {preview[:120]}")

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
    paths = sorted(_get_notes_dir().glob("*.md"))

    if not paths:
        return "No notes found."

    lines = [f"Found {min(len(paths), max_results)} note(s):"]
    for path in paths[:max_results]:
        title = path.stem
        created = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("Title: "):
                title = line[len("Title: "):]
            elif line.startswith("Created: "):
                created = line[len("Created: "):]
            if title and created:
                break
        lines.append(f"- {path.stem}: {title} ({created})" if created else f"- {path.stem}: {title}")

    return "\n".join(lines)


@tool(approval_mode="never_require")
def read_note(
    note_id: Annotated[
        str,
        Field(description="Note id (filename without extension), typically from search_notes results."),
    ]
) -> str:
    """Read a previously stored local note by id."""
    safe_note_id = _slugify(note_id)
    path = _get_notes_dir() / f"{safe_note_id}.md"

    if not path.exists():
        return f"No note found with id '{safe_note_id}'."

    return path.read_text(encoding="utf-8").strip()


@tool(approval_mode="never_require")
def delete_note(
    note_id: Annotated[
        str,
        Field(description="Note id (filename without extension), typically from list_notes or search_notes results."),
    ]
) -> str:
    """Delete a locally stored note by id."""
    safe_note_id = _slugify(note_id)
    path = _get_notes_dir() / f"{safe_note_id}.md"

    if not path.exists():
        return f"No note found with id '{safe_note_id}'."

    path.unlink()
    return f"Deleted note '{safe_note_id}'."
