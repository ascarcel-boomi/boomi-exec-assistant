#!/usr/bin/env python3
"""One-shot task runner — run any EA task manually from the command line.

Examples:
  python3 cli.py --email adam.scarcella@boomi.com --task morning_brief
  python3 cli.py --email adam.scarcella@boomi.com --task email_triage --dry-run
  python3 cli.py --email adam.scarcella@boomi.com --task pre_meeting_brief
  python3 cli.py --email adam.scarcella@boomi.com --task action_tracker
  python3 cli.py --email adam.scarcella@boomi.com --task eod_digest
"""

import argparse
import sys

from ea.config import load_user_config
from ea.context import build_user_context
from ea.tasks import morning_brief, email_triage, pre_meeting_brief, action_tracker, eod_digest
from ea.tasks import claude_usage_report, daily_ticket_brief

TASK_MAP = {
    "morning_brief": morning_brief.run,
    "email_triage": email_triage.run,
    "pre_meeting_brief": pre_meeting_brief.run,
    "action_tracker": action_tracker.run,
    "eod_digest": eod_digest.run,
    "daily_ticket_brief": daily_ticket_brief.run,
    "claude_usage_daily": claude_usage_report.run_daily,
    "claude_usage_weekly": claude_usage_report.run_weekly,
}


def main():
    parser = argparse.ArgumentParser(description="Boomi Executive Assistant — one-shot task runner")
    parser.add_argument("--email", required=True, help="Your Boomi email address")
    parser.add_argument(
        "--task",
        required=True,
        choices=list(TASK_MAP.keys()),
        help="Task to run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print output only — do not send emails",
    )
    args = parser.parse_args()

    try:
        cfg = load_user_config(args.email)
        ctx = build_user_context(cfg)
        TASK_MAP[args.task](cfg=cfg, dry_run=args.dry_run, **ctx)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
