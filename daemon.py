#!/usr/bin/env python3
"""Executive Assistant daemon — runs all scheduled tasks for all configured users."""

import argparse
import logging
import os
import sys

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ea import tasks
from ea.config import load_user_config, list_configured_users
from ea.context import build_user_context
from ea.tasks import morning_brief, email_triage, pre_meeting_brief, action_tracker, eod_digest
from ea.tasks import claude_usage_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def _within_working_hours(cfg) -> bool:
    """Return True if current local time is within user's working hours."""
    import pytz
    from datetime import datetime
    tz = pytz.timezone(cfg.timezone)
    now = datetime.now(tz)
    sh, sm = (int(x) for x in cfg.working_hours_start.split(":"))
    eh, em = (int(x) for x in cfg.working_hours_end.split(":"))
    start_minutes = sh * 60 + sm
    end_minutes = eh * 60 + em
    now_minutes = now.hour * 60 + now.minute
    return start_minutes <= now_minutes <= end_minutes


def _guarded_run(task_fn, cfg, ctx, dry_run: bool):
    """Wrap task execution with error handling."""
    try:
        task_fn(cfg=cfg, dry_run=dry_run, **ctx)
    except Exception as e:
        log.error(f"Task {task_fn.__module__} failed for {cfg.email}: {e}", exc_info=True)


def _guarded_run_working_hours(task_fn, cfg, ctx, dry_run: bool):
    """Only run if within working hours."""
    if not _within_working_hours(cfg):
        return
    _guarded_run(task_fn, cfg, ctx, dry_run)


def build_scheduler(emails: list, dry_run: bool = False) -> BlockingScheduler:
    scheduler = BlockingScheduler()

    for email in emails:
        cfg = load_user_config(email)
        ctx = build_user_context(cfg)
        tz = pytz.timezone(cfg.timezone)

        log.info(f"Scheduling tasks for {cfg.display_name} ({cfg.email}) in {cfg.timezone}")

        # Task 1: Morning Brief — daily at configured time
        h, m = (int(x) for x in cfg.morning_brief_time.split(":"))
        scheduler.add_job(
            _guarded_run,
            CronTrigger(hour=h, minute=m, timezone=tz),
            args=[morning_brief.run, cfg, ctx, dry_run],
            id=f"morning_brief_{email}",
            name=f"Morning Brief [{email}]",
            misfire_grace_time=300,
        )

        # Task 2: Email Triage — every N minutes during working hours
        scheduler.add_job(
            _guarded_run_working_hours,
            IntervalTrigger(minutes=cfg.email_triage_interval_minutes, timezone=tz),
            args=[email_triage.run, cfg, ctx, dry_run],
            id=f"email_triage_{email}",
            name=f"Email Triage [{email}]",
            misfire_grace_time=120,
        )

        # Task 3: Pre-Meeting Brief — every 5 min during working hours
        scheduler.add_job(
            _guarded_run_working_hours,
            IntervalTrigger(minutes=5, timezone=tz),
            args=[pre_meeting_brief.run, cfg, ctx, dry_run],
            id=f"pre_meeting_{email}",
            name=f"Pre-Meeting [{email}]",
            misfire_grace_time=60,
        )

        # Task 4: Action Tracker — noon + 30 min before EOD
        eod_h, eod_m = (int(x) for x in cfg.eod_digest_time.split(":"))
        pre_eod_m = max(0, eod_m - 30)
        for run_h, run_m, suffix in [(12, 0, "noon"), (eod_h, pre_eod_m, "pre_eod")]:
            scheduler.add_job(
                _guarded_run,
                CronTrigger(hour=run_h, minute=run_m, timezone=tz),
                args=[action_tracker.run, cfg, ctx, dry_run],
                id=f"action_tracker_{email}_{suffix}",
                name=f"Action Tracker {suffix} [{email}]",
                misfire_grace_time=300,
            )

        # Task 5: EOD Digest — daily at configured time
        scheduler.add_job(
            _guarded_run,
            CronTrigger(hour=eod_h, minute=eod_m, timezone=tz),
            args=[eod_digest.run, cfg, ctx, dry_run],
            id=f"eod_digest_{email}",
            name=f"EOD Digest [{email}]",
            misfire_grace_time=300,
        )

        # Task 6: Claude Usage — daily morning (5 min after morning brief)
        usage_h, usage_m = h, (m + 5) % 60
        if m + 5 >= 60:
            usage_h = (h + 1) % 24
        scheduler.add_job(
            _guarded_run,
            CronTrigger(hour=usage_h, minute=usage_m, timezone=tz),
            args=[claude_usage_report.run_daily, cfg, ctx, dry_run],
            id=f"claude_usage_daily_{email}",
            name=f"Claude Usage Daily [{email}]",
            misfire_grace_time=300,
        )

        # Task 7: Claude Usage — weekly Friday EOD summary
        scheduler.add_job(
            _guarded_run,
            CronTrigger(day_of_week="fri", hour=eod_h, minute=eod_m, timezone=tz),
            args=[claude_usage_report.run_weekly, cfg, ctx, dry_run],
            id=f"claude_usage_weekly_{email}",
            name=f"Claude Usage Weekly [{email}]",
            misfire_grace_time=300,
        )

    return scheduler


def main():
    parser = argparse.ArgumentParser(description="Boomi Executive Assistant Daemon")
    parser.add_argument(
        "--email",
        nargs="+",
        help="Email(s) to run for. Defaults to all configured users.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print output to stdout only — do not send emails.",
    )
    args = parser.parse_args()

    emails = args.email or list_configured_users()
    if not emails:
        print("No configured users found. Run: python3 setup.py --email you@boomi.com")
        sys.exit(1)

    log.info(f"Starting EA daemon for {len(emails)} user(s): {', '.join(emails)}")
    scheduler = build_scheduler(emails, dry_run=args.dry_run)

    print(f"\nDaemon running. Scheduled jobs:")
    for job in scheduler.get_jobs():
        print(f"  • {job.name}")
    print("\nPress Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("Daemon stopped.")


if __name__ == "__main__":
    main()
