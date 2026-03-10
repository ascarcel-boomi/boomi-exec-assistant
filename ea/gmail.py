"""Gmail API wrapper — fetches and sends messages."""

import base64
import email as email_lib
import re
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Dict, List, Optional


def _decode_body(payload: dict) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime_type == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

    if mime_type == "text/html" and body_data:
        html = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
        # Strip tags for plain-text fallback
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    for part in payload.get("parts", []):
        result = _decode_body(part)
        if result:
            return result

    return ""


def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _parse_message(msg: dict) -> dict:
    """Convert raw Gmail message dict to a clean summary dict."""
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    body = _decode_body(payload)

    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId", ""),
        "subject": _get_header(headers, "Subject") or "(no subject)",
        "from": _get_header(headers, "From"),
        "to": _get_header(headers, "To"),
        "date": _get_header(headers, "Date"),
        "snippet": msg.get("snippet", ""),
        "body": body[:3000],  # cap for Claude context
        "labels": msg.get("labelIds", []),
    }


class GmailClient:
    def __init__(self, service, user_email: str = "me"):
        self.service = service
        self.user_email = user_email

    def _list_messages(
        self,
        query: str,
        max_results: int,
        label_ids: Optional[List[str]] = None,
    ) -> List[dict]:
        kwargs = {
            "userId": self.user_email,
            "q": query,
            "maxResults": min(max_results, 100),
        }
        if label_ids:
            kwargs["labelIds"] = label_ids

        result = self.service.users().messages().list(**kwargs).execute()
        messages = result.get("messages", [])

        full = []
        for m in messages:
            msg = (
                self.service.users()
                .messages()
                .get(userId=self.user_email, id=m["id"], format="full")
                .execute()
            )
            full.append(_parse_message(msg))
        return full

    def get_messages_since(
        self,
        since: datetime,
        max_results: int = 50,
        label_ids: Optional[List[str]] = None,
        query: Optional[str] = None,
    ) -> List[dict]:
        """Fetch messages newer than `since` datetime (UTC)."""
        ts = int(since.timestamp())
        q = f"after:{ts}"
        if query:
            q = f"({query}) {q}"
        return self._list_messages(q, max_results, label_ids)

    def get_messages_since_history_id(
        self,
        history_id: str,
        max_results: int = 50,
    ) -> List[dict]:
        """Incremental fetch using Gmail History API."""
        try:
            result = (
                self.service.users()
                .history()
                .list(
                    userId=self.user_email,
                    startHistoryId=history_id,
                    historyTypes=["messageAdded"],
                    maxResults=max_results,
                )
                .execute()
            )
        except Exception:
            # historyId expired — fall back to last hour
            from datetime import timedelta
            since = datetime.now(timezone.utc) - timedelta(hours=1)
            return self.get_messages_since(since, max_results)

        message_ids = []
        for record in result.get("history", []):
            for added in record.get("messagesAdded", []):
                message_ids.append(added["message"]["id"])

        if not message_ids:
            return []

        full = []
        for mid in message_ids[:max_results]:
            msg = (
                self.service.users()
                .messages()
                .get(userId=self.user_email, id=mid, format="full")
                .execute()
            )
            full.append(_parse_message(msg))
        return full

    def get_history_id(self) -> str:
        """Return current mailbox historyId for next incremental fetch."""
        profile = (
            self.service.users().getProfile(userId=self.user_email).execute()
        )
        return str(profile.get("historyId", ""))

    def get_thread(self, thread_id: str) -> List[dict]:
        """Return all messages in a thread, oldest first."""
        result = (
            self.service.users()
            .threads()
            .get(userId=self.user_email, id=thread_id, format="full")
            .execute()
        )
        return [_parse_message(m) for m in result.get("messages", [])]

    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        html: bool = False,
    ) -> dict:
        """Send an email. Returns {id, threadId}."""
        mime_type = "html" if html else "plain"
        msg = MIMEText(body, mime_type)
        msg["to"] = to
        msg["from"] = self.user_email
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        return (
            self.service.users()
            .messages()
            .send(userId=self.user_email, body={"raw": raw})
            .execute()
        )

    def apply_label(self, message_id: str, label_name: str) -> None:
        """Apply a label (creates it if it doesn't exist)."""
        # Find or create the label
        labels = (
            self.service.users().labels().list(userId=self.user_email).execute()
        )
        label_id = None
        for lbl in labels.get("labels", []):
            if lbl["name"] == label_name:
                label_id = lbl["id"]
                break

        if not label_id:
            new_label = (
                self.service.users()
                .labels()
                .create(userId=self.user_email, body={"name": label_name})
                .execute()
            )
            label_id = new_label["id"]

        self.service.users().messages().modify(
            userId=self.user_email,
            id=message_id,
            body={"addLabelIds": [label_id]},
        ).execute()
