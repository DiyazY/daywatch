"""Plan preview rendering for the tray menu.

Generates text-based representations of the daily plan for use
in the tray menu and (future) popover window.
"""

from __future__ import annotations

from datetime import datetime, time

from daywatch.parser import BlockStatus, DailyPlan, TimeBlock


def _status_icon(block: TimeBlock, now: time | None = None) -> str:
    """Return the status icon for a block."""
    status = block.status(now)
    icons = {
        BlockStatus.COMPLETED: "✅",
        BlockStatus.ACTIVE: "▶",
        BlockStatus.UPCOMING: "○",
        BlockStatus.MISSED: "⚠",
        BlockStatus.FAILED: "🔴",
    }
    return icons.get(status, "○")


def format_block_line(block: TimeBlock, now: time | None = None) -> str:
    """Format a single block as a menu-friendly string.

    Example: '✅ 08:30–09:00 Planning'
    """
    icon = _status_icon(block, now)
    start = block.start.strftime("%H:%M")
    end = block.end.strftime("%H:%M")
    suffix = " ← now" if block.status(now) == BlockStatus.ACTIVE else ""
    return f"{icon} {start}–{end} {block.label}{suffix}"


def format_plan_summary(plan: DailyPlan, now: time | None = None) -> str:
    """Format the full plan as a text summary.

    Returns a multi-line string suitable for display in a popover or terminal.
    """
    if now is None:
        now = datetime.now().time()

    date_str = plan.date.strftime("%A, %d %b %Y")
    pct = plan.progress_percent

    lines = [
        f"{date_str}  {pct}%",
        _progress_bar(plan.progress, width=30),
        "",
    ]

    for block in plan.blocks:
        lines.append(format_block_line(block, now))

    return "\n".join(lines)


def format_status_line(plan: DailyPlan, now: time | None = None) -> str:
    """One-line status for use in status bars (polybar, waybar, etc.).

    Example: 'DW: 45% | ▶ Gym (11:00–11:45)'
    """
    if now is None:
        now = datetime.now().time()

    pct = plan.progress_percent
    current = plan.current_block(now)

    if current:
        start = current.start.strftime("%H:%M")
        end = current.end.strftime("%H:%M")
        return f"DW: {pct}% | ▶ {current.label} ({start}–{end})"

    next_block = plan.next_block(now)
    if next_block:
        start = next_block.start.strftime("%H:%M")
        return f"DW: {pct}% | Next: {next_block.label} ({start})"

    return f"DW: {pct}% | Done for today"


def _progress_bar(fraction: float, width: int = 30) -> str:
    """Render a text progress bar."""
    filled = round(fraction * width)
    empty = width - filled
    return "━" * filled + "░" * empty
