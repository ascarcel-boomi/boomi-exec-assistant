#!/bin/bash
# Boomi Executive Assistant — Automated Installer
# Usage: bash install.sh --email you@boomi.com

set -e

REPO_DIR="$HOME/github/boomi-exec-assistant"
VENV_DIR="$REPO_DIR/.venv"
PLIST_LABEL="com.boomi.exec-assistant"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
LOG_PATH="$HOME/exec-assistant.log"

# ── Helpers ─────────────────────────────────────────────────────────────────

green()  { echo "✅  $*"; }
yellow() { echo "⚠️   $*"; }
red()    { echo "❌  $*"; }
info()   { echo "    $*"; }

require() {
    command -v "$1" >/dev/null 2>&1 || { red "Required tool not found: $1"; exit 1; }
}

# ── Args ─────────────────────────────────────────────────────────────────────

EMAIL=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --email) EMAIL="$2"; shift 2 ;;
        *) shift ;;
    esac
done

if [[ -z "$EMAIL" ]]; then
    read -p "Enter your Boomi email address: " EMAIL
fi

if [[ "$EMAIL" != *@boomi.com ]]; then
    yellow "Email doesn't look like a Boomi address: $EMAIL"
    read -p "Continue anyway? [y/N]: " yn
    [[ "$yn" == "y" || "$yn" == "Y" ]] || exit 1
fi

NAME_PART="${EMAIL%%@*}"  # adam.scarcella

echo ""
echo "=== Boomi Executive Assistant Installer ==="
echo "    Installing for: $EMAIL"
echo ""

# ── Step 1: Python ───────────────────────────────────────────────────────────

echo "[1/8] Checking Python..."
require python3
PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python $PY_VERSION found at $(which python3)"
green "Python OK"

# ── Step 2: Repo ─────────────────────────────────────────────────────────────

echo ""
echo "[2/8] Setting up repository..."
if [[ ! -d "$REPO_DIR" ]]; then
    red "Repo not found at $REPO_DIR"
    info "Clone it first: git clone https://github.com/ascarcel-boomi/boomi-exec-assistant ~/github/boomi-exec-assistant"
    exit 1
fi
green "Repo found at $REPO_DIR"

# ── Step 3: Virtualenv + deps ────────────────────────────────────────────────

echo ""
echo "[3/8] Installing Python dependencies..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q -r "$REPO_DIR/requirements.txt"
green "Dependencies installed"

# ── Step 4: User config ──────────────────────────────────────────────────────

echo ""
echo "[4/8] Creating user config..."
CONFIG_PATH="$REPO_DIR/config/users/$NAME_PART.yaml"

if [[ -f "$CONFIG_PATH" ]]; then
    yellow "Config already exists at $CONFIG_PATH — skipping"
else
    # Detect timezone
    TZ_DEFAULT=$(readlink /etc/localtime 2>/dev/null | sed 's|.*/zoneinfo/||' || echo "America/New_York")
    [[ -z "$TZ_DEFAULT" ]] && TZ_DEFAULT="America/New_York"

    read -p "    Display name [$(echo "$NAME_PART" | sed 's/\./ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) substr($i,2); print}')]: " DISPLAY_NAME
    [[ -z "$DISPLAY_NAME" ]] && DISPLAY_NAME=$(echo "$NAME_PART" | sed 's/\./ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) substr($i,2); print}')

    read -p "    Timezone [$TZ_DEFAULT]: " TIMEZONE
    [[ -z "$TIMEZONE" ]] && TIMEZONE="$TZ_DEFAULT"

    read -p "    Morning brief time [07:30]: " MORNING
    [[ -z "$MORNING" ]] && MORNING="07:30"

    read -p "    EOD digest time [17:30]: " EOD
    [[ -z "$EOD" ]] && EOD="17:30"

    cat > "$CONFIG_PATH" << YAML
email: $EMAIL
display_name: $DISPLAY_NAME
timezone: $TIMEZONE
morning_brief_time: "$MORNING"
eod_digest_time: "$EOD"
email_triage_interval_minutes: 60
pre_meeting_lookback_minutes: 15
max_emails_per_triage: 50
calendar_lookahead_hours: 24
deliver_to_email: true
deliver_to_stdout: true
working_hours_start: "07:00"
working_hours_end: "19:00"
YAML
    green "Config written to $CONFIG_PATH"
