"""Output routing — stdout and/or Gmail (HTML)."""

import re


def _markdown_to_html(text: str) -> str:
    """Convert markdown to basic HTML suitable for Gmail."""
    lines = text.splitlines()
    html_lines = []
    in_list = False

    for line in lines:
        # Convert markdown links [text](url) -> <a href="url">text</a>
        line = re.sub(
            r'\[([^\]]+)\]\((https?://[^\)]+)\)',
            r'<a href="\2">\1</a>',
            line,
        )
        # Headers
        if line.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h1>{line[2:]}</h1>")
        # Bullet points
        elif line.startswith("- ") or line.startswith("• "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            content = line[2:]
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)
            html_lines.append(f"<li>{content}</li>")
        # Horizontal rule
        elif line.strip() == "---":
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<hr>")
        # Empty line
        elif line.strip() == "":
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<br>")
        # Normal paragraph
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            content = re.sub(r'\*(.+?)\*', r'<em>\1</em>', content)
            html_lines.append(f"<p>{content}</p>")

    if in_list:
        html_lines.append("</ul>")

    body_html = "\n".join(html_lines)
    return f"""<html><body style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px;">
{body_html}
</body></html>"""


def _linkify_tickets(text: str) -> str:
    """Convert bare ticket IDs to markdown links, skipping already-linked ones."""
    base = "https://boomii.atlassian.net/browse"

    def replace(m):
        # Group 1 = existing markdown link — leave it untouched
        if m.group(1):
            return m.group(0)
        # Group 2 = bare ticket ID — linkify it
        ticket = m.group(2)
        return f'[{ticket}]({base}/{ticket})'

    # Match either an existing markdown link (pass through) or a bare ticket ID (linkify)
    pattern = r'(\[[^\]]+\]\([^\)]+\))|(?<![/\w])([A-Z]{2,}-\d+)(?!\w)'
    return re.sub(pattern, replace, text)


class Deliverer:
    def __init__(self, gmail_client, cfg):
        self.gmail = gmail_client
        self.cfg = cfg

    def deliver(
        self,
        subject: str,
        body: str,
        task_name: str = "",
        dry_run: bool = False,
    ) -> None:
        # Ensure all ticket IDs are linked (catches any Claude missed)
        body = _linkify_tickets(body)

        if self.cfg.deliver_to_stdout:
            width = 70
            print(f"\n{'=' * width}")
            print(f"  {subject}")
            print(f"{'=' * width}")
            print(body)
            print()

        if self.cfg.deliver_to_email and not dry_run:
            try:
                html_body = _markdown_to_html(body)
                self.gmail.send_message(
                    to=self.cfg.email,
                    subject=f"[EA] {subject}",
                    body=html_body,
                    html=True,
                )
            except Exception as e:
                print(f"[EA] Warning: could not send email — {e}")
