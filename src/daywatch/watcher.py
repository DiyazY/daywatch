"""File system watcher for daily plan files.

Uses watchdog to monitor the plan file for changes and trigger
re-parsing and notification rescheduling.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class PlanFileHandler(FileSystemEventHandler):
    """Watches a specific file and calls a callback when it changes."""

    def __init__(self, watch_path: Path, on_change: Callable[[Path], None]) -> None:
        super().__init__()
        self.watch_path = watch_path.resolve()
        self.on_change = on_change

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        changed = Path(event.src_path).resolve()
        if changed == self.watch_path:
            logger.info("Plan file changed: %s", changed)
            self.on_change(changed)


class PlanWatcher:
    """Watches a daily plan file for changes.

    Usage:
        watcher = PlanWatcher(plan_path, on_change=my_callback)
        watcher.start()
        # ... later ...
        watcher.stop()
    """

    def __init__(self, plan_path: Path, on_change: Callable[[Path], None]) -> None:
        self.plan_path = plan_path.resolve()
        self.on_change = on_change
        self._observer: Observer | None = None

    def start(self) -> None:
        """Start watching the plan file's parent directory."""
        if self._observer is not None:
            return

        handler = PlanFileHandler(self.plan_path, self.on_change)
        self._observer = Observer()
        # Watch the parent directory (watchdog can't watch individual files)
        self._observer.schedule(handler, str(self.plan_path.parent), recursive=False)
        self._observer.daemon = True
        self._observer.start()
        logger.info("Started watching: %s", self.plan_path)

    def stop(self) -> None:
        """Stop watching."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            logger.info("Stopped watching: %s", self.plan_path)

    def update_path(self, new_path: Path) -> None:
        """Switch to watching a different file (e.g., when the day changes)."""
        self.stop()
        self.plan_path = new_path.resolve()
        self.start()

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()
