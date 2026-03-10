"""Task 5: EOD Digest — day recap, pending items, tomorrow preview."""

from datetime import datetime, timezone


def run(cfg, gmail, calendar, claude, deliverer, state, dry_run: bool = False) -> None:
    # Idempotency: skip if already ran today
    last = state.get_last_run("eod_digest")
    today = datetime.now(timezone.utc).date()
    if last and last.date() == today:
        print(f"[eod_digest] Already ran today at {last.strftime('%H:%M UTC')} — skipping.")
        return

    print("[eod_digest] Running...")
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    emails = gmail.get_messages_since(since, max_results=cfg.max_emails_per_triage)
    events = calendar.get_events_today(cfg.timezone)
    action_items = state.get_action_items()
    tomorrow_events = calendar.get_events_tomorrow(cfg.timezone)
    now_str = datetime.now(timezone.utc).strftime("%A, %B %d %Y %H:%M UTC")

    system, user_msg = claude.eod_digest_prompt(
        cfg, events, emails, action_items, tomorrow_events, now_str
    )
    digest = claude.complete(system, user_msg)

    state.set_last_run("eod_digest")
    deliverer.deliver(
        subject=f"EOD Digest — {datetime.now().strftime('%A %b %d')}",
        body=digest,
        task_name="eod_digest",
        dry_run=dry_run,
    )
    print("[eod_digest] Done.")
