"""Notification scheduler for DayWatch.

Maintains a schedule of upcoming notifications based on parsed time blocks.
Fires native desktop notifications via plyer at the right moments.
"""

from __future__ import annotations

import logging
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


def _send_notification(title: str, message: str, sound: bool = True) -> None:
    """Send a native OS notification via plyer."""
    try:
        from plyer import notification

        notification.notify(
            title=title,
            message=message,
            app_name="DayWatch",
            timeout=10,
        )
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

            # Schedule "coming up" notification
            lead_time = block_start - timedelta(minutes=self.lead_time_minutes)
            if lead_time > now:
                delay = (lead_time - now).total_seconds()
                timer = threading.Timer(
                    delay,
                    self._fire_lead_notification,
                    args=(block,),
                )
                timer.daemon = True
                timer.start()
                self._timers.append(timer)
                scheduled += 1
                logger.debug(
                    "Scheduled lead notification for '%s' in %.0fs",
                    block.label,
                    delay,
                )

            # Schedule "now starting" notification
            if self.notify_on_start and block_start > now:
                delay = (block_start - now).total_seconds()
                timer = threading.Timer(
                    delay,
                    self._fire_start_notification,
                    args=(block,),
                )
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

    @property
    def pending_count(self) -> int:
        """Number of pending notification timers."""
        return sum(1 for t in self._timers if t.is_alive())
