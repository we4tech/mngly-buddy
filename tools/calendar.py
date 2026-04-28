"""Calendar tools — Redis-backed ActivityEvent and Reminder management with macOS sync."""

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Annotated

from agent_framework import tool
from pydantic import Field

from repositories.calendar_repository import CalendarRepository, get_calendar_repository


# ---------------------------------------------------------------------------
# Recurrence options
# ---------------------------------------------------------------------------

class Recurrence(str, Enum):
    NONE = "none"
    DAILY = "daily"
    SPECIFIC_DAYS = "specific_days"  # recurrence_days = "MON,WED,FRI"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


_VALID_RECURRENCES = {r.value for r in Recurrence}
_VALID_DAYS = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ActivityEvent:
    """A calendar event with optional recurrence.

    recurrence_days is only used when recurrence == 'specific_days' and holds
    a comma-separated list of weekday abbreviations, e.g. 'MON,WED,FRI'.
    source is 'local' for user-created events or 'system' for events synced
    from the macOS Calendar app.
    """
    id: str
    title: str
    start_at: str           # ISO-8601
    end_at: str             # ISO-8601
    location: str = ""
    notes: str = ""
    recurrence: str = Recurrence.NONE
    recurrence_days: str = ""
    source: str = "local"
    external_id: str = ""   # EventKit identifier used for dedup during sync
    calendar_name: str = ""
    created_at: str = ""


@dataclass
class Reminder:
    """A reminder with optional recurrence, mirroring ActivityEvent's structure.

    start_at is when the reminder becomes active.
    end_at is the due date/time when the reminder fires.
    recurrence_days is only used when recurrence == 'specific_days'.
    """
    id: str
    title: str
    start_at: str           # ISO-8601 — reminder activation time
    end_at: str             # ISO-8601 — reminder due/fire time
    notes: str = ""
    recurrence: str = Recurrence.NONE
    recurrence_days: str = ""
    created_at: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-") or "event"


def _validate_recurrence(recurrence: str, recurrence_days: str) -> str | None:
    """Return an error string or None if valid."""
    if recurrence not in _VALID_RECURRENCES:
        return f"Invalid recurrence '{recurrence}'. Choose from: {', '.join(sorted(_VALID_RECURRENCES))}."
    if recurrence == Recurrence.SPECIFIC_DAYS:
        if not recurrence_days.strip():
            return "recurrence_days is required when recurrence is 'specific_days' (e.g. 'MON,WED,FRI')."
        days = {d.strip().upper() for d in recurrence_days.split(",")}
        invalid = days - _VALID_DAYS
        if invalid:
            return f"Invalid day(s): {', '.join(sorted(invalid))}. Use: {', '.join(sorted(_VALID_DAYS))}."
    return None


# ---------------------------------------------------------------------------
# macOS EventKit helpers (used only by sync_calendar)
# ---------------------------------------------------------------------------

_NS_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)


def _dt_to_nsdate(dt: datetime):
    from Foundation import NSDate  # type: ignore[import]
    secs = (dt.astimezone(timezone.utc) - _NS_EPOCH).total_seconds()
    return NSDate.dateWithTimeIntervalSinceReferenceDate_(secs)


def _nsdate_to_iso(nsdate) -> str:
    if nsdate is None:
        return ""
    secs = float(nsdate.timeIntervalSinceReferenceDate())
    return (_NS_EPOCH + timedelta(seconds=secs)).replace(microsecond=0).isoformat()


def _request_eventkit_access(store) -> bool:
    import EventKit  # type: ignore[import]
    from Foundation import NSDate, NSRunLoop  # type: ignore[import]

    result: dict = {"granted": False, "done": False}

    def callback(granted, error):
        result["granted"] = bool(granted)
        result["done"] = True

    if hasattr(store, "requestFullAccessToEventsWithCompletion_"):
        store.requestFullAccessToEventsWithCompletion_(callback)
    else:
        store.requestAccessToEntityType_completion_(0, callback)

    deadline = time.time() + 15
    while not result["done"] and time.time() < deadline:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))

    return result["granted"]


