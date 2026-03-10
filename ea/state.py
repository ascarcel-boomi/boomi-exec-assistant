"""Lightweight per-user state — timestamps and action items stored as local files."""

import json
import pathlib
from datetime import datetime, timezone
from typing import Dict, List, Optional


class UserState:
    def __init__(self, email: str, state_dir: pathlib.Path):
        self.dir = state_dir / email
        self.dir.mkdir(parents=True, exist_ok=True)

    def _ts_path(self, task_name: str) -> pathlib.Path:
        safe = task_name.replace("/", "_").replace(":", "_")
        return self.dir / f"last_{safe}.txt"

    def get_last_run(self, task_name: str) -> Optional[datetime]:
        path = self._ts_path(task_name)
        if not path.exists():
            return None
        try:
            return datetime.fromisoformat(path.read_text().strip())
        except ValueError:
            return None

    def set_last_run(self, task_name: str, when: Optional[datetime] = None) -> None:
        when = when or datetime.now(timezone.utc)
        self._ts_path(task_name).write_text(when.isoformat())

    def get_last_history_id(self) -> Optional[str]:
        path = self.dir / "last_history_id.txt"
        if not path.exists():
            return None
        return path.read_text().strip() or None

    def set_last_history_id(self, history_id: str) -> None:
        (self.dir / "last_history_id.txt").write_text(history_id)

    def get_action_items(self) -> List[Dict]:
        path = self.dir / "action_items.json"
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, ValueError):
            return []

    def set_action_items(self, items: List[Dict]) -> None:
        (self.dir / "action_items.json").write_text(json.dumps(items, indent=2, default=str))

    def append_action_items(self, new_items: List[Dict]) -> None:
        existing = self.get_action_items()
        existing_texts = {i.get("item", "").lower() for i in existing}
        deduped = [i for i in new_items if i.get("item", "").lower() not in existing_texts]
        self.set_action_items(existing + deduped)
