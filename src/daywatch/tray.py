"""System tray application for DayWatch.

Provides a persistent tray icon with a menu showing today's plan,
progress, and quick actions. Uses pystray for cross-platform support.
"""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw

from daywatch.config import Config, load_config
from daywatch.parser import DailyPlan, parse_file
from daywatch.scheduler import Scheduler
from daywatch.ui.preview import format_block_line
from daywatch.watcher import PlanWatcher

logger = logging.getLogger(__name__)

# Icon dimensions
ICON_SIZE = 64


def _create_icon(progress: float = 0.0, active: bool = False, no_plan: bool = False) -> Image:
    """Generate a tray icon dynamically based on state.

    Args:
        progress: Completion fraction (0.0 to 1.0) for the progress ring.
        active: Whether there's an active block (changes accent color).
        no_plan: Whether no plan file was found (grey icon with ?).

    Returns:
        A PIL Image suitable for use as a tray icon.
    """
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if no_plan:
        # Grey circle with "?"
        draw.ellipse([4, 4, 60, 60], fill=(128, 128, 128, 200))
        draw.text((22, 14), "?", fill=(255, 255, 255, 255))
        return img

    # Background circle
    bg_color = (59, 130, 246, 220) if active else (100, 116, 139, 220)
    draw.ellipse([4, 4, 60, 60], fill=bg_color)

    # Progress ring
    if progress > 0:
        angle = int(360 * progress)
        draw.arc([2, 2, 62, 62], -90, -90 + angle, fill=(34, 197, 94, 255), width=4)

    # Center dot
    draw.ellipse([26, 26, 38, 38], fill=(255, 255, 255, 240))

    return img


class DayWatchTray:
    """Main tray application.

    Coordinates the parser, scheduler, watcher, and tray menu.
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config()
        self.plan: DailyPlan | None = None
        self.scheduler = Scheduler(
            lead_time_minutes=self.config.notifications.lead_time_minutes,
            notify_on_start=self.config.notifications.notify_on_start,
            sound=self.config.notifications.sound,
        )
        self.watcher: PlanWatcher | None = None
        self._tray = None

    def _get_today_plan_path(self) -> Path:
        """Resolve the path to today's plan file."""
        today = date.today()
        return self.config.resolve_daily_plan_path(today.year, today.month, today.day)

    def _load_plan(self, path: Path | None = None) -> None:
        """Load (or reload) the daily plan."""
        if path is None:
            path = self._get_today_plan_path()

        if not path.exists():
            logger.warning("Plan file not found: %s", path)
            self.plan = None
            self._update_tray()
            return

        try:
            self.plan = parse_file(path)
            logger.info(
                "Loaded plan for %s: %d blocks, %d%% done",
                self.plan.date,
                len(self.plan.blocks),
                self.plan.progress_percent,
            )
            self.scheduler.update(self.plan)
            self._update_tray()
        except Exception as e:
            logger.error("Failed to parse plan: %s", e)

    def _on_file_change(self, path: Path) -> None:
        """Callback when the plan file changes."""
        logger.info("Plan file changed, reloading...")
        self._load_plan(path)

    def _build_menu(self):
        """Build the pystray menu from current plan state."""
        import pystray

        items = []

        if self.plan and self.plan.blocks:
            # Header: date + progress
            date_str = self.plan.date.strftime("%A, %d %b")
            pct = self.plan.progress_percent
            items.append(pystray.MenuItem(f"{date_str} — {pct}%", None, enabled=False))
            items.append(pystray.Menu.SEPARATOR)

            # Block list
            now = datetime.now().time()
            for block in self.plan.blocks:
                line = format_block_line(block, now)
                items.append(pystray.MenuItem(line, None, enabled=False))

            items.append(pystray.Menu.SEPARATOR)
        else:
            items.append(pystray.MenuItem("No plan for today", None, enabled=False))
            items.append(pystray.Menu.SEPARATOR)

        # Actions
        items.append(pystray.MenuItem("Refresh", lambda: self._load_plan()))
        items.append(pystray.MenuItem("Quit", self._quit))

        return pystray.Menu(*items)

    def _update_tray(self) -> None:
        """Update the tray icon and menu to reflect current state."""
        if self._tray is None:
            return

        now = datetime.now().time()
        if self.plan is None:
            self._tray.icon = _create_icon(no_plan=True)
        else:
            active = self.plan.current_block(now) is not None
            self._tray.icon = _create_icon(progress=self.plan.progress, active=active)

        self._tray.menu = self._build_menu()

    def _quit(self) -> None:
        """Clean shutdown."""
        logger.info("Shutting down DayWatch...")
        self.scheduler.cancel_all()
        if self.watcher:
            self.watcher.stop()
        if self._tray:
            self._tray.stop()

    def run(self) -> None:
        """Start the tray application (blocking)."""
        import pystray

        # Load today's plan
        self._load_plan()

        # Start file watcher
        plan_path = self._get_today_plan_path()
        if plan_path.exists():
            self.watcher = PlanWatcher(plan_path, self._on_file_change)
            self.watcher.start()

        # Create tray icon
        icon_img = _create_icon(
            progress=self.plan.progress if self.plan else 0.0,
            active=False,
            no_plan=self.plan is None,
        )

        self._tray = pystray.Icon(
            name="daywatch",
            icon=icon_img,
            title="DayWatch",
            menu=self._build_menu(),
        )

        # Periodic refresh (every 60s) to update active block highlighting
        def _periodic_refresh():
            import time as _time

            while self._tray is not None:
                _time.sleep(60)
                try:
                    self._update_tray()
                except Exception:
                    pass

        refresh_thread = threading.Thread(target=_periodic_refresh, daemon=True)
        refresh_thread.start()

        logger.info("DayWatch tray started")
        self._tray.run()
