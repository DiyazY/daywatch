"""Tests for the daily plan parser."""

from datetime import date, time

import pytest

from daywatch.parser import (
    BlockStatus,
    DailyPlan,
    SubTask,
    TimeBlock,
    extract_failed_items,
    parse_daily_plan,
)

# -- Sample plan content matching the real format --

SAMPLE_PLAN = """\
Check the prior day: do it until the roll mechanism is not implemented
# Day planner
- [x] 8:30 - 9:00 planning
- [x] 9:00 - 11:00 toptop
\t- [x] busypipe
\t- [ ] trade extension
- [ ] 11:00 - 11:45 gym
- [ ] 11:45 - 12:30 swedish
- [ ] 12:30 - 13:00 lunch
- [x] 13:00 - 15:30 uni
\t- [ ] finish the draft and send it
- [ ] 15:30 - 20:00 family
- [ ] 20:00 - 22:00 bp
\t- [ ] work on marketing campaign strategy
- [ ] 22:00 - 23:00 toptop

#### statuses
- ✅ - done
- 🔴 - failed
## TODO notes
- yesterday's failures
- week-13 open items

## Time tracking

| activity | time |
| -------- | ---- |
|          |      |
# daily notes
Start working on trade extension
"""

SAMPLE_PLAN_WITH_FAILURES = """\
# Day planner
- [x] 8:30 - 9:00 planning
- [x] 9:00 - 11:00 toptop
- [x] 11:00 - 12:00 gym
\t- [ ] swedish (check courses) 🔴
- [x] 12:00 - 13:00 lunch
- [x] 13:00 - 15:00 uni
\t- [ ] finish the draft and send it 🔴
- [x] 15:00 - 16:30 family
- [ ] 16:30 - 21:00 toastmaster 🔴
\t- [x] toptop
- [ ] 21:00 - 23:00 toptop
"""


class TestParseDaily:
    """Tests for parse_daily_plan."""

    def test_basic_parsing(self):
        plan = parse_daily_plan(SAMPLE_PLAN, date(2026, 3, 24))
        assert plan.date == date(2026, 3, 24)
        assert len(plan.blocks) == 9

    def test_completed_blocks(self):
        plan = parse_daily_plan(SAMPLE_PLAN, date(2026, 3, 24))
        completed = [b for b in plan.blocks if b.completed]
        assert len(completed) == 3
        assert completed[0].label == "planning"
        assert completed[1].label == "toptop"
        assert completed[2].label == "uni"

    def test_progress(self):
        plan = parse_daily_plan(SAMPLE_PLAN, date(2026, 3, 24))
        assert plan.progress == pytest.approx(3 / 9)
        assert plan.progress_percent == 33

    def test_subtasks(self):
        plan = parse_daily_plan(SAMPLE_PLAN, date(2026, 3, 24))
        toptop = plan.blocks[1]  # 9:00-11:00 toptop
        assert len(toptop.subtasks) == 2
        assert toptop.subtasks[0].label == "busypipe"
        assert toptop.subtasks[0].completed is True
        assert toptop.subtasks[1].label == "trade extension"
        assert toptop.subtasks[1].completed is False

    def test_time_parsing(self):
        plan = parse_daily_plan(SAMPLE_PLAN, date(2026, 3, 24))
        first = plan.blocks[0]
        assert first.start == time(8, 30)
        assert first.end == time(9, 0)
        assert first.label == "planning"

    def test_section_parsing(self):
        plan = parse_daily_plan(SAMPLE_PLAN, date(2026, 3, 24))
        assert "yesterday's failures" in plan.todo_notes
        assert "trade extension" in plan.daily_notes

    def test_empty_plan(self):
        plan = parse_daily_plan("# Day Planner\n", date(2026, 1, 1))
        assert len(plan.blocks) == 0
        assert plan.progress == 0.0

    def test_default_date(self):
        plan = parse_daily_plan("# Day Planner\n")
        assert plan.date == date.today()


class TestFailedItems:
    """Tests for failed item detection."""

    def test_failed_blocks(self):
        plan = parse_daily_plan(SAMPLE_PLAN_WITH_FAILURES, date(2026, 3, 23))
        failed = plan.failed_blocks()
        assert len(failed) == 1
        assert failed[0].label == "toastmaster"

    def test_extract_failed_items(self):
        failed = extract_failed_items(SAMPLE_PLAN_WITH_FAILURES)
        assert "toastmaster" in failed
        assert "swedish (check courses)" in failed
        assert "finish the draft and send it" in failed
        assert len(failed) == 3


class TestBlockStatus:
    """Tests for time block status determination."""

    def test_completed_status(self):
        block = TimeBlock(
            start=time(8, 0), end=time(9, 0),
            label="test", completed=True, failed=False,
        )
        assert block.status(time(8, 30)) == BlockStatus.COMPLETED

    def test_active_status(self):
        block = TimeBlock(
            start=time(8, 0), end=time(9, 0),
            label="test", completed=False, failed=False,
        )
        assert block.status(time(8, 30)) == BlockStatus.ACTIVE

    def test_upcoming_status(self):
        block = TimeBlock(
            start=time(14, 0), end=time(15, 0),
            label="test", completed=False, failed=False,
        )
        assert block.status(time(10, 0)) == BlockStatus.UPCOMING

    def test_missed_status(self):
        block = TimeBlock(
            start=time(8, 0), end=time(9, 0),
            label="test", completed=False, failed=False,
        )
        assert block.status(time(10, 0)) == BlockStatus.MISSED

    def test_failed_status(self):
        block = TimeBlock(
            start=time(8, 0), end=time(9, 0),
            label="test", completed=False, failed=True,
        )
        assert block.status(time(10, 0)) == BlockStatus.FAILED

    def test_duration(self):
        block = TimeBlock(
            start=time(9, 0), end=time(11, 30),
            label="test", completed=False, failed=False,
        )
        assert block.duration_minutes == 150


class TestDailyPlan:
    """Tests for DailyPlan methods."""

    def _make_plan(self):
        return DailyPlan(
            date=date(2026, 3, 24),
            blocks=[
                TimeBlock(time(8, 0), time(9, 0), "morning", True, False),
                TimeBlock(time(9, 0), time(11, 0), "work", False, False),
                TimeBlock(time(14, 0), time(15, 0), "afternoon", False, False),
            ],
        )

    def test_current_block(self):
        plan = self._make_plan()
        assert plan.current_block(time(9, 30)).label == "work"

    def test_current_block_none(self):
        plan = self._make_plan()
        assert plan.current_block(time(12, 0)) is None

    def test_next_block(self):
        plan = self._make_plan()
        assert plan.next_block(time(9, 30)).label == "afternoon"

    def test_next_block_none(self):
        plan = self._make_plan()
        assert plan.next_block(time(15, 30)) is None

    def test_to_dict(self):
        plan = self._make_plan()
        d = plan.to_dict()
        assert d["date"] == "2026-03-24"
        assert d["progress"] == 33
        assert len(d["blocks"]) == 3
