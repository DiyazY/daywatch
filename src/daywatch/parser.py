"""Markdown daily plan parser.

Parses time-blocked daily plans in the DayWatch format:

    ## Day Planner
    - [ ] 08:00 - 09:00 Planning
    - [x] 09:00 - 11:00 Deep work
        - [x] Write tests
        - [ ] Review PR
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path


class BlockStatus(Enum):
    """Status of a time block."""

    UPCOMING = "upcoming"
    ACTIVE = "active"
    COMPLETED = "completed"
    MISSED = "missed"
    FAILED = "failed"


# Matches: - [ ] 8:00 - 9:30 Some label  OR  - [x] 08:00 - 11:00 Some label
TIME_BLOCK_RE = re.compile(
    r"^- \[(x| )\]\s+(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s+(.+)$"
)

# Matches indented subtasks: \t- [ ] subtask label  OR  \t- [x] subtask label
SUBTASK_RE = re.compile(r"^\s+- \[(x| )\]\s+(.+)$")

# Matches the 🔴 marker anywhere on a line
FAILED_MARKER = "🔴"


@dataclass
class SubTask:
    """A subtask nested under a time block."""

    label: str
    completed: bool

    def to_dict(self) -> dict:
        return {"label": self.label, "completed": self.completed}


@dataclass
class TimeBlock:
    """A time-blocked entry in a daily plan."""

    start: time
    end: time
    label: str
    completed: bool
    failed: bool
    subtasks: list[SubTask] = field(default_factory=list)

    def status(self, now: time | None = None) -> BlockStatus:
        """Determine the current status of this block."""
        if self.completed:
            return BlockStatus.COMPLETED
        if self.failed:
            return BlockStatus.FAILED
        if now is None:
            now = datetime.now().time()
        if self.start <= now < self.end:
            return BlockStatus.ACTIVE
        if now >= self.end:
            return BlockStatus.MISSED
        return BlockStatus.UPCOMING

    @property
    def duration_minutes(self) -> int:
        """Duration of the block in minutes."""
        start_min = self.start.hour * 60 + self.start.minute
        end_min = self.end.hour * 60 + self.end.minute
        return end_min - start_min

    def to_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "label": self.label,
            "completed": self.completed,
            "failed": self.failed,
            "subtasks": [s.to_dict() for s in self.subtasks],
        }


@dataclass
class DailyPlan:
    """A parsed daily plan."""

    date: date
    blocks: list[TimeBlock] = field(default_factory=list)
    todo_notes: str = ""
    daily_notes: str = ""

    @property
    def progress(self) -> float:
        """Fraction of top-level blocks completed (0.0 to 1.0)."""
        if not self.blocks:
            return 0.0
        done = sum(1 for b in self.blocks if b.completed)
        return done / len(self.blocks)

    @property
    def progress_percent(self) -> int:
        """Progress as an integer percentage."""
        return round(self.progress * 100)

    def current_block(self, now: time | None = None) -> TimeBlock | None:
        """Return the currently active block, if any."""
        if now is None:
            now = datetime.now().time()
        for block in self.blocks:
            if block.status(now) == BlockStatus.ACTIVE:
                return block
        return None

    def next_block(self, now: time | None = None) -> TimeBlock | None:
        """Return the next upcoming block, if any."""
        if now is None:
            now = datetime.now().time()
        for block in self.blocks:
            if block.status(now) == BlockStatus.UPCOMING:
                return block
        return None

    def failed_blocks(self) -> list[TimeBlock]:
        """Return all blocks marked as failed."""
        return [b for b in self.blocks if b.failed]

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "blocks": [b.to_dict() for b in self.blocks],
            "progress": self.progress_percent,
            "todo_notes": self.todo_notes,
            "daily_notes": self.daily_notes,
        }


def _parse_time(s: str) -> time:
    """Parse a time string like '8:00' or '08:30' into a time object."""
    parts = s.strip().split(":")
    return time(int(parts[0]), int(parts[1]))


def parse_daily_plan(content: str, plan_date: date | None = None) -> DailyPlan:
    """Parse a daily plan markdown string into a DailyPlan object.

    Args:
        content: The raw markdown content of the daily plan file.
        plan_date: The date of the plan. If None, uses today.

    Returns:
        A DailyPlan object with parsed time blocks and metadata.
    """
    if plan_date is None:
        plan_date = date.today()

    plan = DailyPlan(date=plan_date)
    lines = content.splitlines()

    current_block: TimeBlock | None = None
    current_section: str | None = None
    section_lines: dict[str, list[str]] = {
        "todo_notes": [],
        "daily_notes": [],
    }

    for line in lines:
        stripped = line.strip()

        # Track which section we're in
        lower = stripped.lower()
        if lower.startswith("## todo") or lower.startswith("## todo notes"):
            current_section = "todo_notes"
            current_block = None
            continue
        elif lower.startswith("## daily notes") or lower == "# daily notes":
            current_section = "daily_notes"
            current_block = None
            continue
        elif lower.startswith("## time tracking"):
            current_section = "time_tracking"
            current_block = None
            continue
        elif (
            lower.startswith("## day planner")
            or lower.startswith("# day planner")
        ):
            current_section = "planner"
            current_block = None
            continue
        elif stripped.startswith("## ") or stripped.startswith("# "):
            current_section = "other"
            current_block = None
            continue

        # Parse time blocks (only in planner section or before any section)
        if current_section in ("planner", None):
            block_match = TIME_BLOCK_RE.match(stripped)
            if block_match:
                completed = block_match.group(1) == "x"
                start = _parse_time(block_match.group(2))
                end = _parse_time(block_match.group(3))
                label = block_match.group(4).strip()
                is_failed = FAILED_MARKER in label
                # Clean the failed marker from label
                clean_label = label.replace(FAILED_MARKER, "").strip()

                current_block = TimeBlock(
                    start=start,
                    end=end,
                    label=clean_label,
                    completed=completed,
                    failed=is_failed,
                )
                plan.blocks.append(current_block)
                continue

            # Parse subtasks
            subtask_match = SUBTASK_RE.match(line)  # Use original line (with indent)
            if subtask_match and current_block is not None:
                sub_completed = subtask_match.group(1) == "x"
                sub_label = subtask_match.group(2).strip()
                is_sub_failed = FAILED_MARKER in sub_label
                clean_sub_label = sub_label.replace(FAILED_MARKER, "").strip()
                current_block.subtasks.append(
                    SubTask(label=clean_sub_label, completed=sub_completed or is_sub_failed)
                )
                continue

        # Collect section content
        if current_section in section_lines:
            section_lines[current_section].append(line)

    plan.todo_notes = "\n".join(section_lines["todo_notes"]).strip()
    plan.daily_notes = "\n".join(section_lines["daily_notes"]).strip()

    return plan


def parse_file(path: Path, plan_date: date | None = None) -> DailyPlan:
    """Parse a daily plan from a file path.

    Args:
        path: Path to the markdown file.
        plan_date: The date of the plan. If None, attempts to extract from filename.

    Returns:
        A DailyPlan object.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    content = path.read_text(encoding="utf-8")

    if plan_date is None:
        # Try to extract date from filename like 2026-03-24.md
        date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", path.stem)
        if date_match:
            plan_date = date(
                int(date_match.group(1)),
                int(date_match.group(2)),
                int(date_match.group(3)),
            )
        else:
            plan_date = date.today()

    return parse_daily_plan(content, plan_date)


def extract_failed_items(content: str) -> list[str]:
    """Extract labels of failed items (marked with 🔴) from a plan.

    Useful for showing "yesterday's failures" summary.

    Args:
        content: Raw markdown content of a plan file.

    Returns:
        List of failed task labels.
    """
    failed = []
    for line in content.splitlines():
        if FAILED_MARKER in line:
            block_match = TIME_BLOCK_RE.match(line.strip())
            if block_match:
                label = block_match.group(4).replace(FAILED_MARKER, "").strip()
                failed.append(label)
            else:
                subtask_match = SUBTASK_RE.match(line)
                if subtask_match:
                    label = subtask_match.group(2).replace(FAILED_MARKER, "").strip()
                    failed.append(label)
    return failed
