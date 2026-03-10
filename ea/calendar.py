"""Google Calendar API wrapper."""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import pytz


def _parse_event(event: dict) -> dict:
    """Normalize a Google Calendar event into a clean dict."""
    start = event.get("start", {})
    end = event.get("end", {})

    # Handle all-day events (date) vs timed events (dateTime)
    start_str = start.get("dateTime") or start.get("date", "")
    end_str = end.get("dateTime") or end.get("date", "")

    is_all_day = "dateTime" not in start

    def parse_dt(s: str) -> Optional[datetime]:
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None

    start_dt = parse_dt(start_str)
    end_dt = parse_dt(end_str)
    duration = None
    if start_dt and end_dt and not is_all_day:
        duration = int((end_dt - start_dt).total_seconds() / 60)

    attendees = [
        {
            "email": a.get("email", ""),
            "name": a.get("displayName", ""),
            "response": a.get("responseStatus", ""),
        }
        for a in event.get("attendees", [])
    ]

    return {
        "id": event.get("id", ""),
        "summary": event.get("summary", "(No title)"),
        "description": (event.get("description") or "")[:500],
        "start": start_dt,
        "end": end_dt,
        "start_str": start_str,
        "end_str": end_str,
        "is_all_day": is_all_day,
        "duration_minutes": duration,
        "attendees": attendees,
        "hangout_link": event.get("hangoutLink") or event.get("htmlLink", ""),
        "location": event.get("location", ""),
        "organizer": (event.get("organizer") or {}).get("email", ""),
        "status": event.get("status", ""),
    }


class CalendarClient:
    def __init__(self, service):
        self.service = service

    def _get_events(self, time_min: datetime, time_max: datetime) -> List[dict]:
        result = (
            self.service.events()
            .list(
                calendarId="primary",
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=50,
            )
            .execute()
        )
        return [_parse_event(e) for e in result.get("items", [])]

    def get_events_today(self, user_timezone: str) -> List[dict]:
        tz = pytz.timezone(user_timezone)
        now = datetime.now(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self._get_events(
            start.astimezone(timezone.utc),
            end.astimezone(timezone.utc),
        )

    def get_events_tomorrow(self, user_timezone: str) -> List[dict]:
        tz = pytz.timezone(user_timezone)
        now = datetime.now(tz)
        start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self._get_events(
            start.astimezone(timezone.utc),
            end.astimezone(timezone.utc),
        )

    def get_events_in_range(self, start: datetime, end: datetime) -> List[dict]:
        return self._get_events(start, end)

    def get_next_event(self) -> Optional[dict]:
        now = datetime.now(timezone.utc)
        events = self._get_events(now, now + timedelta(hours=24))
        for e in events:
            if e["start"] and e["start"] > now and not e["is_all_day"]:
                return e
        return None

    def get_events_starting_within(self, minutes: int) -> List[dict]:
        """Events that start between now and now+minutes."""
        now = datetime.now(timezone.utc)
        window_end = now + timedelta(minutes=minutes)
        events = self._get_events(now, window_end + timedelta(minutes=1))
        return [
            e for e in events
            if e["start"] and now <= e["start"] <= window_end and not e["is_all_day"]
        ]
