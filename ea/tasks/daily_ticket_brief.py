"""Task 6: Daily Ticket Brief — strategic Jira work plan for the day.

Queries Jira for all open tickets assigned to the user, categorizes them
(in-progress, overdue, sprint to-do, unplanned kanban), and uses Claude to
generate a prioritized, prescriptive plan for the day.

Works for both managers and individual contributors. Fires each morning
alongside the morning brief.
"""

from datetime import datetime, timezone

from ea.jira import JiraClient


def _fmt(t: dict) -> str:
    """Format a single ticket as a markdown bullet with metadata."""
    line = f"- [{t['key']}]({t['url']}) **{t['summary']}**"
    meta = []
    if t.get("priority") and t["priority"] not in ("Medium", "None", ""):
        meta.append(t["priority"])
    if t.get("type"):
        meta.append(t["type"])
    if t.get("due"):
        meta.append(f"due {t['due']}")
    if t.get("sprint"):
        meta.append(t["sprint"])
    if t.get("updated"):
        meta.append(f"updated {t['updated']}")
    if meta:
        line += f" _({', '.join(meta)})_"
    if t.get("last_comment"):
        line += f"\n  > {t['last_comment'][:150]}"
    return line


def format_tickets(data: dict) -> str:
    """Format all ticket categories into a text block for Claude."""
    sections = []

    if data.get("in_progress"):
        bullets = "\n".join(_fmt(t) for t in data["in_progress"])
        sections.append(f"### IN PROGRESS\n{bullets}")

    if data.get("overdue"):
        bullets = "\n".join(_fmt(t) for t in data["overdue"])
        sections.append(f"### OVERDUE (past due date)\n{bullets}")

    if data.get("sprint_todo"):
        bullets = "\n".join(_fmt(t) for t in data["sprint_todo"])
        sections.append(f"### SPRINT TO-DO (planned, not yet started)\n{bullets}")

    if data.get("unplanned"):
        bullets = "\n".join(_fmt(t) for t in data["unplanned"])
        sections.append(f"### UNPLANNED / KANBAN (OR · TR · AR · Bug)\n{bullets}")

    return "\n\n".join(sections) if sections else "No open tickets found."


def run(cfg, deliverer, claude, dry_run: bool = False, **kwargs) -> None:
    if not getattr(cfg, "jira_base_url", None):
        print("[daily_ticket_brief] No jira_base_url configured — skipping.")
        return

    print("[daily_ticket_brief] Fetching Jira tickets...")
    jira = JiraClient(cfg.jira_base_url, cfg.email)

    if not jira.configured:
        print("[daily_ticket_brief] JIRA_API_TOKEN not set — skipping.")
        return

    try:
        tickets = jira.get_my_tickets(cfg.jira_project_keys)
    except Exception as e:
        print(f"[daily_ticket_brief] Jira fetch failed: {e}")
        return

    total = sum(len(v) for v in tickets.values())
    print(f"[daily_ticket_brief] Found {total} tickets across {len([v for v in tickets.values() if v])} categories.")

    now_str = datetime.now(timezone.utc).strftime("%A, %B %d %Y %H:%M UTC")
    system, user_msg = claude.daily_ticket_brief_prompt(cfg, format_tickets(tickets), now_str)
    brief = claude.complete(system, user_msg)

    deliverer.deliver(
        subject=f"Ticket Plan — {datetime.now().strftime('%a %b %d')}",
        body=brief,
        task_name="daily_ticket_brief",
        dry_run=dry_run,
    )
    print("[daily_ticket_brief] Done.")
