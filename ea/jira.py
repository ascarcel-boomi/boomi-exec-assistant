"""Jira REST API v3 client for ticket fetching."""

import os
from typing import Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth


class JiraClient:
    def __init__(self, base_url: str, email: str):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self._token = os.environ.get("JIRA_API_TOKEN")
        self._auth = HTTPBasicAuth(email, self._token) if self._token else None

    @property
    def configured(self) -> bool:
        return bool(self._auth and self.base_url)

    def _search(self, jql: str, max_results: int = 30) -> List[dict]:
        if not self.configured:
            return []
        fields = [
            "summary", "status", "priority", "issuetype",
            "duedate", "labels", "created", "updated",
            "customfield_10020",  # sprint
            "comment",
        ]
        resp = requests.post(
            f"{self.base_url}/rest/api/3/search/jql",
            auth=self._auth,
            json={
                "jql": jql,
                "fields": fields,
                "maxResults": max_results,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("issues", [])

    def get_my_tickets(self, project_keys: List[str] = None) -> Dict[str, List[dict]]:
        """Return tickets for the current user grouped into four categories."""
        pf = ""
        if project_keys:
            keys = ", ".join(f'"{k}"' for k in project_keys)
            pf = f" AND project in ({keys})"

        in_progress = self._search(
            f'assignee = "{self.email}" AND statusCategory = "In Progress"{pf}'
            f' ORDER BY updated DESC',
        )

        overdue = self._search(
            f'assignee = "{self.email}" AND due < now()'
            f' AND statusCategory != Done{pf}'
            f' ORDER BY due ASC',
        )

        sprint_todo = self._search(
            f'assignee = "{self.email}" AND sprint in openSprints()'
            f' AND statusCategory = "To Do"{pf}'
            f' ORDER BY priority ASC, created ASC',
        )

        unplanned = self._search(
            f'assignee = "{self.email}"'
            f' AND issuetype in ("Operational Request", "Troubleshooting Request",'
            f' "Access Request", "Bug", "Incident")'
            f' AND statusCategory != Done'
            f' AND (sprint is EMPTY OR sprint not in openSprints()){pf}'
            f' ORDER BY priority ASC, created ASC',
            max_results=20,
        )

        return {
            "in_progress": [self._normalize(t) for t in in_progress],
            "overdue":     [self._normalize(t) for t in overdue],
            "sprint_todo": [self._normalize(t) for t in sprint_todo],
            "unplanned":   [self._normalize(t) for t in unplanned],
        }

    def _normalize(self, issue: dict) -> dict:
        f = issue.get("fields", {})

        # Sprint name from Jira custom field
        sprint_name = None
        sprint_data = f.get("customfield_10020")
        if sprint_data and isinstance(sprint_data, list):
            sprint_name = sprint_data[-1].get("name") if sprint_data else None

        # Last comment text (Atlassian Document Format → plain text)
        last_comment = None
        comments = (f.get("comment") or {}).get("comments", [])
        if comments:
            body = comments[-1].get("body", {})
            if isinstance(body, dict):
                parts = []
                for block in body.get("content", []):
                    for inline in block.get("content", []):
                        if inline.get("type") == "text":
                            parts.append(inline.get("text", ""))
                last_comment = " ".join(parts)[:200].strip()
            else:
                last_comment = str(body)[:200]

        return {
            "key":          issue["key"],
            "url":          f"{self.base_url}/browse/{issue['key']}",
            "summary":      f.get("summary", ""),
            "type":         (f.get("issuetype") or {}).get("name", "Story"),
            "status":       (f.get("status") or {}).get("name", "Unknown"),
            "priority":     (f.get("priority") or {}).get("name", "Medium"),
            "sprint":       sprint_name,
            "due":          f.get("duedate"),
            "labels":       f.get("labels", []),
            "created":      (f.get("created") or "")[:10],
            "updated":      (f.get("updated") or "")[:10],
            "last_comment": last_comment,
        }