fi

# ── Step 5: Jira integration ─────────────────────────────────────────────────

echo ""
echo "[5/8] Setting up Jira integration (daily ticket brief)..."

# Look for an existing token in known credential locations
JIRA_TOKEN="${JIRA_API_TOKEN:-}"
if [[ -z "$JIRA_TOKEN" ]]; then
    for cred_file in \
        "$HOME/.kiro/mcp_credentials/mcp-atlassian.env" \
        "$HOME/.amazonq/mcp_credentials/mcp-atlassian.env"; do
        if [[ -f "$cred_file" ]]; then
            FOUND=$(grep "^JIRA_API_TOKEN=" "$cred_file" 2>/dev/null | cut -d= -f2- | tr -d '[:space:]')
            if [[ -n "$FOUND" ]]; then
                JIRA_TOKEN="$FOUND"
                info "Found Jira API token in $cred_file"
                break
            fi
        fi
    done
fi

if [[ -z "$JIRA_TOKEN" ]]; then
    yellow "Jira API token not found automatically."
    info "Create one at: https://id.atlassian.com/manage-profile/security/api-tokens"
    info "Choose 'Create API token with scopes' and select the Jira Read scopes."
    info "(Press Enter to skip — daily ticket brief will be disabled until you add it)"
    read -s -p "    Paste your Jira API token (or Enter to skip): " JIRA_TOKEN
    echo ""
fi

if [[ -n "$JIRA_TOKEN" ]]; then
    # Save token to shell profile
    if ! grep -q "JIRA_API_TOKEN" ~/.zshrc 2>/dev/null; then
        echo "export JIRA_API_TOKEN=\"$JIRA_TOKEN\"" >> ~/.zshrc
        info "Saved JIRA_API_TOKEN to ~/.zshrc"
    fi

    # Prompt for Jira config (with sensible defaults)
    read -p "    Jira base URL [https://boomii.atlassian.net]: " JIRA_URL
    [[ -z "$JIRA_URL" ]] && JIRA_URL="https://boomii.atlassian.net"

    read -p "    Jira project keys, comma-separated [CAMSRE,SRE]: " JIRA_KEYS_INPUT
    [[ -z "$JIRA_KEYS_INPUT" ]] && JIRA_KEYS_INPUT="CAMSRE,SRE"

    # Build YAML list from comma-separated input
    JIRA_YAML_LIST=""
    IFS=',' read -ra _KEYS <<< "$JIRA_KEYS_INPUT"
    for _k in "${_KEYS[@]}"; do
        _k=$(echo "$_k" | tr -d '[:space:]')
        JIRA_YAML_LIST="${JIRA_YAML_LIST}  - \"${_k}\"\n"
    done

    # Append Jira block to config YAML (only if not already present)
    if ! grep -q "jira_base_url" "$CONFIG_PATH" 2>/dev/null; then
        printf "\n# Jira — enables daily ticket brief (JIRA_API_TOKEN set in environment)\njira_base_url: \"%s\"\njira_project_keys:\n%b" \
            "$JIRA_URL" "$JIRA_YAML_LIST" >> "$CONFIG_PATH"
    fi

    green "Jira configured (daily ticket brief enabled)"
else
    # Still write placeholder so the config is valid
    if ! grep -q "jira_base_url" "$CONFIG_PATH" 2>/dev/null; then
        printf "\n# Jira — uncomment and set JIRA_API_TOKEN to enable daily ticket brief\n# jira_base_url: \"https://boomii.atlassian.net\"\n# jira_project_keys:\n#   - \"CAMSRE\"\n" >> "$CONFIG_PATH"
    fi
    yellow "Jira skipped — daily ticket brief will not fire until JIRA_API_TOKEN is set"
fi

# ── Step 6: Google auth token ────────────────────────────────────────────────

echo ""
echo "[6/8] Setting up Google authentication..."
TOKEN_DIR="$REPO_DIR/tokens"
TOKEN_PATH="$TOKEN_DIR/$EMAIL.json"
mkdir -p "$TOKEN_DIR"
chmod 700 "$TOKEN_DIR"

if [[ -f "$TOKEN_PATH" ]]; then
    green "Token already exists — skipping OAuth flow"
