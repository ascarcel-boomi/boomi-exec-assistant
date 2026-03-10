# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

An AI-powered executive assistant for Boomi managers. It connects to your Boomi Google Workspace account (Gmail + Google Calendar) and delivers 5 daily briefings via email and terminal — powered by Claude AI. It runs as a silent macOS background service.

## Installing for a New User

When someone asks you to "download and install" this project, perform these steps autonomously in order. Do not ask the user to run commands themselves unless you hit a blocker that requires their input (e.g. they need to paste a credential).

### Step 1 — Clone the repo

```bash
mkdir -p ~/github
git clone https://github.com/ascarcel-boomi/boomi-exec-assistant ~/github/boomi-exec-assistant
cd ~/github/boomi-exec-assistant
```

### Step 2 — Run the installer

```bash
bash install.sh --email <their-boomi-email>
```

If you don't know their email, check `git config user.email` or ask them once. The installer handles everything: Python venv, dependencies, user config (interactive prompts), Google auth, Anthropic API key, and the launchd background service.

### Step 3 — Verify it's running

```bash
launchctl list | grep exec-assistant   # should show a PID
tail -20 ~/exec-assistant.log          # should show "Scheduler started"
```

### Step 4 — Run a live test

```bash
cd ~/github/boomi-exec-assistant
source .venv/bin/activate
python3 cli.py --email <their-email> --task morning_brief --dry-run
```

This confirms Google auth and Claude API are both working. If it prints a morning brief, the install is complete.

---

## How the Installer Works (what to do if it fails)

The installer (`install.sh`) runs 8 steps:

1. **Python check** — requires Python 3.9+. If missing: `brew install python3`
2. **Repo check** — must already be cloned to `~/github/boomi-exec-assistant`
3. **Venv + deps** — creates `.venv/` and installs `requirements.txt`
4. **User config** — writes `config/users/<firstname>.<lastname>.yaml` with schedule and timezone
5. **Jira integration** — enables the daily ticket brief:
   - Auto-discovers `JIRA_API_TOKEN` from `~/.kiro/mcp_credentials/mcp-atlassian.env` or `~/.amazonq/mcp_credentials/mcp-atlassian.env`
   - Prompts for token if not found (skippable — brief is disabled until token is set)
   - Saves token to `~/.zshrc` and to the launchd plist environment
   - Prompts for Jira base URL (default: `https://boomii.atlassian.net`) and project keys (default: `CAMSRE,SRE`)
   - Appends Jira config block to user YAML
6. **Google auth** — tries these sources in order:
   - Copy existing MCP token from `~/.google_workspace_mcp/credentials/<email>.json` (preferred — no browser needed)
   - Run full OAuth flow using `config/client_secrets.json`
   - If neither exists: prompt user to get `client_secrets.json` from adam.scarcella@boomi.com
7. **Anthropic API key** — tries these sources in order:
   - macOS Keychain: `security find-generic-password -s "Claude Code" -w` (works if Claude Code CLI is installed)
   - `$ANTHROPIC_API_KEY` environment variable
   - Prompts the user to paste their key (get it from 1Password or IT)
   - Saves to `~/.zshrc` for future sessions
8. **launchd service** — writes `~/Library/LaunchAgents/com.boomi.exec-assistant.plist` and loads it

---

## Troubleshooting

### Google Calendar API not enabled
Error: `Google Calendar API has not been used in project <ID> before or it is disabled`
Fix: Visit the URL in the error message and click Enable. Wait 60 seconds and retry.

### Google auth token expired or missing scopes
```bash
rm ~/github/boomi-exec-assistant/tokens/<email>.json
# Re-copy MCP token or re-run OAuth:
cp ~/.google_workspace_mcp/credentials/<email>.json ~/github/boomi-exec-assistant/tokens/<email>.json
```

### No Anthropic API key
```bash
security find-generic-password -s "Claude Code" -w   # check Claude Code keychain
# If empty, ask IT for the key associated with: claude_code_key_<firstname>.<lastname>_<suffix>
# Then add to shell:
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.zshrc
# And update the plist:
launchctl unload ~/Library/LaunchAgents/com.boomi.exec-assistant.plist
# Edit the plist to update ANTHROPIC_API_KEY value, then:
launchctl load ~/Library/LaunchAgents/com.boomi.exec-assistant.plist
```

### Service not running
```bash
tail -50 ~/exec-assistant.log          # look for errors
launchctl unload ~/Library/LaunchAgents/com.boomi.exec-assistant.plist
launchctl load ~/Library/LaunchAgents/com.boomi.exec-assistant.plist
launchctl list | grep exec-assistant   # verify PID appears
```

