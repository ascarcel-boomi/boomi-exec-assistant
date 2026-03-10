"""Task 1: Morning Briefing — daily calendar + overnight email summary."""

from datetime import datetime, timedelta, timezone


def run(cfg, gmail, calendar, claude, deliverer, state, dry_run: bool = False) -> None:
    # Idempotency: skip if already ran today
    last = state.get_last_run("morning_brief")
    today = datetime.now(timezone.utc).date()
    if last and last.date() == today:
        print(f"[morning_brief] Already ran today at {last.strftime('%H:%M UTC')} — skipping.")
        return

    print("[morning_brief] Running...")
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=10)
    emails = gmail.get_messages_since(since, max_results=cfg.max_emails_per_triage)
    events = calendar.get_events_today(cfg.timezone)
    now_str = datetime.now(timezone.utc).strftime("%A, %B %d %Y %H:%M UTC")

    system, user_msg = claude.morning_brief_prompt(cfg, events, emails, now_str)
    brief = claude.complete(system, user_msg)

    state.set_last_run("morning_brief")
    deliverer.deliver(
        subject=f"Morning Brief — {datetime.now().strftime('%A %b %d')}",
        body=brief,
        task_name="morning_brief",
        dry_run=dry_run,
    )
    print("[morning_brief] Done.")
