"""Tests for the file system watcher."""

from unittest.mock import MagicMock

from watchdog.events import FileCreatedEvent, FileModifiedEvent

from daywatch.watcher import PlanFileHandler


class TestPlanFileHandler:
    def test_on_created_triggers_callback(self, tmp_path):
        """File creation should trigger the callback."""
        plan_path = tmp_path / "plan.md"
        callback = MagicMock()
        handler = PlanFileHandler(plan_path, callback)

        event = FileCreatedEvent(str(plan_path))
        handler.on_created(event)

        callback.assert_called_once_with(plan_path.resolve())

    def test_on_created_ignores_other_files(self, tmp_path):
        """Creation of a different file should not trigger the callback."""
        plan_path = tmp_path / "plan.md"
        other_path = tmp_path / "other.md"
        callback = MagicMock()
        handler = PlanFileHandler(plan_path, callback)

        event = FileCreatedEvent(str(other_path))
        handler.on_created(event)

        callback.assert_not_called()

    def test_on_modified_still_works(self, tmp_path):
        """File modification should still trigger the callback (regression)."""
        plan_path = tmp_path / "plan.md"
        callback = MagicMock()
        handler = PlanFileHandler(plan_path, callback)

        event = FileModifiedEvent(str(plan_path))
        handler.on_modified(event)

        callback.assert_called_once_with(plan_path.resolve())

    def test_ignores_directory_events(self, tmp_path):
        """Directory events should be ignored."""
        plan_path = tmp_path / "plan.md"
        callback = MagicMock()
        handler = PlanFileHandler(plan_path, callback)

        event = FileModifiedEvent(str(tmp_path))
        event.is_directory = True  # type: ignore[attr-defined]
        handler.on_modified(event)

        callback.assert_not_called()
