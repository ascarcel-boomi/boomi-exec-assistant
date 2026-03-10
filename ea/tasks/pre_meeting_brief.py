"""Task 3: Pre-Meeting Brief — context brief fired before each calendar event."""

from datetime import datetime, timedelta, timezone


def run(cfg, gmail, calendar, claude, deliverer, state, dry_run: bool = False) -> None:
    events = calendar.get_events_starting_within(cfg.pre_meeting_lookback_minutes)
    if not events:
        return  # quiet exit — this runs every 5 min

    now_str = datetime.now(timezone.utc).strftime("%A, %B %d %Y %H:%M UTC")

    for event in events:
        state_key = f"pre_meeting_{event['id']}"
        if state.get_last_run(state_key):
            continue  # already sent for this event

        print(f"[pre_meeting] Preparing brief for: {event['summary']}")

        # Search emails related to attendees and event title
        attendee_emails = [a["email"] for a in event.get("attendees", []) if a.get("email")]
        title_words = " ".join(event.get("summary", "").split()[:4])
        parts = attendee_emails[:4] + ([title_words] if title_words else [])
        query = " OR ".join(f'"{p}"' for p in parts) if parts else ""

        since = datetime.now(timezone.utc) - timedelta(days=7)
        related_emails = gmail.get_messages_since(since, max_results=15, query=query or None)

        system, user_msg = claude.pre_meeting_prompt(cfg, event, related_emails, now_str)
        brief = claude.complete(system, user_msg)

        state.set_last_run(state_key)
        deliverer.deliver(
            subject=f"Pre-Meeting: {event['summary']}",
            body=brief,
            task_name="pre_meeting_brief",
            dry_run=dry_run,
        )
        print(f"[pre_meeting] Done for: {event['summary']}")