def _fetch_system_events(start_dt: datetime, end_dt: datetime) -> list[dict]:
    try:
        import EventKit  # type: ignore[import]
    except ImportError:
        raise RuntimeError(
            "pyobjc-framework-EventKit is not installed. "
            "Run: pip install pyobjc-framework-EventKit"
        )

    store = EventKit.EKEventStore.alloc().init()  # type: ignore[attr-defined]
    if not _request_eventkit_access(store):
        raise RuntimeError(
            "Calendar access denied. "
            "Go to System Settings -> Privacy & Security -> Calendars "
            "and enable access for this application, then try again."
        )

    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
        _dt_to_nsdate(start_dt),
        _dt_to_nsdate(end_dt),
        None,
    )
    ek_events = store.eventsMatchingPredicate_(predicate) or []

    results = []
    for ev in ek_events:
        cal = ev.calendar()
        results.append(
            {
                "external_id": str(ev.eventIdentifier() or ""),
                "calendar_name": str(cal.title()) if cal else "",
                "title": str(ev.title() or "(no title)"),
                "start_at": _nsdate_to_iso(ev.startDate()),
                "end_at": _nsdate_to_iso(ev.endDate()),
                "location": str(ev.location() or ""),
            }
        )

    return sorted(results, key=lambda e: e["start_at"])


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool(approval_mode="never_require")
def create_calendar_event(
    title: Annotated[str, Field(description="Short title for the event.")],
    start_at: Annotated[str, Field(description="Event start in ISO-8601, e.g. 2026-04-20T09:00:00.")],
    end_at: Annotated[str, Field(description="Event end in ISO-8601, e.g. 2026-04-20T10:00:00.")],
    location: Annotated[str, Field(description="Optional location.")] = "",
    notes: Annotated[str, Field(description="Optional notes.")] = "",
    recurrence: Annotated[
        str,
        Field(description="Recurrence pattern: none, daily, specific_days, weekly, biweekly, monthly, yearly."),
    ] = "none",
    recurrence_days: Annotated[
        str,
        Field(description="Required when recurrence is 'specific_days'. Comma-separated weekdays, e.g. MON,WED,FRI."),
    ] = "",
) -> str:
    """Create a calendar event and store it in Redis."""
    title = title.strip()
    if not title:
        return "Event title cannot be empty."
    if not start_at.strip() or not end_at.strip():
        return "start_at and end_at are required."

    err = _validate_recurrence(recurrence, recurrence_days)
    if err:
        return err

    start_at = start_at.strip()
    end_at = end_at.strip()

    repo = get_calendar_repository()
    existing_id = repo.get_event_dedup(title, start_at)
    if existing_id:
        return (
            f"Duplicate: an event titled '{title}' already exists at {start_at} "
            f"(id: {existing_id}). Use a different title or time."
        )

    now = datetime.now(timezone.utc).isoformat()
    event_id = repo.unique_event_id(title)
    days = ",".join(d.strip().upper() for d in recurrence_days.split(",") if d.strip())

    data = {
        "id": event_id, "title": title, "start_at": start_at, "end_at": end_at,
        "location": location.strip(), "notes": notes.strip(),
        "recurrence": recurrence, "recurrence_days": days,
        "source": "local", "external_id": "", "calendar_name": "", "created_at": now,
    }

    repo.save_event(data)
    repo.set_event_dedup(title, start_at, event_id)

    return f"Created event '{event_id}'."


@tool(approval_mode="never_require")
def search_calendar(
    query: Annotated[
        str,
        Field(description="Keyword to match event title, location, or notes. Leave empty to list all."),
    ] = "",
    from_date: Annotated[
        str,
        Field(description="Optional start date filter in YYYY-MM-DD or ISO-8601 format."),
    ] = "",
    to_date: Annotated[
        str,
        Field(description="Optional end date filter in YYYY-MM-DD or ISO-8601 format."),
    ] = "",
    max_results: Annotated[
        int,
        Field(description="Maximum events to return. Must be between 1 and 50."),
    ] = 10,
) -> str:
    """Search calendar events stored in Redis."""
    max_results = max(1, min(max_results, 50))
    keyword = query.strip().lower()
    from_d = from_date.strip()
    to_d = to_date.strip()

    repo = get_calendar_repository()
    all_ids = repo.list_event_ids()

    matches = []
    for eid in all_ids:
        ev = repo.get_event(eid)
        if not ev:
            continue
        if from_d and ev["start_at"] < from_d:
            continue
        if to_d and ev["start_at"] > to_d:
            continue
        if keyword and not (
            keyword in ev["title"].lower()
            or keyword in ev["location"].lower()
            or keyword in ev["notes"].lower()
        ):
            continue
        matches.append(ev)
        if len(matches) >= max_results:
            break

    if not matches:
        return "No events found."

    lines = [f"Found {len(matches)} event(s):"]
    for ev in matches:
        recur = f" [{ev['recurrence']}]" if ev["recurrence"] != "none" else ""
        cal = f" ({ev['calendar_name']})" if ev["calendar_name"] else ""
        loc = f" | {ev['location']}" if ev["location"] else ""
        lines.append(f"- {ev['id']}: {ev['title']}{cal} | {ev['start_at']} -> {ev['end_at']}{loc}{recur}")

    return "\n".join(lines)