else
    # Try to reuse existing google-workspace MCP token (same format, same scopes)
    MCP_TOKEN="$HOME/.google_workspace_mcp/credentials/$EMAIL.json"
    if [[ -f "$MCP_TOKEN" ]]; then
        cp "$MCP_TOKEN" "$TOKEN_PATH"
        chmod 600 "$TOKEN_PATH"
        green "Reused existing Google Workspace MCP token (no browser login needed)"
    else
        # Need client_secrets.json for OAuth flow
        SECRETS_PATH="$REPO_DIR/config/client_secrets.json"
        if [[ ! -f "$SECRETS_PATH" ]]; then
            yellow "client_secrets.json not found at $SECRETS_PATH"
            info "Ask your team admin (adam.scarcella@boomi.com) for the file and place it at:"
            info "  $SECRETS_PATH"
            info "Then re-run this installer."
            exit 1
        fi
        info "Running Google OAuth flow — a browser window will open..."
        info "Sign in as $EMAIL and grant the requested permissions."
        "$VENV_DIR/bin/python3" "$REPO_DIR/setup.py" --email "$EMAIL" 2>/dev/null || true
    fi
fi

# ── Step 6: Anthropic API key ────────────────────────────────────────────────

echo ""
echo "[7/8] Setting up Anthropic API key..."

# Check Claude Code keychain first (works if Claude Code CLI is installed)
API_KEY=$(security find-generic-password -s "Claude Code" -w 2>/dev/null || true)

if [[ -z "$API_KEY" ]]; then
    # Check environment / shell profile
    API_KEY="${ANTHROPIC_API_KEY:-}"
fi

if [[ -z "$API_KEY" ]]; then
    yellow "Could not find API key automatically."
    info "Your Boomi Anthropic API key should be in 1Password or provided by IT."
    read -s -p "    Paste your Anthropic API key (sk-ant-...): " API_KEY
    echo ""
fi

if [[ -z "$API_KEY" ]]; then
    red "No Anthropic API key provided. Cannot continue."
    exit 1
fi

# Save to shell profile if not already there
if ! grep -q "ANTHROPIC_API_KEY" ~/.zshrc 2>/dev/null; then
    echo "export ANTHROPIC_API_KEY=\"$API_KEY\"" >> ~/.zshrc
    info "Saved to ~/.zshrc"
fi
green "Anthropic API key configured"

# ── Step 7: launchd background service ──────────────────────────────────────

echo ""
echo "[8/8] Installing macOS background service (launchd)..."

# Stop existing service if running
if launchctl list | grep -q "$PLIST_LABEL" 2>/dev/null; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    info "Stopped existing service"
fi

cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_DIR/bin/python3</string>
        <string>$REPO_DIR/daemon.py</string>
        <string>--email</string>
        <string>$EMAIL</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ANTHROPIC_API_KEY</key>
        <string>$API_KEY</string>
        <key>JIRA_API_TOKEN</key>
        <string>$JIRA_TOKEN</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_PATH</string>
    <key>StandardErrorPath</key>
    <string>$LOG_PATH</string>
</dict>
</plist>
PLIST

launchctl load "$PLIST_PATH"
sleep 2

if launchctl list | grep -q "$PLIST_LABEL"; then
    green "Background service installed and running"
else
    red "Service failed to start — check $LOG_PATH for errors"
    exit 1
fi

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "================================================="
echo "  Installation complete!"
echo "================================================="
echo ""
echo "  Your EA is running silently in the background."
echo ""
echo "  Schedule:"
echo "    • Morning brief:      daily at $MORNING (calendar + overnight email)"
echo "    • Daily ticket brief: daily at $MORNING (Jira work plan for the day)"
echo "    • Email triage:       every 60 min during working hours"
echo "    • Pre-meeting:        15 min before each calendar event"
echo "    • Action tracker:     noon + 30 min before EOD"
echo "    • EOD digest:         daily at $EOD"
echo ""
echo "  Logs:  tail -f $LOG_PATH"
echo ""
echo "  Run a task now:"
echo "    cd $REPO_DIR"
echo "    source .venv/bin/activate"
echo "    python3 cli.py --email $EMAIL --task morning_brief --dry-run"
echo ""
echo "  Stop the service:"
echo "    launchctl unload $PLIST_PATH"
echo ""
