"""Claude AI client and prompt builders for each EA task."""

import json
from typing import Dict, List, Optional, Tuple

import anthropic

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

EA_PERSONA = """You are an expert executive assistant for {display_name} ({email}) at Boomi, \
a B2B integration software company. You are precise, concise, and professional. \
You surface only what matters and never pad your responses. \
Today's date/time in {timezone}: {now}.

IMPORTANT: Whenever you reference a Jira ticket (any pattern like PCR-1234, CAMSRE-1234, \
SRE-1234, EIN-1234, WA-1234, CAMSRE-1234, etc.), always format it as a markdown link: \
[TICKET-ID](https://boomii.atlassian.net/browse/TICKET-ID). Never mention a ticket ID as plain text."""


def _format_events(events: list) -> str:
    if not events:
        return "No events scheduled."
    lines = []
    for e in events:
        time_str = ""
        if e.get("is_all_day"):
            time_str = "All day"
        elif e.get("start"):
            time_str = e["start"].strftime("%I:%M %p")
            if e.get("end"):
                time_str += f" – {e['end'].strftime('%I:%M %p')}"
        attendees = ", ".join(
            a["email"].split("@")[0] for a in (e.get("attendees") or [])[:5]
        )
        line = f"• {time_str}: {e['summary']}"
        if attendees:
            line += f" (with: {attendees})"
        if e.get("duration_minutes"):
            line += f" [{e['duration_minutes']}min]"
        lines.append(line)
    return "\n".join(lines)


def _format_emails(emails: list, max_per: int = 300) -> str:
    if not emails:
        return "No emails."
    lines = []
    for i, e in enumerate(emails, 1):
        lines.append(
            f"[{i}] FROM: {e['from']}\n"
            f"    SUBJECT: {e['subject']}\n"
            f"    DATE: {e['date']}\n"
            f"    BODY: {e['body'][:max_per]}"
        )
    return "\n\n".join(lines)


