"""Song storage tools for BuddyAgent."""

from datetime import datetime, timezone
from typing import Annotated

from agent_framework import tool
from pydantic import Field

from repositories.song_repository import get_song_repository


@tool(approval_mode="never_require")
def store_song(
    title: Annotated[str, Field(description="Title of the song.")],
    artist: Annotated[str, Field(description="Artist or band name.")] = "",
    album: Annotated[str, Field(description="Album the song belongs to.")] = "",
    genre: Annotated[str, Field(description="Genre of the song (e.g. pop, rock, jazz).")] = "",
    notes: Annotated[str, Field(description="Any extra notes about the song.")] = "",
) -> str:
    """Save a song to the Redis store so it can be listed and searched later."""
    title = title.strip()
    if not title:
        return "Song title cannot be empty."

    repo = get_song_repository()
    song_id = repo.unique_id(title)
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "id": song_id,
        "title": title,
        "artist": artist.strip(),
        "album": album.strip(),
        "genre": genre.strip(),
        "notes": notes.strip(),
        "added_at": now,
    }
    repo.save(data)
    artist_part = f" by {artist.strip()}" if artist.strip() else ""
    return f"Saved song '{title}'{artist_part} as '{song_id}'."


@tool(approval_mode="never_require")
def list_songs(
    max_results: Annotated[
        int,
        Field(description="Maximum number of songs to list. Must be between 1 and 100."),
    ] = 20,
) -> str:
    """List all stored songs ordered by the time they were added."""
    max_results = max(1, min(max_results, 100))
    repo = get_song_repository()
    ids = repo.list_ids()
    if not ids:
        return "No songs stored yet."

    ids = ids[-max_results:]  # most recent slice
    lines = [f"Songs ({len(ids)} shown, oldest → newest):\n"]
    for sid in ids:
        song = repo.get(sid)
        if not song:
            continue
        artist_part = f" — {song['artist']}" if song.get("artist") else ""
        album_part = f" [{song['album']}]" if song.get("album") else ""
        genre_part = f" ({song['genre']})" if song.get("genre") else ""
        lines.append(f"- {song['title']}{artist_part}{album_part}{genre_part}  [id: {song['id']}]")
    return "\n".join(lines)


@tool(approval_mode="never_require")
def search_songs(
    query: Annotated[
        str,
        Field(description="Keyword to search in song title, artist, album, genre, or notes."),
    ],
    max_results: Annotated[
        int,
        Field(description="Maximum songs to return. Must be between 1 and 50."),
    ] = 10,
) -> str:
    """Search stored songs by keyword across title, artist, album, genre, and notes."""
    query = query.strip()
    if not query:
        return "Search query cannot be empty."

    max_results = max(1, min(max_results, 50))
    keyword = query.lower()
    repo = get_song_repository()
    all_ids = repo.list_ids()

    matches = []
    for sid in all_ids:
        song = repo.get(sid)
        if not song:
            continue
        searchable = " ".join([
            song.get("title", ""),
            song.get("artist", ""),
            song.get("album", ""),
            song.get("genre", ""),
            song.get("notes", ""),
        ]).lower()
        if keyword in searchable:
            matches.append(song)
        if len(matches) >= max_results:
            break

    if not matches:
        return f"No songs matched '{query}'."

    lines = [f"Found {len(matches)} song(s) matching '{query}':\n"]
    for song in matches:
        artist_part = f" — {song['artist']}" if song.get("artist") else ""
        album_part = f" [{song['album']}]" if song.get("album") else ""
        genre_part = f" ({song['genre']})" if song.get("genre") else ""
        lines.append(f"- {song['title']}{artist_part}{album_part}{genre_part}  [id: {song['id']}]")
    return "\n".join(lines)