@tool(approval_mode="never_require")
def sync_calendar(
    days_ahead: Annotated[
        int,
        Field(description="How many days ahead to sync from now. Must be between 1 and 7."),
    ] = 5,
) -> str:
    """Sync events from macOS Calendar for the next N days into Redis. Skips duplicates."""
    days_ahead = max(1, min(days_ahead, 7))
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)

    try:
        system_events = _fetch_system_events(start_dt=now, end_dt=end)
    except RuntimeError as exc:
        return str(exc)

    if not system_events:
        return f"No events found in the macOS Calendar for the next {days_ahead} day(s)."

    added = 0
    skipped = 0
    db_now = now.isoformat()
    repo = get_calendar_repository()

    for ev in system_events:
        # Dedup by external_id (preferred) or by (title, start_at)
        if ev["external_id"]:
            exists = repo.event_extid_exists(ev["external_id"])
        else:
            exists = repo.event_dedup_exists(ev["title"], ev["start_at"])

        if exists:
            skipped += 1
            continue

        event_id = repo.unique_event_id(ev["title"])
        data = {
            "id": event_id, "title": ev["title"],
            "start_at": ev["start_at"], "end_at": ev["end_at"],
            "location": ev["location"], "notes": "",
            "recurrence": "none", "recurrence_days": "",
            "source": "system", "external_id": ev["external_id"],
            "calendar_name": ev["calendar_name"], "created_at": db_now,
        }

        repo.save_event(data)
        if ev["external_id"]:
            repo.set_event_extid(ev["external_id"], event_id)
        else:
            repo.set_event_dedup(ev["title"], ev["start_at"], event_id)
        added += 1

    return (
        f"Sync complete: {added} new event(s) added, {skipped} duplicate(s) skipped "
        f"(next {days_ahead} day(s))."
    )


@tool(approval_mode="never_require")
def create_reminder(
    title: Annotated[str, Field(description="Short title for the reminder.")],
    start_at: Annotated[str, Field(description="When the reminder becomes active, in ISO-8601 format.")],
    end_at: Annotated[str, Field(description="When the reminder fires/is due, in ISO-8601 format.")],
    notes: Annotated[str, Field(description="Optional notes.")] = "",
    recurrence: Annotated[
        str,
        Field(description="Recurrence pattern: none, daily, specific_days, weekly, biweekly, monthly, yearly."),
    ] = "none",
    recurrence_days: Annotated[
        str,
        Field(description="Required when recurrence is 'specific_days'. Comma-separated weekdays, e.g. MON,WED,FRI."),
    ] = "",
) -> str:
    """Create a reminder and store it in Redis."""
    title = title.strip()
    if not title:
        return "Reminder title cannot be empty."
    if not start_at.strip() or not end_at.strip():
        return "start_at and end_at are required."

    err = _validate_recurrence(recurrence, recurrence_days)
    if err:
        return err

    start_at = start_at.strip()
    end_at = end_at.strip()

    repo = get_calendar_repository()
    existing_id = repo.get_reminder_dedup(title, end_at)
    if existing_id:
        return (
            f"Duplicate: a reminder titled '{title}' already exists due at {end_at} "
            f"(id: {existing_id}). Use a different title or due time."
        )

    now = datetime.now(timezone.utc).isoformat()
    reminder_id = repo.unique_reminder_id(title)
    days = ",".join(d.strip().upper() for d in recurrence_days.split(",") if d.strip())

    data = {
        "id": reminder_id, "title": title,
        "start_at": start_at, "end_at": end_at,
        "notes": notes.strip(), "recurrence": recurrence,
        "recurrence_days": days, "created_at": now,
    }

    repo.save_reminder(data)
    repo.set_reminder_dedup(title, end_at, reminder_id)

    return f"Created reminder '{reminder_id}'."


@tool(approval_mode="never_require")
def list_reminders(
    max_results: Annotated[
        int,
        Field(description="Maximum reminders to return. Must be between 1 and 50."),
    ] = 20,
) -> str:
    """List all reminders stored in Redis, ordered by due date."""
    max_results = max(1, min(max_results, 50))

    repo = get_calendar_repository()
    ids = repo.list_reminder_ids(0, max_results - 1)

    if not ids:
        return "No reminders found."

    lines = [f"Found {len(ids)} reminder(s):"]
    for rid in ids:
        rem = repo.get_reminder(rid)
        if not rem:
            continue
        recur = f" [{rem['recurrence']}]" if rem["recurrence"] != "none" else ""
        lines.append(f"- {rem['id']}: {rem['title']} | due {rem['end_at']}{recur}")

    return "\n".join(lines)


@tool(approval_mode="never_require")
def delete_calendar_event(
    event_id: Annotated[
        str,
        Field(description="Event id, typically from search_calendar results."),
    ]
) -> str:
    """Delete a calendar event from Redis by id."""
    safe_id = _slugify(event_id)
    repo = get_calendar_repository()
    if not repo.event_exists(safe_id):
        return f"No event found with id '{safe_id}'."
    repo.delete_event(safe_id)
    return f"Deleted event '{safe_id}'."


@tool(approval_mode="never_require")
def delete_reminder(
    reminder_id: Annotated[
        str,
        Field(description="Reminder id, typically from list_reminders results."),
    ]
) -> str:
    """Delete a reminder from Redis by id."""
    safe_id = _slugify(reminder_id)
    repo = get_calendar_repository()
    if not repo.reminder_exists(safe_id):
        return f"No reminder found with id '{safe_id}'."
    repo.delete_reminder(safe_id)
    return f"Deleted reminder '{safe_id}'."
