"""Voice recording tools for BuddyAgent."""

import subprocess
import sys
import threading
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from agent_framework import tool
from pydantic import Field

from repositories.voice_repository import get_voice_repository

_VOICE_DIR = Path("data/voice")

# Audio recording settings
_CHANNELS = 1
_RATE = 16000
_CHUNK = 1024
_FORMAT_WIDTH = 2  # 16-bit PCM → 2 bytes per sample


def _ensure_voice_dir() -> Path:
    _VOICE_DIR.mkdir(parents=True, exist_ok=True)
    return _VOICE_DIR


@tool(approval_mode="never_require")
def record_voice(
    label: Annotated[
        str,
        Field(description="Optional short label for the recording (e.g. 'homework reminder')."),
    ] = "",
) -> str:
    """Record audio from the microphone and save it as a WAV file.

    Recording starts immediately and stops when Enter is pressed or after
    60 seconds of silence. The file is saved to data/voice/<timestamp>.wav
    and registered in the Redis voice index.
    """
    import pyaudio  # lazy — only available with voice support

    pa = pyaudio.PyAudio()
    frames: list[bytes] = []
    stop_event = threading.Event()

    stream = pa.open(
        format=pa.get_format_from_width(_FORMAT_WIDTH),
        channels=_CHANNELS,
        rate=_RATE,
        input=True,
        frames_per_buffer=_CHUNK,
    )

    def _recorder() -> None:
        """Capture audio chunks until stop_event is set."""
        while not stop_event.is_set():
            try:
                data = stream.read(_CHUNK, exception_on_overflow=False)
                frames.append(data)
            except OSError:
                break

    def _enter_watcher() -> None:
        try:
            sys.stdin.readline()
        except (EOFError, OSError):
            pass
        stop_event.set()

    recorder_thread = threading.Thread(target=_recorder, daemon=True)
    enter_thread = threading.Thread(target=_enter_watcher, daemon=True)

    print("🎙  Recording… press Enter to stop.", flush=True)
    recorder_thread.start()
    enter_thread.start()

    # Also enforce a 60-second hard cap
    stop_event.wait(timeout=60)
    stop_event.set()
    recorder_thread.join(timeout=2)

    stream.stop_stream()
    stream.close()
    pa.terminate()

    if not frames:
        return "No audio was captured."

    # Persist WAV file
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    dest = _ensure_voice_dir() / f"{timestamp}.wav"

    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(_CHANNELS)
        wf.setsampwidth(_FORMAT_WIDTH)
        wf.setframerate(_RATE)
        wf.writeframes(b"".join(frames))

    duration_s = round(len(frames) * _CHUNK / _RATE, 1)

    # Register in Redis
    repo = get_voice_repository()
    data = {
        "id": timestamp,
        "path": str(dest),
        "label": label.strip(),
        "recorded_at": now.isoformat(),
        "duration_s": duration_s,
    }
    repo.save(data)

    label_part = f" ({label.strip()})" if label.strip() else ""
    return (
        f"Saved recording{label_part} → {dest}  "
        f"[{duration_s}s, {len(frames)} chunks]"
    )


@tool(approval_mode="never_require")
def list_voices() -> str:
    """List all voice recordings saved in the Redis index."""
    repo = get_voice_repository()
    ids = repo.list_ids()
    if not ids:
        return "No voice recordings found."
    lines = ["Voice recordings (oldest → newest):\n"]
    for vid in ids:
        rec = repo.get(vid)
        if not rec:
            continue
        label = f" — {rec['label']}" if rec.get("label") else ""
        lines.append(
            f"- {rec['id']}{label}  |  {rec['duration_s']}s  |  {rec['path']}"
        )
    return "\n".join(lines)


@tool(approval_mode="never_require")
def delete_voice(
    voice_id: Annotated[
        str,
        Field(description="The timestamp ID of the recording to delete (e.g. 20260509T143000Z)."),
    ],
) -> str:
    """Delete a specific voice recording file and remove it from the Redis index."""
    repo = get_voice_repository()
    rec = repo.get(voice_id)
    if not rec:
        return f"No recording found with id '{voice_id}'."

    path = Path(rec["path"])
    if path.exists():
        path.unlink()

    repo.delete(voice_id)
    return f"Deleted recording '{voice_id}'."


