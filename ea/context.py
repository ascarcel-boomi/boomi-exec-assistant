"""Build per-user dependency context (Gmail, Calendar, Claude, Deliverer, State)."""

import os
import pathlib

from ea.auth import get_credentials, build_gmail_service, build_calendar_service
from ea.calendar import CalendarClient
from ea.claude import ClaudeClient
from ea.config import UserConfig, TOKENS_DIR, STATE_DIR, SECRETS_PATH
from ea.delivery import Deliverer
from ea.gmail import GmailClient
from ea.state import UserState


def build_user_context(cfg: UserConfig, anthropic_api_key: str = None) -> dict:
    """Instantiate all clients for a user. Returns kwargs dict for task.run()."""
    api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY not set. "
            "Export it or add it to your shell profile."
        )

    creds = get_credentials(cfg.email, TOKENS_DIR, SECRETS_PATH)
    gmail_service = build_gmail_service(creds)
    cal_service = build_calendar_service(creds)

    gmail = GmailClient(gmail_service, user_email="me")
    calendar = CalendarClient(cal_service)
    claude = ClaudeClient(api_key)
    state = UserState(cfg.email, STATE_DIR)
    deliverer = Deliverer(gmail, cfg)

    return {
        "gmail": gmail,
        "calendar": calendar,
        "claude": claude,
        "deliverer": deliverer,
        "state": state,
    }
