import time
from datetime import datetime, timedelta, timezone
from typing import Annotated

from agent_framework import tool
from pydantic import Field

# Reference epoch for NSDate <-> datetime conversion
_NS_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)


def _dt_to_nsdate(dt: datetime):
    from Foundation import NSDate  # type: ignore[import]

    secs = (dt.astimezone(timezone.utc) - _NS_EPOCH).total_seconds()
    return NSDate.dateWithTimeIntervalSinceReferenceDate_(secs)


def _nsdate_to_iso(nsdate) -> str:
    if nsdate is None:
        return ""
    secs = float(nsdate.timeIntervalSinceReferenceDate())
    return (_NS_EPOCH + timedelta(seconds=secs)).isoformat()


def _request_eventkit_access(store) -> bool:
    """Request calendar access and block until macOS grants or denies it."""
    import EventKit  # type: ignore[import]
    from Foundation import NSDate, NSRunLoop  # type: ignore[import]

    result: dict = {"granted": False, "done": False}

    def callback(granted, error):
        result["granted"] = bool(granted)
        result["done"] = True

    # macOS 14+ (Sonoma) requires requestFullAccessToEventsWithCompletion_
    if hasattr(store, "requestFullAccessToEventsWithCompletion_"):
        store.requestFullAccessToEventsWithCompletion_(callback)
    else:
        store.requestAccessToEntityType_completion_(EventKit.EKEntityTypeEvent, callback)

    # Spin the run loop so the async callback fires on this thread
    deadline = time.time() + 15
    while not result["done"] and time.time() < deadline:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))

    return result["granted"]


def _fetch_events(start_dt: datetime, end_dt: datetime) -> list[dict[str, str]]:
    """Fetch calendar events via the native macOS EventKit framework."""
    try:
        import EventKit  # type: ignore[import]
    except ImportError:
        raise RuntimeError(
            "pyobjc-framework-EventKit is not installed. "
            "Run: pip install pyobjc-framework-EventKit"
        )

    store = EventKit.EKEventStore.alloc().init()

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

    events: list[dict[str, str]] = []
    for ev in ek_events:
        cal = ev.calendar()
        events.append(
            {
                "calendar": str(cal.title()) if cal else "Unknown",
                "title": str(ev.title() or "(no title)"),
                "start": _nsdate_to_iso(ev.startDate()),
                "end": _nsdate_to_iso(ev.endDate()),
                "location": str(ev.location() or ""),
            }
        )

    events.sort(key=lambda e: e["start"])
    return events


@tool(approval_mode="never_require")
def search_local_calendar(
    query: Annotated[
        str,
        Field(description="Optional keyword to match event title, location, or calendar name."),
    ] = "",
    days_ahead: Annotated[
        int,
        Field(description="How many days ahead to search from now. Must be between 1 and 365."),
    ] = 30,
    max_results: Annotated[
        int,
        Field(description="Maximum number of matching events to return. Must be between 1 and 50."),
    ] = 10,
) -> str:
    """Search upcoming events from the local macOS Calendar app using the native EventKit API."""
    days_ahead = max(1, min(days_ahead, 365))
    max_results = max(1, min(max_results, 50))

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)

    try:
        events = _fetch_events(start_dt=now, end_dt=end)
    except RuntimeError as exc:
        return str(exc)

    if not events:
        return f"No upcoming events found in the next {days_ahead} days."

    keyword = query.strip().lower()
    if keyword:
        events = [
            event
            for event in events
            if keyword in event["title"].lower()
            or keyword in event["location"].lower()
            or keyword in event["calendar"].lower()
        ]

    if not events:
        return f"No events matched '{query}' in the next {days_ahead} days."

    lines = [f"Found {min(len(events), max_results)} event(s):"]
    for event in events[:max_results]:
        location = event["location"] if event["location"] else "(no location)"
        lines.append(
            f"- [{event['calendar']}] {event['title']} | "
            f"{event['start']} -> {event['end']} | {location}"
        )

    return "\n".join(lines)
