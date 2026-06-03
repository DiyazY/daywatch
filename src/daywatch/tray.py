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

# Error-state messages surfaced in the tray menu/tooltip. The full, actionable
# remediation goes to the log; these are the short forms that fit a tray UI.
_ERR_PERMISSION = "Can't read plan file"
_ERR_PERMISSION_HINT = "Grant Full Disk Access & restart"
_ERR_PARSE = "Couldn't parse plan file"
_ERR_PARSE_HINT = "See logs for details"


def _create_icon(
    progress: float = 0.0,
    active: bool = False,
    no_plan: bool = False,
    error: bool = False,
) -> Image:
    """Generate a tray icon dynamically based on state.

    Args:
        progress: Completion fraction (0.0 to 1.0) for the progress ring.
        active: Whether there's an active block (changes accent color).
        no_plan: Whether no plan file was found (grey icon with ?).
        error: Whether the plan file exists but couldn't be read (red icon with !).

    Returns:
        A PIL Image suitable for use as a tray icon.
    """
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if error:
        # Red circle with "!" — the file is present but unreadable. Distinct from
        # the grey "?" so an access problem doesn't look like a missing plan.
        draw.ellipse([4, 4, 60, 60], fill=(220, 38, 38, 220))
        draw.text((26, 14), "!", fill=(255, 255, 255, 255))
        return img

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
        # Distinct from ``plan is None``: the file exists but couldn't be read/parsed.
        self.error: str | None = None
        self.error_hint: str | None = None
        self._current_date: date = date.today()
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

    def _set_error(self, summary: str, hint: str | None, detail: str) -> None:
        """Enter an error state, surface it in the tray, and log ``detail`` once.

        The previously loaded plan (if any) is intentionally left untouched so a
        transient read failure doesn't wipe a good plan. ``detail`` (the full,
        actionable remediation) is logged only when the error first appears or
        changes, so the 60s refresh loop doesn't flood the log with duplicates.
        """
        is_new = self.error != summary
        self.error = summary
        self.error_hint = hint
        if is_new:
            logger.error("%s", detail)
        self._update_tray()

    def _clear_error(self) -> None:
        """Leave the error state (called when the file is absent or loads cleanly)."""
        self.error = None
        self.error_hint = None

    def _load_plan(self, path: Path | None = None) -> None:
        """Load (or reload) the daily plan."""
        if path is None:
            path = self._get_today_plan_path()

        if not path.exists():
            logger.warning("Plan file not found: %s", path)
            self.plan = None
            self._clear_error()
            self._update_tray()
            return

        try:
            plan = parse_file(path)
        except PermissionError as e:
            self._set_error(
                _ERR_PERMISSION,
                _ERR_PERMISSION_HINT,
                f"Permission denied reading plan file: {path}. Grant Full Disk Access "
                "to the app you launch DayWatch from (System Settings → Privacy & "
                f"Security → Full Disk Access), then quit and reopen it. ({e})",
            )
            return
        except Exception as e:
            self._set_error(_ERR_PARSE, _ERR_PARSE_HINT, f"Failed to parse plan {path}: {e}")
            return

        self.plan = plan
        self._clear_error()
        logger.info(
            "Loaded plan for %s: %d blocks, %d%% done",
            plan.date,
            len(plan.blocks),
            plan.progress_percent,
        )
        self.scheduler.update(plan)
        self._update_tray()

    def _on_file_change(self, path: Path) -> None:
        """Callback when the plan file changes."""
        logger.info("Plan file changed, reloading...")
        self._load_plan(path)

    def _build_menu(self):
        """Build the pystray menu from current plan state."""
        import pystray

        items = []

        if self.error is not None:
            items.append(pystray.MenuItem(f"⚠️ {self.error}", None, enabled=False))
            if self.error_hint:
                items.append(pystray.MenuItem(self.error_hint, None, enabled=False))
            items.append(pystray.Menu.SEPARATOR)

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
        elif self.error is None:
            # Only claim "no plan" when there genuinely isn't one — not when the
            # file exists but we couldn't read it (that's shown as a warning above).
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
        if self.error is not None:
            self._tray.icon = _create_icon(error=True)
            tooltip = f"DayWatch — {self.error}"
            if self.error_hint:
                tooltip += f" ({self.error_hint})"
            self._tray.title = tooltip
        elif self.plan is None:
            self._tray.icon = _create_icon(no_plan=True)
            self._tray.title = "DayWatch"
        else:
            active = self.plan.current_block(now) is not None
            self._tray.icon = _create_icon(progress=self.plan.progress, active=active)
            self._tray.title = "DayWatch"

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

        # Start file watcher (always, even if file doesn't exist yet)
        plan_path = self._get_today_plan_path()
        plan_path.parent.mkdir(parents=True, exist_ok=True)
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
                    today = date.today()

                    # Day rollover: switch to new plan file at midnight
                    if today != self._current_date:
                        logger.info(
                            "Day changed from %s to %s, reloading plan",
                            self._current_date,
                            today,
                        )
                        self._current_date = today
                        new_path = self._get_today_plan_path()
                        new_path.parent.mkdir(parents=True, exist_ok=True)
                        if self.watcher:
                            self.watcher.update_path(new_path)
                        self._load_plan()
                        continue

                    # Detect plan file appearance (belt-and-suspenders)
                    if self.plan is None:
                        plan_path = self._get_today_plan_path()
                        if plan_path.exists():
                            logger.info("Plan file appeared, loading...")
                            self._load_plan()
                            continue

                    self._update_tray()
                except Exception:
                    pass

        refresh_thread = threading.Thread(target=_periodic_refresh, daemon=True)
        refresh_thread.start()

        logger.info("DayWatch tray started")
        self._tray.run()
