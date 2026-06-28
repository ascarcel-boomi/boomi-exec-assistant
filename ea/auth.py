"""Google OAuth2 credential management.

Token format is compatible with the google-workspace MCP server so existing
MCP token files can be reused by copying them into tokens/.
"""

import json
import pathlib
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

# Canonical OAuth client-secret store: the google-workspace MCP credentials file.
# The client secret can be rotated independently of a user's refresh token (a
# secret reset does NOT invalidate refresh tokens). The token file caches a copy
# of the secret, which goes stale on rotation and breaks refresh with
# `invalid_client`. Re-read the live secret from the MCP store on every load so
# rotations self-heal instead of crash-looping the daemon.
MCP_CREDENTIALS_DIR = pathlib.Path.home() / ".google_workspace_mcp" / "credentials"


class NoTokenError(Exception):
    pass


def _live_client_secret(email: str):
    """Return (client_id, client_secret) from the canonical MCP creds file, or (None, None)."""
    mcp_path = MCP_CREDENTIALS_DIR / f"{email}.json"
    if not mcp_path.exists():
        return None, None
    try:
        data = json.loads(mcp_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None, None
    return data.get("client_id"), data.get("client_secret")


def _token_path(email: str, tokens_dir: pathlib.Path) -> pathlib.Path:
    return tokens_dir / f"{email}.json"


def get_credentials(
    email: str,
    tokens_dir: pathlib.Path,
    secrets_path: pathlib.Path,
) -> Credentials:
    """Load cached credentials, refreshing if expired. Raises NoTokenError if not set up."""
    path = _token_path(email, tokens_dir)
    if not path.exists():
        raise NoTokenError(
            f"No token found for {email}. Run: python3 setup.py --email {email}"
        )

    data = json.loads(path.read_text())

    # Prefer the live client id/secret from the canonical MCP store so a rotated
    # secret doesn't break refresh with `invalid_client`. A successful refresh
    # below re-saves the token file with the current secret, so it self-heals.
    live_id, live_secret = _live_client_secret(email)
    client_id = live_id or data.get("client_id")
    client_secret = live_secret or data.get("client_secret")

    # Parse expiry — handle both ISO string (MCP format) and None
    expiry = None
    if data.get("expiry"):
        try:
            expiry = datetime.fromisoformat(data["expiry"].replace("Z", "+00:00"))
        except ValueError:
            expiry = None

    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=client_id,
        client_secret=client_secret,
        scopes=data.get("scopes", SCOPES),
        expiry=expiry,
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(creds, email, tokens_dir)

    return creds


def run_oauth_flow(
    email: str,
    tokens_dir: pathlib.Path,
    secrets_path: pathlib.Path,
) -> Credentials:
    """Interactive OAuth2 browser flow. Saves token to tokens/<email>.json."""
    if not secrets_path.exists():
        raise FileNotFoundError(
            f"client_secrets.json not found at {secrets_path}.\n"
            "Download it from Google Cloud Console → APIs & Services → Credentials."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
    creds = flow.run_local_server(
        port=0,
        login_hint=email,
        prompt="consent",
    )
    save_credentials(creds, email, tokens_dir)
    return creds


def save_credentials(
    creds: Credentials,
    email: str,
    tokens_dir: pathlib.Path,
) -> None:
    """Serialize credentials to JSON in MCP-compatible format."""
    tokens_dir.mkdir(parents=True, exist_ok=True)
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }
    path = _token_path(email, tokens_dir)
    path.write_text(json.dumps(token_data, indent=2))
    path.chmod(0o600)  # restrict to owner only


def build_gmail_service(creds: Credentials):
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def build_calendar_service(creds: Credentials):
    return build("calendar", "v3", credentials=creds, cache_discovery=False)
