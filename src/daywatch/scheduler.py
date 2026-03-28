"""Notification scheduler for DayWatch.

Maintains a schedule of upcoming notifications based on parsed time blocks.
Fires native desktop notifications at the right moments using platform-specific
commands (osascript on macOS, notify-send on Linux, PowerShell on Windows).
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
from datetime import datetime, time, timedelta
from typing import Callable

from daywatch.parser import DailyPlan, TimeBlock

logger = logging.getLogger(__name__)


def _time_to_datetime(t: time, base_date: datetime | None = None) -> datetime:
    """Convert a time object to a datetime using today's date."""
    if base_date is None:
        base_date = datetime.now()
    return base_date.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)


def _applescript_quote(s: str) -> str:
    """Escape a string for use in an AppleScript literal."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _ps_escape(s: str) -> str:
    """Escape a string for PowerShell single-quoted context."""
    return s.replace("'", "''")


def _send_notification(title: str, message: str, sound: bool = True) -> None:
    """Send a native OS notification using platform-specific commands."""
    try:
        if sys.platform == "darwin":
            script = (
                f"display notification {_applescript_quote(message)}"
                f" with title {_applescript_quote(title)}"
            )
            if sound:
                script += ' sound name "default"'
            subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "win32":
            ps_script = (
                "[Windows.UI.Notifications.ToastNotificationManager,"
                " Windows.UI.Notifications, ContentType = WindowsRuntime]"
                " | Out-Null\n"
                "$t = [Windows.UI.Notifications.ToastNotificationManager]::"
                "GetTemplateContent("
                "[Windows.UI.Notifications.ToastTemplateType]::ToastText02)\n"
                "$n = $t.GetElementsByTagName('text')\n"
                f"$n.Item(0).AppendChild($t.CreateTextNode('{_ps_escape(title)}'))"
                " | Out-Null\n"
                f"$n.Item(1).AppendChild($t.CreateTextNode('{_ps_escape(message)}'))"
                " | Out-Null\n"
                "$toast = [Windows.UI.Notifications.ToastNotification]::new($t)\n"
                "[Windows.UI.Notifications.ToastNotificationManager]::"
                "CreateToastNotifier('DayWatch').Show($toast)"
            )
            subprocess.Popen(
                ["powershell", "-Command", ps_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            cmd = ["notify-send", title, message]
            if not sound:
                cmd.extend(["--hint", "int:suppress-sound:1"])
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        logger.warning("Failed to send notification: %s", e)


class Scheduler:
    """Schedules and fires notifications for upcoming time blocks.

    Usage:
        scheduler = Scheduler(lead_time_minutes=5, notify_on_start=True)
        scheduler.update(plan)
        # ... notifications fire automatically via timers ...
        scheduler.cancel_all()
    """

    def __init__(
        self,
        lead_time_minutes: int = 5,
        notify_on_start: bool = True,
        sound: bool = True,
        on_notification: Callable[[str, str], None] | None = None,
    ) -> None:
        self.lead_time_minutes = lead_time_minutes
        self.notify_on_start = notify_on_start
        self.sound = sound
        self._timers: list[threading.Timer] = []
        self._muted_blocks: set[str] = set()  # Labels of muted blocks
        self._notified_active: set[str] = set()  # Block keys already notified as active
        # Optional callback for custom notification handling (e.g., UI updates)
        self._on_notification = on_notification or _send_notification

    def update(self, plan: DailyPlan) -> int:
        """Reschedule notifications based on a (possibly updated) plan.

        Cancels all existing timers and creates new ones for upcoming blocks.

        Args:
            plan: The parsed daily plan.

        Returns:
            Number of notifications scheduled.
        """
        self.cancel_all()

        now = datetime.now()
        scheduled = 0

        for block in plan.blocks:
            if block.completed or block.failed:
                continue
            if block.label in self._muted_blocks:
                continue

            block_start = _time_to_datetime(block.start, now)
            now_time = now.time()

            # Case 1: Block is currently active (app started mid-block)
            if block.start <= now_time < block.end:
                block_key = f"{block.start}-{block.label}"
                if block_key not in self._notified_active:
                    self._notified_active.add(block_key)
                    timer = threading.Timer(
                        0.1, self._fire_active_notification, args=(block,)
                    )
                    timer.daemon = True
                    timer.start()
                    self._timers.append(timer)
                    scheduled += 1
                    logger.debug("Immediate active notification for '%s'", block.label)
                else:
                    logger.debug("Skipped duplicate active notification for '%s'", block.label)
                continue  # No need to schedule lead/start for an active block

            # Case 2+3: Block hasn't started yet — schedule lead + start
            lead_time = block_start - timedelta(minutes=self.lead_time_minutes)

            if lead_time >= now:
                # Normal future lead notification
                delay = (lead_time - now).total_seconds()
                timer = threading.Timer(delay, self._fire_lead_notification, args=(block,))
                timer.daemon = True
                timer.start()
                self._timers.append(timer)
                scheduled += 1
                logger.debug(
                    "Scheduled lead notification for '%s' in %.0fs",
                    block.label,
                    delay,
                )
            elif lead_time < now < block_start:
                # Lead time passed but block not started — fire immediately
                timer = threading.Timer(0.1, self._fire_lead_notification, args=(block,))
                timer.daemon = True
                timer.start()
                self._timers.append(timer)
                scheduled += 1
                logger.debug(
                    "Immediate lead notification for '%s' (lead time passed)",
                    block.label,
                )

            # Schedule "now starting" notification
            if self.notify_on_start and block_start >= now:
                delay = (block_start - now).total_seconds()
                timer = threading.Timer(delay, self._fire_start_notification, args=(block,))
                timer.daemon = True
                timer.start()
                self._timers.append(timer)
                scheduled += 1
                logger.debug(
                    "Scheduled start notification for '%s' in %.0fs",
                    block.label,
                    delay,
                )

        logger.info("Scheduled %d notifications for %s", scheduled, plan.date)
        return scheduled

    def cancel_all(self) -> None:
        """Cancel all pending notification timers."""
        for timer in self._timers:
            timer.cancel()
        self._timers.clear()

    def mute_block(self, label: str) -> None:
        """Mute notifications for a specific block label."""
        self._muted_blocks.add(label)

    def unmute_block(self, label: str) -> None:
        """Unmute notifications for a specific block label."""
        self._muted_blocks.discard(label)

    def _fire_lead_notification(self, block: TimeBlock) -> None:
        """Fire the 'coming up' notification."""
        start_str = block.start.strftime("%H:%M")
        end_str = block.end.strftime("%H:%M")
        title = f"⏰ In {self.lead_time_minutes} min: {block.label}"
        message = f"{start_str} – {end_str}"
        logger.info("Notification: %s", title)
        self._on_notification(title, message)

    def _fire_start_notification(self, block: TimeBlock) -> None:
        """Fire the 'now starting' notification."""
        start_str = block.start.strftime("%H:%M")
        end_str = block.end.strftime("%H:%M")
        title = f"▶ Now: {block.label}"
        message = f"{start_str} – {end_str}"
        logger.info("Notification: %s", title)
        self._on_notification(title, message)

    def _fire_active_notification(self, block: TimeBlock) -> None:
        """Fire notification for a block that is currently active (app started mid-block)."""
        start_str = block.start.strftime("%H:%M")
        end_str = block.end.strftime("%H:%M")
        title = f"▶ Active: {block.label}"
        message = f"{start_str} – {end_str} (in progress)"
        logger.info("Notification: %s", title)
        self._on_notification(title, message)

    @property
    def pending_count(self) -> int:
        """Number of pending notification timers."""
        return sum(1 for t in self._timers if t.is_alive())
