#!/usr/bin/env python3
"""First-time setup wizard — configure a new user and run the OAuth flow."""

import argparse
import os
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).parent
CONFIG_DIR = ROOT / "config"
TOKENS_DIR = ROOT / "tokens"
SECRETS_PATH = CONFIG_DIR / "client_secrets.json"


def prompt(msg: str, default: str = "") -> str:
    if default:
        val = input(f"{msg} [{default}]: ").strip()
        return val if val else default
    return input(f"{msg}: ").strip()


def check_secrets():
    if not SECRETS_PATH.exists():
        print(f"\n❌  client_secrets.json not found at {SECRETS_PATH}")
        print(
            "\nTo get it:\n"
            "  1. Go to https://console.cloud.google.com/apis/credentials\n"
            "  2. Create an OAuth 2.0 Client ID (Desktop App type)\n"
            "  3. Enable: Gmail API + Google Calendar API\n"
            "  4. Download the JSON and save it to config/client_secrets.json\n"
        )
        sys.exit(1)
    print("✅  client_secrets.json found.")


def interactive_config(email: str) -> dict:
    print(f"\n[2/4] Creating user config for {email}")
    name_default = " ".join(p.capitalize() for p in email.split("@")[0].split("."))
    display_name = prompt("  Display name", name_default)
    timezone = prompt("  Timezone", "America/New_York")
    morning = prompt("  Morning brief time (HH:MM)", "07:30")
    eod = prompt("  EOD digest time (HH:MM)", "17:30")
    interval = prompt("  Email triage interval (minutes)", "60")
    deliver_email = prompt("  Deliver results to your Gmail inbox? (y/n)", "y").lower() == "y"

    return {
        "email": email,
        "display_name": display_name,
        "timezone": timezone,
        "morning_brief_time": morning,
        "eod_digest_time": eod,
        "email_triage_interval_minutes": int(interval),
        "pre_meeting_lookback_minutes": 15,
        "max_emails_per_triage": 50,
        "calendar_lookahead_hours": 24,
        "deliver_to_email": deliver_email,
        "deliver_to_stdout": True,
        "working_hours_start": "07:00",
        "working_hours_end": "19:00",
    }


def write_user_config(config: dict):
    users_dir = CONFIG_DIR / "users"
    users_dir.mkdir(parents=True, exist_ok=True)
    name = config["email"].split("@")[0]
    path = users_dir / f"{name}.yaml"
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    print(f"  Config saved: {path}")


def smoke_test(email: str, creds):
    print("\n[4/4] Running smoke test...")
    try:
        from ea.auth import build_gmail_service, build_calendar_service
        gmail_svc = build_gmail_service(creds)
        profile = gmail_svc.users().getProfile(userId="me").execute()
        print(f"  ✅  Gmail: OK ({profile.get('messagesTotal', '?')} messages, {profile.get('emailAddress')})")
    except Exception as e:
        print(f"  ❌  Gmail: {e}")

    try:
        cal_svc = build_calendar_service(creds)
        now_str = __import__("datetime").datetime.utcnow().isoformat() + "Z"
        cal_svc.events().list(calendarId="primary", maxResults=1, timeMin=now_str, singleEvents=True).execute()
        print("  ✅  Calendar: OK")
    except Exception as e:
        print(f"  ❌  Calendar: {e}")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            print("  ✅  Claude API: OK")
        except Exception as e:
            print(f"  ❌  Claude API: {e}")
    else:
        print("  ⚠️   Claude API: ANTHROPIC_API_KEY not set — set it before running the daemon")


def main():
    parser = argparse.ArgumentParser(description="Boomi Executive Assistant — first-time setup")
    parser.add_argument("--email", required=True, help="Your Boomi email address")
    args = parser.parse_args()

    print(f"\n=== Boomi Executive Assistant Setup ===\n")

    print("[1/4] Checking prerequisites...")
    check_secrets()

    config = interactive_config(args.email)
    write_user_config(config)

    print(f"\n[3/4] Starting Google OAuth2 flow for {args.email}...")
    print("  A browser window will open. Sign in as", args.email, "and grant permissions.")
    from ea.auth import run_oauth_flow
    creds = run_oauth_flow(args.email, TOKENS_DIR, SECRETS_PATH)
    print(f"  ✅  Token saved to tokens/{args.email}.json")

    smoke_test(args.email, creds)

    print(f"""
=== Setup complete! ===

Run a task now:
  python3 cli.py --email {args.email} --task morning_brief --dry-run

Start the scheduled daemon:
  python3 daemon.py --email {args.email}

Run the daemon for all configured users:
  python3 daemon.py
""")


if __name__ == "__main__":
    main()