@tool(approval_mode="never_require")
def delete_all_voices() -> str:
    """Delete every voice recording file and clear the Redis voice index."""
    repo = get_voice_repository()
    ids = repo.list_ids()
    if not ids:
        return "No voice recordings to delete."

    deleted_files = 0
    for vid in ids:
        rec = repo.get(vid)
        if rec:
            path = Path(rec["path"])
            if path.exists():
                path.unlink()
                deleted_files += 1
        repo.delete(vid)

    # Remove the voice directory if now empty
    if _VOICE_DIR.exists() and not any(_VOICE_DIR.iterdir()):
        _VOICE_DIR.rmdir()

    return f"Deleted {len(ids)} recording(s) ({deleted_files} file(s) removed)."


@tool(approval_mode="never_require")
def play_voice(
    voice_id: Annotated[
        str,
        Field(description="The timestamp ID of the recording to play (e.g. 20260509T143000Z)."),
    ],
) -> str:
    """Play back a saved voice recording. Press Enter to stop playback early."""
    repo = get_voice_repository()
    rec = repo.get(voice_id)
    if not rec:
        return f"No recording found with id '{voice_id}'."

    path = Path(rec["path"])
    if not path.exists():
        return f"Audio file for '{voice_id}' is missing from disk."

    label = f" ({rec['label']})" if rec.get("label") else ""
    print(f"▶  Playing '{voice_id}'{label} [{rec['duration_s']}s] — press Enter to stop.", flush=True)

    proc = subprocess.Popen(
        ["afplay", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def _enter_watcher() -> None:
        try:
            sys.stdin.readline()
        except (EOFError, OSError):
            pass
        proc.terminate()

    threading.Thread(target=_enter_watcher, daemon=True).start()
    proc.wait()
    return f"Finished playing '{voice_id}'."


# Default voice used when none is specified
_DEFAULT_VOICE = ""


@tool(approval_mode="never_require")
def speak(
    text: Annotated[str, Field(description="The text to speak aloud.")],
    voice: Annotated[
        str,
        Field(
            description=(
                "macOS voice name to use (e.g. 'Junior', 'Samantha', 'Fred'). "
                "Leave empty to use the default Junior voice."
            )
        ),
    ] = "",
) -> str:
    """Speak text aloud using a macOS voice. Press Enter to stop early.

    Use list_available_voices to see installed voice names.
    """
    text = text.strip()
    if not text:
        return "Nothing to speak — text was empty."

    chosen = voice.strip() or _DEFAULT_VOICE
    print(f"🔊  Speaking with voice '{chosen}' — press Enter to stop.", flush=True)

    proc = subprocess.Popen(
        ["say", "-v", chosen, text],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    def _enter_watcher() -> None:
        try:
            sys.stdin.readline()
        except (EOFError, OSError):
            pass
        proc.terminate()

    threading.Thread(target=_enter_watcher, daemon=True).start()
    proc.wait()
    return f"Done speaking with voice '{chosen}'."


@tool(approval_mode="never_require")
def list_available_voices(
    language: Annotated[
        str,
        Field(description="Filter by language code (e.g. 'en_US'). Leave empty to list all."),
    ] = "",
) -> str:
    """List macOS voices available for the speak tool."""
    result = subprocess.run(
        ["say", "-v", "?"],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = result.stdout.splitlines()
    if language.strip():
        lang = language.strip()
        lines = [l for l in lines if lang.lower() in l.lower()]
    if not lines:
        return "No voices found matching that language."

    # Format: "VoiceName   lang   # sample"
    voices = []
    for line in lines:
        parts = line.split("#", 1)
        meta = parts[0].strip()
        sample = parts[1].strip() if len(parts) > 1 else ""
        voices.append(f"- {meta}  →  {sample}")
    return "Available voices:\n" + "\n".join(voices)
