"""Task: Claude Code Usage Report — daily morning + weekly Friday summary.

Parses ~/.claude/projects/**/*.jsonl to extract per-message token usage and
calculates estimated cost using Anthropic's published pricing.

Daily report: fires each morning, covers usage since midnight (rolling 8h window).
Weekly report: fires every Friday EOD, covers the past 7 days.
"""

import json
import pathlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# Pricing per million tokens (USD) — update if Anthropic changes rates.
# Source: https://www.anthropic.com/pricing
MODEL_PRICING = {
    "claude-opus-4-6":    {"input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50},
    "claude-opus-4-5":    {"input": 15.00, "output": 75.00, "cache_write": 18.75, "cache_read": 1.50},
    "claude-sonnet-4-6":  {"input":  3.00, "output": 15.00, "cache_write":  3.75, "cache_read": 0.30},
    "claude-sonnet-4-5":  {"input":  3.00, "output": 15.00, "cache_write":  3.75, "cache_read": 0.30},
    "claude-haiku-4-5":   {"input":  0.80, "output":  4.00, "cache_write":  1.00, "cache_read": 0.08},
}
_DEFAULT_PRICING = {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30}

CLAUDE_PROJECTS_DIR = pathlib.Path.home() / ".claude" / "projects"


def _cost(usage: dict, model: str) -> float:
    p = MODEL_PRICING.get(model, _DEFAULT_PRICING)
    return (
        usage.get("input_tokens", 0)                    * p["input"]       / 1_000_000
        + usage.get("output_tokens", 0)                 * p["output"]      / 1_000_000
        + usage.get("cache_creation_input_tokens", 0)   * p["cache_write"] / 1_000_000
        + usage.get("cache_read_input_tokens", 0)       * p["cache_read"]  / 1_000_000
    )


def _parse_usage_since(since: datetime) -> dict:
    """Scan all JSONL logs under ~/.claude/projects/ and aggregate token usage."""
    stats = defaultdict(lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cost": 0.0,
        "messages": 0,
    })

    if not CLAUDE_PROJECTS_DIR.exists():
        return {}

    for jsonl_file in CLAUDE_PROJECTS_DIR.rglob("*.jsonl"):
        try:
            for line in jsonl_file.read_text(errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("type") != "assistant":
                    continue
                ts_str = obj.get("timestamp")
                if not ts_str:
                    continue
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts < since:
                    continue
                msg = obj.get("message", {})
                if not isinstance(msg, dict):
                    continue
                usage = msg.get("usage")
                if not usage:
                    continue
                model = msg.get("model", "unknown")
                s = stats[model]
                s["input_tokens"]                  += usage.get("input_tokens", 0)
                s["output_tokens"]                 += usage.get("output_tokens", 0)
                s["cache_creation_input_tokens"]   += usage.get("cache_creation_input_tokens", 0)
                s["cache_read_input_tokens"]       += usage.get("cache_read_input_tokens", 0)
                s["cost"]                          += _cost(usage, model)
                s["messages"]                      += 1
        except Exception:
            continue

    return dict(stats)


def _format_report(stats: dict, period_label: str) -> str:
    if not stats:
        return f"# Claude Code Usage — {period_label}\n\nNo usage recorded for this period."

    total_cost     = sum(s["cost"]                          for s in stats.values())
    total_input    = sum(s["input_tokens"]                  for s in stats.values())
    total_output   = sum(s["output_tokens"]                 for s in stats.values())
    total_cw       = sum(s["cache_creation_input_tokens"]   for s in stats.values())
    total_cr       = sum(s["cache_read_input_tokens"]       for s in stats.values())
    total_msgs     = sum(s["messages"]                      for s in stats.values())

    total_reads = total_input + total_cr
    cache_pct = (total_cr / total_reads * 100) if total_reads > 0 else 0.0

    lines = [
        f"# Claude Code Usage — {period_label}",
        "",
        "## Summary",
        f"- **Estimated cost:** ${total_cost:.4f}",
        f"- **Messages:** {total_msgs:,}",
        f"- **Input tokens:** {total_input:,}",
        f"- **Output tokens:** {total_output:,}",
        f"- **Cache writes:** {total_cw:,}",
        f"- **Cache reads:** {total_cr:,}",
        f"- **Cache hit rate:** {cache_pct:.1f}%",
        "",
        "## By Model",
    ]

    for model, s in sorted(stats.items(), key=lambda x: -x[1]["cost"]):
        lines += [
            f"### {model}",
            f"- Cost: **${s['cost']:.4f}** | Messages: {s['messages']:,}",
            f"- Input: {s['input_tokens']:,} | Output: {s['output_tokens']:,}",
            f"- Cache writes: {s['cache_creation_input_tokens']:,} | Reads: {s['cache_read_input_tokens']:,}",
        ]

    lines += ["", "## Optimization Tips"]
    if cache_pct < 30:
        lines.append(
            "- **Low cache hit rate** — keep sessions alive and work on related files together "
            "to avoid cold re-reads."
        )
    if total_msgs > 0 and total_input / total_msgs > 50_000:
        lines.append(
            "- **Large average context per message** — scope Claude to specific files or "
            "directories to cut input tokens."
        )
    if cache_pct >= 50:
        lines.append("- Cache efficiency is healthy — keep sessions focused to maintain this.")
    if not lines[-1].startswith("-"):
        lines.append("- Usage looks efficient — no obvious issues to flag.")

    lines += [
        "",
        "---",
        "*Costs are estimates based on Anthropic list pricing. "
        "Actual billing may differ. "
        "Check [Anthropic Console](https://console.anthropic.com/settings/usage) or "
        "[Vantage](https://console.vantage.sh/reports/rprt_b65ee52029f90623) for authoritative figures.*",
    ]

    return "\n".join(lines)


def run_daily(cfg, deliverer, dry_run: bool = False, **kwargs) -> None:
    """Daily usage snapshot — fires each morning.  Covers rolling ~8h window to midnight."""
    now = datetime.now(timezone.utc)
    since = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=8)
    stats = _parse_usage_since(since)
    report = _format_report(stats, f"Today ({now.strftime('%A %b %d')})")
    print("[claude_usage] Daily report generated.")
    deliverer.deliver(
        subject=f"Claude Usage — {now.strftime('%a %b %d')}",
        body=report,
        task_name="claude_usage_daily",
        dry_run=dry_run,
    )


def run_weekly(cfg, deliverer, dry_run: bool = False, **kwargs) -> None:
    """Weekly summary — fires Friday EOD, covers past 7 days."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=7)
    stats = _parse_usage_since(since)
    week_label = f"{since.strftime('%b %d')}–{now.strftime('%b %d')}"
    report = _format_report(stats, f"Week of {week_label}")
    print("[claude_usage] Weekly report generated.")
    deliverer.deliver(
        subject=f"Claude Weekly Usage — {week_label}",
        body=report,
        task_name="claude_usage_weekly",
        dry_run=dry_run,
    )