### Jira daily ticket brief not appearing
The brief fires at your `morning_brief_time` only if `JIRA_API_TOKEN` is set and `jira_base_url` is in your user config.

**Check token:**
```bash
echo $JIRA_API_TOKEN   # must be non-empty in the daemon environment
```
If empty, the token may not be in the plist. Fix:
```bash
launchctl unload ~/Library/LaunchAgents/com.boomi.exec-assistant.plist
# Edit the plist: set JIRA_API_TOKEN value in EnvironmentVariables dict
launchctl load ~/Library/LaunchAgents/com.boomi.exec-assistant.plist
```

**Check config:**
```bash
grep jira ~/github/boomi-exec-assistant/config/users/<name>.yaml
# Should show jira_base_url and jira_project_keys
```
If missing, add to your YAML:
```yaml
jira_base_url: "https://boomii.atlassian.net"
jira_project_keys:
  - "CAMSRE"
  - "SRE"
```

**Test it manually:**
```bash
cd ~/github/boomi-exec-assistant && source .venv/bin/activate
python3 cli.py --email you@boomi.com --task daily_ticket_brief --dry-run
```

**Get a Jira token:** https://id.atlassian.com/manage-profile/security/api-tokens — choose "Create API token with scopes" and select Jira Read scopes.

---

### Missing client_secrets.json (only needed if no MCP token)
Get the file from adam.scarcella@boomi.com and place it at:
`~/github/boomi-exec-assistant/config/client_secrets.json`

---

## Managing the Service

```bash
# Stop
launchctl unload ~/Library/LaunchAgents/com.boomi.exec-assistant.plist

# Start
launchctl load ~/Library/LaunchAgents/com.boomi.exec-assistant.plist

# Restart
launchctl unload ~/Library/LaunchAgents/com.boomi.exec-assistant.plist && launchctl load ~/Library/LaunchAgents/com.boomi.exec-assistant.plist

# Watch live logs
tail -f ~/exec-assistant.log
```

---

## Running Tasks Manually

```bash
cd ~/github/boomi-exec-assistant
source .venv/bin/activate

python3 cli.py --email you@boomi.com --task morning_brief      # send to inbox
python3 cli.py --email you@boomi.com --task email_triage       # send to inbox
python3 cli.py --email you@boomi.com --task pre_meeting_brief  # fires if meeting within 15 min
python3 cli.py --email you@boomi.com --task action_tracker     # send to inbox
python3 cli.py --email you@boomi.com --task eod_digest         # send to inbox

# Add --dry-run to any command to print output without sending email
```

---

## What Each Task Does

| Task | When | What It Does |
|---|---|---|
| `morning_brief` | Daily at configured time (default 7:30 AM) | Today's calendar + overnight emails + action items → email |
| `daily_ticket_brief` | Daily at morning_brief_time (requires `JIRA_API_TOKEN`) | Prioritized Jira work plan: in-progress, overdue, sprint to-do, unplanned queue → email |
| `email_triage` | Every 60 min during working hours | Inbox P1/P2/P3 prioritization + reply suggestions → email |
| `pre_meeting_brief` | 15 min before each calendar event | Attendee context + related email threads + talking points → email |
| `action_tracker` | Noon + 30 min before EOD | Extract commitments/follow-ups from emails and meetings → email |
| `eod_digest` | Daily at configured time (default 5:30 PM) | Day recap + open items + tomorrow preview → email |

All results are sent to the user's own Gmail inbox as `[EA]` tagged emails with clickable Jira ticket links.

---

## Key Files

| File | Purpose |
|---|---|
| `install.sh` | Full automated installer — run this first |
| `daemon.py` | APScheduler daemon (managed by launchd — do not run manually) |
| `cli.py` | One-shot task runner for manual use |
| `config/users/<name>.yaml` | Per-user schedule and preference config |
| `tokens/<email>.json` | OAuth token — gitignored, never commit |
| `state/<email>/` | Run timestamps and action item state — gitignored |
| `ea/claude.py` | All Claude AI prompts — edit here to tune output |
| `ea/tasks/` | One module per task |

---

## Adding a New User (for admins)

To add another manager:
1. Give them the repo URL: `https://github.com/ascarcel-boomi/boomi-exec-assistant`
2. If they don't have the google-workspace MCP configured, also send them `config/client_secrets.json` (out of band — do not commit it)
3. They run: `bash install.sh --email their.name@boomi.com` (or ask Claude Code to do it)
4. The service starts automatically and persists across reboots
