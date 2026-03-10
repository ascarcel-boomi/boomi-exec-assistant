"""User configuration loading and validation."""

from dataclasses import dataclass
from typing import List
import pathlib
import yaml

CONFIG_DIR = pathlib.Path(__file__).parent.parent / "config"
TOKENS_DIR = pathlib.Path(__file__).parent.parent / "tokens"
STATE_DIR = pathlib.Path(__file__).parent.parent / "state"
SECRETS_PATH = CONFIG_DIR / "client_secrets.json"


class ConfigError(Exception):
    pass


@dataclass
class UserConfig:
    email: str
    display_name: str
    timezone: str
    morning_brief_time: str
    eod_digest_time: str
    email_triage_interval_minutes: int
    pre_meeting_lookback_minutes: int
    max_emails_per_triage: int
    calendar_lookahead_hours: int
    deliver_to_email: bool
    deliver_to_stdout: bool
    working_hours_start: str
    working_hours_end: str


def _config_path(email: str) -> pathlib.Path:
    name = email.split("@")[0]  # adam.scarcella
    return CONFIG_DIR / "users" / f"{name}.yaml"


def load_user_config(email: str) -> UserConfig:
    path = _config_path(email)
    if not path.exists():
        raise ConfigError(
            f"No config found for {email}. "
            f"Expected: {path}\n"
            f"Run: python3 setup.py --email {email}"
        )
    with open(path) as f:
        data = yaml.safe_load(f)

    required = ["email", "display_name", "timezone", "morning_brief_time", "eod_digest_time"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ConfigError(f"Config {path} missing required fields: {missing}")

    return UserConfig(
        email=data["email"],
        display_name=data["display_name"],
        timezone=data["timezone"],
        morning_brief_time=data.get("morning_brief_time", "07:30"),
        eod_digest_time=data.get("eod_digest_time", "17:30"),
        email_triage_interval_minutes=int(data.get("email_triage_interval_minutes", 60)),
        pre_meeting_lookback_minutes=int(data.get("pre_meeting_lookback_minutes", 15)),
        max_emails_per_triage=int(data.get("max_emails_per_triage", 50)),
        calendar_lookahead_hours=int(data.get("calendar_lookahead_hours", 24)),
        deliver_to_email=bool(data.get("deliver_to_email", True)),
        deliver_to_stdout=bool(data.get("deliver_to_stdout", True)),
        working_hours_start=data.get("working_hours_start", "07:00"),
        working_hours_end=data.get("working_hours_end", "19:00"),
    )


def list_configured_users() -> List[str]:
    users_dir = CONFIG_DIR / "users"
    if not users_dir.exists():
        return []
    return [
        yaml.safe_load(open(p))["email"]
        for p in sorted(users_dir.glob("*.yaml"))
        if p.stem != "example"
    ]
