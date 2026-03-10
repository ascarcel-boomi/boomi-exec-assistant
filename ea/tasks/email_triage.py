"""Task 2: Email Triage — incremental inbox prioritization."""

from datetime import datetime, timedelta, timezone


def run(cfg, gmail, calendar, claude, deliverer, state, dry_run: bool = False) -> None:
    print("[email_triage] Running...")
    history_id = state.get_last_history_id()

    if history_id:
        emails = gmail.get_messages_since_history_id(history_id, max_results=cfg.max_emails_per_triage)
    else:
        since = datetime.now(timezone.utc) - timedelta(hours=cfg.email_triage_interval_minutes / 60 * 2)
        emails = gmail.get_messages_since(since, max_results=cfg.max_emails_per_triage)

    if not emails:
        print("[email_triage] No new emails — skipping.")
        state.set_last_history_id(gmail.get_history_id())
        return

    print(f"[email_triage] Triaging {len(emails)} email(s)...")
    new_history_id = gmail.get_history_id()
    now_str = datetime.now(timezone.utc).strftime("%A, %B %d %Y %H:%M UTC")

    system, user_msg = claude.email_triage_prompt(cfg, emails, now_str)
    triage = claude.complete(system, user_msg)

    state.set_last_history_id(new_history_id)
    state.set_last_run("email_triage")

    deliverer.deliver(
        subject=f"Email Triage — {datetime.now().strftime('%b %d %H:%M')}",
        body=triage,
        task_name="email_triage",
        dry_run=dry_run,
    )
    print("[email_triage] Done.")
