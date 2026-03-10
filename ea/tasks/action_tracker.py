"""Task 4: Action Item Tracker — extract commitments from emails and completed meetings."""

import json
from datetime import datetime, timezone


def run(cfg, gmail, calendar, claude, deliverer, state, dry_run: bool = False) -> None:
    print("[action_tracker] Running...")
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    emails = gmail.get_messages_since(since, max_results=cfg.max_emails_per_triage)

    events = calendar.get_events_today(cfg.timezone)
    now = datetime.now(timezone.utc)
    past_events = [e for e in events if e.get("end") and e["end"] < now and not e["is_all_day"]]

    now_str = now.strftime("%A, %B %d %Y %H:%M UTC")
    system, user_msg = claude.action_tracker_prompt(cfg, emails, past_events, now_str)
    raw = claude.complete(system, user_msg)

    new_items = _parse_action_items(raw)
    if new_items:
        state.append_action_items(new_items)
        print(f"[action_tracker] Added {len(new_items)} new action item(s).")
    else:
        print("[action_tracker] No new action items found.")

    state.set_last_run("action_tracker")

    all_items = state.get_action_items()
    deliverer.deliver(
        subject=f"Action Items — {now.strftime('%b %d %H:%M')}",
        body=_format_action_items(all_items),
        task_name="action_tracker",
        dry_run=dry_run,
    )
    print("[action_tracker] Done.")


def _parse_action_items(raw: str) -> list:
    """Extract JSON array from Claude's response."""
    raw = raw.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        items = json.loads(raw)
        return items if isinstance(items, list) else []
    except (json.JSONDecodeError, ValueError):
        return []


def _format_action_items(items: list) -> str:
    if not items:
        return "No action items tracked today."

    by_type = {}
    for item in items:
        t = item.get("type", "follow_up")
        by_type.setdefault(t, []).append(item)

    labels = {
        "commit_made": "Commitments You Made",
        "commit_received": "Waiting On Others",
        "follow_up": "Follow-Ups Needed",
        "decision_needed": "Decisions Needed",
    }

    lines = []
    for type_key, label in labels.items():
        group = by_type.get(type_key, [])
        if not group:
            continue
        lines.append(f"\n## {label}")
        for item in group:
            owner = item.get("owner", "")
            due = item.get("due", "")
            source = item.get("source", "")
            lines.append(f"• {item.get('item', '')}")
            meta = " | ".join(filter(None, [f"Owner: {owner}" if owner else "", f"Due: {due}" if due else "", f"From: {source}" if source else ""]))
            if meta:
                lines.append(f"  {meta}")

    return "\n".join(lines).strip()
