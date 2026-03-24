"""Tests for the notification scheduler."""

from datetime import date, datetime, time, timedelta

from daywatch.parser import DailyPlan, TimeBlock
from daywatch.scheduler import Scheduler


def _make_plan(blocks: list[TimeBlock]) -> DailyPlan:
    return DailyPlan(date=date.today(), blocks=blocks)


def _block(
    start_h: int,
    start_m: int,
    end_h: int,
    end_m: int,
    label: str,
    completed: bool = False,
    failed: bool = False,
) -> TimeBlock:
    return TimeBlock(
        start=time(start_h, start_m),
        end=time(end_h, end_m),
        label=label,
        completed=completed,
        failed=failed,
    )


class TestScheduler:
    def test_schedules_upcoming_blocks(self):
        """Should schedule notifications for future blocks."""
        now = datetime.now()
        # Create a block 30 minutes from now
        future = (now + timedelta(minutes=30)).time()
        future_end = (now + timedelta(minutes=90)).time()

        plan = _make_plan(
            [
                _block(
                    future.hour, future.minute, future_end.hour, future_end.minute, "future task"
                ),
            ]
        )

        scheduler = Scheduler(lead_time_minutes=5, notify_on_start=True)
        count = scheduler.update(plan)

        assert count == 2  # lead + start
        assert scheduler.pending_count == 2

        scheduler.cancel_all()

    def test_skips_completed_blocks(self):
        """Should not schedule notifications for completed blocks."""
        now = datetime.now()
        future = (now + timedelta(minutes=30)).time()
        future_end = (now + timedelta(minutes=90)).time()

        plan = _make_plan(
            [
                _block(
                    future.hour,
                    future.minute,
                    future_end.hour,
                    future_end.minute,
                    "done task",
                    completed=True,
                ),
            ]
        )

        scheduler = Scheduler(lead_time_minutes=5)
        count = scheduler.update(plan)

        assert count == 0
        scheduler.cancel_all()

    def test_skips_failed_blocks(self):
        """Should not schedule notifications for failed blocks."""
        now = datetime.now()
        future = (now + timedelta(minutes=30)).time()
        future_end = (now + timedelta(minutes=90)).time()

        plan = _make_plan(
            [
                _block(
                    future.hour,
                    future.minute,
                    future_end.hour,
                    future_end.minute,
                    "failed task",
                    failed=True,
                ),
            ]
        )

        scheduler = Scheduler(lead_time_minutes=5)
        count = scheduler.update(plan)

        assert count == 0
        scheduler.cancel_all()

    def test_skips_past_blocks(self):
        """Should not schedule notifications for blocks that already passed."""
        plan = _make_plan(
            [
                _block(0, 0, 0, 30, "past task"),
            ]
        )

        scheduler = Scheduler(lead_time_minutes=5)
        count = scheduler.update(plan)

        assert count == 0
        scheduler.cancel_all()

    def test_cancel_all(self):
        """cancel_all should clear all timers."""
        now = datetime.now()
        future = (now + timedelta(minutes=30)).time()
        future_end = (now + timedelta(minutes=90)).time()

        plan = _make_plan(
            [
                _block(future.hour, future.minute, future_end.hour, future_end.minute, "task"),
            ]
        )

        scheduler = Scheduler(lead_time_minutes=5)
        scheduler.update(plan)
        assert scheduler.pending_count > 0

        scheduler.cancel_all()
        assert scheduler.pending_count == 0

    def test_mute_block(self):
        """Muted blocks should be skipped."""
        now = datetime.now()
        future = (now + timedelta(minutes=30)).time()
        future_end = (now + timedelta(minutes=90)).time()

        plan = _make_plan(
            [
                _block(
                    future.hour, future.minute, future_end.hour, future_end.minute, "muted task"
                ),
            ]
        )

        scheduler = Scheduler(lead_time_minutes=5)
        scheduler.mute_block("muted task")
        count = scheduler.update(plan)

        assert count == 0
        scheduler.cancel_all()

    def test_update_replaces_previous(self):
        """Calling update again should cancel old timers and reschedule."""
        now = datetime.now()
        future = (now + timedelta(minutes=30)).time()
        future_end = (now + timedelta(minutes=90)).time()

        plan = _make_plan(
            [
                _block(future.hour, future.minute, future_end.hour, future_end.minute, "task"),
            ]
        )

        scheduler = Scheduler(lead_time_minutes=5)
        scheduler.update(plan)
        first_count = scheduler.pending_count

        # Update again — should cancel and reschedule
        scheduler.update(plan)
        second_count = scheduler.pending_count

        assert first_count == second_count
        scheduler.cancel_all()

    def test_no_start_notification_when_disabled(self):
        """Should only schedule lead notification when notify_on_start=False."""
        now = datetime.now()
        future = (now + timedelta(minutes=30)).time()
        future_end = (now + timedelta(minutes=90)).time()

        plan = _make_plan(
            [
                _block(future.hour, future.minute, future_end.hour, future_end.minute, "task"),
            ]
        )

        scheduler = Scheduler(lead_time_minutes=5, notify_on_start=False)
        count = scheduler.update(plan)

        assert count == 1  # Only lead notification
        scheduler.cancel_all()
