# Boomi Executive Assistant

An AI-powered executive assistant that connects to your Boomi Google Workspace account (Gmail + Google Calendar) and performs the top 5 daily EA tasks — automatically, on a schedule.

Built with Claude AI (Anthropic) and designed for the Boomi management team. Each person authenticates their own Google account. No shared credentials.

---

## Quick Install (Claude Code CLI)

If you have [Claude Code](https://claude.ai/code) installed, just open it in any directory and say:

```
Download and install this boomi-exec-assistant https://github.com/ascarcel-boomi/boomi-exec-assistant
```

Claude will clone the repo, install dependencies, configure your Google auth, set up your Anthropic API key, and install the macOS background service — no manual steps required.

---

## Manual Install

```bash
git clone https://github.com/ascarcel-boomi/boomi-exec-assistant ~/github/boomi-exec-assistant
cd ~/github/boomi-exec-assistant
bash install.sh --email your.name@boomi.com
```

The installer handles everything: Python venv, dependencies, Google OAuth, Anthropic API key, and the launchd background service that starts automatically on login.

---

## What It Does

| Task | Schedule | Description |
|---|---|---|
| **Morning Brief** | Daily at your configured time | Calendar overview + overnight email summary + action items |
| **Email Triage** | Every 60 min (configurable) | Inbox prioritization (P1/P2/P3), suggested actions, reply drafts for urgent items |
| **Pre-Meeting Brief** | 15 min before each meeting | Attendee context, related email threads, suggested talking points |
| **Action Tracker** | Noon + 30 min before EOD | Extracts commitments made/received, follow-ups, deadlines from emails and completed meetings |
| **EOD Digest** | Daily at your configured time | Day recap, open items, "waiting on" list, tomorrow's preview, one priority |

Results are delivered to your Gmail inbox (as emails from yourself, tagged `[EA]`) and printed to stdout.

---

## Prerequisites

- Python 3.9+
- A Boomi Google Workspace account
- An [Anthropic API key](https://console.anthropic.com/)
- `config/client_secrets.json` — obtain from a team admin (one shared OAuth app for the whole team)

---

## Setup (per person, one time)

```bash
# 1. Clone the repo
git clone https://github.com/ascarcel-boomi/boomi-exec-assistant.git
cd boomi-exec-assistant

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-..."
# Add this to ~/.zshrc or ~/.bashrc to persist it

# 5. Get client_secrets.json from a team admin and place it at:
#    config/client_secrets.json

# 6. Run the setup wizard
python3 setup.py --email firstname.lastname@boomi.com
```

The setup wizard will:
1. Verify `client_secrets.json` exists
2. Prompt for your preferences (timezone, schedule times, etc.)
3. Open a browser for Google OAuth (sign in with your Boomi account)
4. Run a smoke test against Gmail, Calendar, and Claude API

---

## Running

### One-shot (test a task manually)
```bash
# Dry run — output to terminal only, no email sent
python3 cli.py --email you@boomi.com --task morning_brief --dry-run

# Live run — also sends to your Gmail
python3 cli.py --email you@boomi.com --task morning_brief

# All available tasks:
# morning_brief | email_triage | pre_meeting_brief | action_tracker | eod_digest
```

### Scheduled daemon
```bash
# Run for yourself
python3 daemon.py --email you@boomi.com

# Run for all users with a config file in config/users/
python3 daemon.py

# Dry run (no emails sent)
python3 daemon.py --dry-run
```

### Keep the daemon running (macOS launchd)
```bash
# Create a launchd plist — see docs/launchd-example.plist
launchctl load ~/Library/LaunchAgents/com.boomi.exec-assistant.plist
```

---

## Configuration

Each user has a YAML config at `config/users/<firstname>.<lastname>.yaml`.

Copy `config/users/example.yaml` and edit it. Key fields:

```yaml
email: you@boomi.com
display_name: Your Name
timezone: America/New_York

morning_brief_time: "07:30"
eod_digest_time: "17:30"
email_triage_interval_minutes: 60
pre_meeting_lookback_minutes: 15

deliver_to_email: true   # send [EA] emails to yourself
deliver_to_stdout: true  # also print to terminal
```

---

## Getting `client_secrets.json` (admin setup, one time)

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a project (e.g. "Boomi Exec Assistant")
3. Enable **Gmail API** and **Google Calendar API**
4. Create an **OAuth 2.0 Client ID** → Desktop App → Download JSON
5. Save the file as `config/client_secrets.json`
6. Share it with team members (out-of-band — it is gitignored)

> The `client_secrets.json` contains only the OAuth app credentials (not any user's token). It is safe to share within the team but should not be committed to git.

---

## Token Compatibility

If you already have a `google-workspace` MCP server token at
`~/.google_workspace_mcp/credentials/your@email.json`,
you can copy it directly to `tokens/your@email.json` to skip the OAuth flow:

```bash
cp ~/.google_workspace_mcp/credentials/adam.scarcella@boomi.com.json \
   tokens/adam.scarcella@boomi.com.json
```

The token formats are identical.

---

## Project Structure

```
boomi-exec-assistant/
├── setup.py              # First-time setup wizard
├── cli.py                # One-shot task runner
├── daemon.py             # APScheduler daemon
├── requirements.txt
├── config/
│   ├── client_secrets.json    # gitignored — get from team admin
│   └── users/
│       ├── example.yaml       # copy this for new users
│       └── adam.scarcella.yaml
├── tokens/               # gitignored — per-user OAuth tokens
├── state/                # gitignored — run timestamps, action items
└── ea/
    ├── auth.py           # Google OAuth2
    ├── gmail.py          # Gmail API wrapper
    ├── calendar.py       # Calendar API wrapper
    ├── claude.py         # Claude AI prompts and client
    ├── config.py         # User config loading
    ├── context.py        # Dependency wiring
    ├── delivery.py       # Output routing (email + stdout)
    ├── state.py          # Local state management
    └── tasks/
        ├── morning_brief.py
        ├── email_triage.py
        ├── pre_meeting_brief.py
        ├── action_tracker.py
        └── eod_digest.py
```