class ClaudeClient:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system: str, user: str, max_tokens: int = MAX_TOKENS) -> str:
        message = self.client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text

    def _system(self, cfg, now_str: str) -> str:
        return EA_PERSONA.format(
            display_name=cfg.display_name,
            email=cfg.email,
            timezone=cfg.timezone,
            now=now_str,
        )

    # ── Task 1: Morning Brief ────────────────────────────────────────────────

    def morning_brief_prompt(self, cfg, events: list, emails: list, now_str: str) -> Tuple[str, str]:
        system = self._system(cfg, now_str)
        user = f"""Prepare {cfg.display_name}'s morning briefing.

## TODAY'S CALENDAR
{_format_events(events)}

## OVERNIGHT EMAILS (since 10pm yesterday)
{_format_emails(emails)}

Write a morning brief with these sections:
1. **Day at a Glance** — 2–3 sentence overview of the day
2. **Meetings Today** — list each meeting with time, attendees, and a one-line purpose
3. **Email Priorities** — top 3–5 emails that need attention today, with suggested action
4. **Action Items** — any commitments or deadlines visible from the emails above
5. **Heads Up** — anything unusual, time-sensitive, or worth flagging

Keep the whole brief under 400 words. Use bullet points. Be direct."""
        return system, user

    # ── Task 2: Email Triage ─────────────────────────────────────────────────

    def email_triage_prompt(self, cfg, emails: list, now_str: str) -> Tuple[str, str]:
        system = self._system(cfg, now_str)
        user = f"""Triage {cfg.display_name}'s inbox. Here are the new emails:

{_format_emails(emails)}

For each email, classify it:
- **P1 — Respond within 2 hours**: direct questions, executive escalations, time-sensitive requests
- **P2 — Respond by end of day**: items that need a reply today but not urgently
- **P3 — FYI / Low priority**: newsletters, notifications, CC'd threads, no action needed

Output format (one block per email):
---
**[P1/P2/P3] Subject**
From: sender
Action: one sentence describing what to do
Reply suggestion (P1 only): "..."
---

After the list, add a **Summary** line: "X P1 items need your attention, Y P2 by EOD, Z P3 can wait."
"""
        return system, user

    # ── Task 3: Pre-Meeting Brief ────────────────────────────────────────────

    def pre_meeting_prompt(self, cfg, event: dict, related_emails: list, now_str: str) -> Tuple[str, str]:
        system = self._system(cfg, now_str)
        attendees = ", ".join(
            f"{a.get('name') or a['email']}" for a in event.get("attendees", [])[:8]
        )
        user = f"""Prepare a pre-meeting brief for {cfg.display_name}.

## MEETING
Title: {event['summary']}
Time: {event.get('start_str', '')} → {event.get('end_str', '')}
Duration: {event.get('duration_minutes', '?')} minutes
Attendees: {attendees or 'None listed'}
Description: {event.get('description') or 'None'}
Location/Link: {event.get('hangout_link') or event.get('location') or 'None'}

## RECENT RELATED EMAILS
{_format_emails(related_emails, max_per=400)}

Write a concise pre-meeting brief (under 250 words) with:
1. **Purpose** — what this meeting is for in one sentence
2. **Key People** — who's attending and their likely agenda
3. **Context from Email** — relevant threads or decisions from recent emails
4. **Suggested Talking Points** — 3–4 bullets {cfg.display_name} should be ready to address
5. **Watch Out** — any open questions, risks, or tensions to be aware of
"""
        return system, user

    # ── Task 4: Action Tracker ───────────────────────────────────────────────

    def action_tracker_prompt(self, cfg, emails: list, past_events: list, now_str: str) -> Tuple[str, str]:
        system = self._system(cfg, now_str)
        user = f"""Extract action items from {cfg.display_name}'s emails and completed meetings today.

## TODAY'S EMAILS
{_format_emails(emails)}

## COMPLETED MEETINGS TODAY
{_format_events(past_events)}

Return a JSON array (no markdown, just valid JSON). Each item:
{{
  "source": "email subject or meeting title",
  "item": "what needs to be done",
  "owner": "who owns it (use '{cfg.display_name}' or the person's name/email)",
  "due": "deadline if mentioned, else 'ASAP' or 'This week'",
  "type": "commit_made | commit_received | follow_up | decision_needed"
}}

Only include concrete, actionable items. Skip vague items like "let's discuss later" unless there's a real date. Return [] if nothing actionable found."""
        return system, user

    # ── Task 6: Daily Ticket Brief ──────────────────────────────────────────

    def daily_ticket_brief_prompt(self, cfg, tickets_text: str, now_str: str) -> Tuple[str, str]:
        system = self._system(cfg, now_str)
        user = f"""Build a strategic daily ticket plan for {cfg.display_name}.

## OPEN JIRA TICKETS (assigned to {cfg.display_name})

{tickets_text}

Create a focused daily ticket brief using only the sections that apply. Omit any section with no relevant tickets.

**Focus Now** — The 1–3 tickets to start on first today. Be specific about why each one is the priority (e.g. overdue, blocking others, sprint at risk, SLA concern). One action sentence per ticket.

**Sprint Commitments** — In-sprint stories. Is the sprint on track? Flag anything at risk of not completing. If everything looks fine, one sentence is enough.

**Unplanned Queue** — Operational Requests, Troubleshooting Requests, and Access Requests. Order by urgency. Call out anything that looks time-sensitive or SLA-bound.

**Blocked / Needs Input** — Tickets that can't move forward without action from someone else. What exactly is needed and from whom?

**Defer** — Tickets that can safely wait until tomorrow or later. One line each.

Formatting rules:
- Every ticket must be a markdown link: [TICKET-KEY](url)
- Be prescriptive — tell {cfg.display_name} exactly what to do, not just what to think about
- When sprint work and unplanned work compete, favor clearing the unplanned queue first unless the sprint is at risk
- Keep the total brief under 500 words
- Start directly with the first section — no preamble"""
        return system, user

    # ── Task 5: EOD Digest ───────────────────────────────────────────────────

    def eod_digest_prompt(
        self,
        cfg,
        events: list,
        emails: list,
        action_items: list,
        tomorrow_events: list,
        now_str: str,
    ) -> Tuple[str, str]:
        system = self._system(cfg, now_str)
        action_items_text = (
            json.dumps(action_items, indent=2, default=str)
            if action_items
            else "None tracked today."
        )
        user = f"""Prepare {cfg.display_name}'s end-of-day digest.

## TODAY'S MEETINGS
{_format_events(events)}

## TODAY'S EMAILS (sample)
{_format_emails(emails[:15])}

## TRACKED ACTION ITEMS
{action_items_text}

## TOMORROW'S CALENDAR
{_format_events(tomorrow_events)}

Write an EOD digest (under 350 words) with:
1. **Day Summary** — 2–3 sentences on what got done today
2. **Open Action Items** — what still needs attention before tomorrow
3. **Waiting On** — items where {cfg.display_name} is waiting on someone else
4. **Tomorrow's Preview** — key meetings and priorities for tomorrow
5. **One Thing** — the single most important thing to do first thing tomorrow

Be direct. No filler."""
        return system, user
