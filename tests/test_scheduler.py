"""Tests for the notification scheduler."""

from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from daywatch.parser import DailyPlan, TimeBlock
from daywatch.scheduler import Scheduler, _send_notification


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

    def test_active_block_fires_immediate_notification(self):
        """Mid-block startup should fire an immediate 'active' notification."""
        import time as _time

        notifications = []

        def capture(title, message):
            notifications.append((title, message))

        now = datetime.now()
        start = (now - timedelta(minutes=30)).time()
        end = (now + timedelta(minutes=30)).time()

        plan = _make_plan([_block(start.hour, start.minute, end.hour, end.minute, "active task")])

        scheduler = Scheduler(lead_time_minutes=5, on_notification=capture)
        count = scheduler.update(plan)

        assert count >= 1
        _time.sleep(0.3)  # Wait for the 0.1s timer to fire

        assert len(notifications) >= 1
        assert "Active" in notifications[0][0]
        scheduler.cancel_all()

    def test_missed_lead_fires_immediate(self):
        """Lead time passed but block not started should fire lead notification immediately."""
        import time as _time

        notifications = []

        def capture(title, message):
            notifications.append((title, message))

        now = datetime.now()
        # Block starts 3 min from now, lead_time is 5 min => lead was 2 min ago
        start = (now + timedelta(minutes=3)).time()
        end = (now + timedelta(minutes=63)).time()

        plan = _make_plan([_block(start.hour, start.minute, end.hour, end.minute, "upcoming task")])

        scheduler = Scheduler(lead_time_minutes=5, on_notification=capture)
        count = scheduler.update(plan)

        # Should have: 1 immediate lead + 1 future start = at least 2
        assert count >= 2
        _time.sleep(0.3)

        # The immediate lead notification should have fired
        assert len(notifications) >= 1
        assert "upcoming task" in notifications[0][1] or "upcoming task" in notifications[0][0]
        scheduler.cancel_all()

    def test_active_block_skips_start_notification(self):
        """Active block should only get 'active' notification, not 'now starting'."""
        import time as _time

        notifications = []

        def capture(title, message):
            notifications.append((title, message))

        now = datetime.now()
        start = (now - timedelta(minutes=15)).time()
        end = (now + timedelta(minutes=45)).time()

        plan = _make_plan([_block(start.hour, start.minute, end.hour, end.minute, "task")])

        scheduler = Scheduler(lead_time_minutes=5, on_notification=capture)
        count = scheduler.update(plan)

        assert count == 1  # Only the active notification
        _time.sleep(0.3)

        assert len(notifications) == 1
        assert "Active" in notifications[0][0]
        assert "Now" not in notifications[0][0]
        scheduler.cancel_all()

    def test_active_notification_not_repeated_on_reload(self):
        """Reloading the plan should not re-fire the active block notification."""
        import time as _time

        notifications = []

        def capture(title, message):
            notifications.append((title, message))

        now = datetime.now()
        start = (now - timedelta(minutes=15)).time()
        end = (now + timedelta(minutes=45)).time()

        plan = _make_plan([_block(start.hour, start.minute, end.hour, end.minute, "task")])

        scheduler = Scheduler(lead_time_minutes=5, on_notification=capture)
        scheduler.update(plan)
        _time.sleep(0.3)

        assert len(notifications) == 1

        # Simulate file edit → reload
        scheduler.update(plan)
        _time.sleep(0.3)

        # Should still be 1, not 2
        assert len(notifications) == 1
        scheduler.cancel_all()

    def test_completed_active_block_skipped(self):
        """A block that is active in time but marked completed gets no notifications."""
        now = datetime.now()
        start = (now - timedelta(minutes=15)).time()
        end = (now + timedelta(minutes=45)).time()

        plan = _make_plan(
            [_block(start.hour, start.minute, end.hour, end.minute, "done", completed=True)]
        )

        scheduler = Scheduler(lead_time_minutes=5)
        count = scheduler.update(plan)

        assert count == 0
        scheduler.cancel_all()


class TestSendNotification:
    @patch("daywatch.scheduler.sys")
    @patch("daywatch.scheduler.subprocess.Popen")
    def test_macos_uses_osascript(self, mock_popen, mock_sys):
        """On macOS, should call osascript."""
        mock_sys.platform = "darwin"
        _send_notification("Test Title", "Test message")
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[0] == "osascript"
        assert "-e" in args

    @patch("daywatch.scheduler.sys")
    @patch("daywatch.scheduler.subprocess.Popen")
    def test_linux_uses_notify_send(self, mock_popen, mock_sys):
        """On Linux, should call notify-send."""
        mock_sys.platform = "linux"
        _send_notification("Test Title", "Test message")
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[0] == "notify-send"

    @patch("daywatch.scheduler.sys")
    @patch("daywatch.scheduler.subprocess.Popen")
    def test_windows_uses_powershell(self, mock_popen, mock_sys):
        """On Windows, should call powershell."""
        mock_sys.platform = "win32"
        _send_notification("Test Title", "Test message")
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[0] == "powershell"

    @patch("daywatch.scheduler.sys")
    @patch("daywatch.scheduler.subprocess.Popen")
    def test_macos_sound_included_by_default(self, mock_popen, mock_sys):
        """macOS notification should include sound by default."""
        mock_sys.platform = "darwin"
        _send_notification("Title", "Msg", sound=True)
        script = mock_popen.call_args[0][0][2]
        assert "sound name" in script

    @patch("daywatch.scheduler.sys")
    @patch("daywatch.scheduler.subprocess.Popen")
    def test_macos_no_sound(self, mock_popen, mock_sys):
        """macOS notification with sound=False should omit sound."""
        mock_sys.platform = "darwin"
        _send_notification("Title", "Msg", sound=False)
        script = mock_popen.call_args[0][0][2]
        assert "sound name" not in script

    @patch("daywatch.scheduler.subprocess.Popen", side_effect=FileNotFoundError("no cmd"))
    def test_handles_missing_command(self, mock_popen):
        """Should log warning, not crash, when notification command is missing."""
        _send_notification("Title", "Msg")  # Should not raise
