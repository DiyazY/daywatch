"""Tests for the tray app's plan-loading error handling.

These focus on the *state machine* in ``DayWatchTray._load_plan`` — specifically
that an unreadable plan file (``PermissionError``, the macOS Full Disk Access
case) is surfaced as a distinct, actionable error state rather than being
conflated with "no plan exists". The tray's pystray rendering is not exercised
here: ``_load_plan`` calls ``_update_tray`` which early-returns while
``self._tray is None``, so these run headless.
"""

from __future__ import annotations

import logging

from daywatch.config import Config, VaultConfig
from daywatch.scheduler import Scheduler
from daywatch.tray import _ERR_PARSE, DayWatchTray, _create_icon

VALID_PLAN = """\
# Day Planner
- [ ] 08:00 - 09:00 Morning routine
- [x] 09:00 - 11:00 Deep work
"""


def make_tray(tmp_path):
    """Build a tray with a no-op notification scheduler (no real desktop popups)."""
    config = Config(vault=VaultConfig(path=str(tmp_path)))
    tray = DayWatchTray(config=config)
    tray.scheduler = Scheduler(on_notification=lambda *a, **k: None)
    return tray


def write_plan(tmp_path, name="2026-06-02.md", content=VALID_PLAN):
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return f


def _raise_permission_error(path, plan_date=None):
    raise PermissionError(1, "Operation not permitted")


def test_permission_error_sets_actionable_error(tmp_path, monkeypatch, caplog):
    tray = make_tray(tmp_path)
    plan_file = write_plan(tmp_path)
    monkeypatch.setattr("daywatch.tray.parse_file", _raise_permission_error)

    with caplog.at_level(logging.ERROR):
        tray._load_plan(plan_file)

    # A distinct error state is set...
    assert tray.error is not None
    # ...and the actionable remediation (with the path) reaches the log.
    assert "Full Disk Access" in caplog.text
    assert str(plan_file) in caplog.text


def test_success_clears_previous_error(tmp_path):
    tray = make_tray(tmp_path)
    plan_file = write_plan(tmp_path)
    tray.error = _ERR_PARSE  # pretend a prior load left the tray in an error state

    tray._load_plan(plan_file)

    assert tray.error is None
    assert tray.plan is not None
    assert len(tray.plan.blocks) == 2


def test_transient_error_preserves_previous_plan(tmp_path, monkeypatch):
    tray = make_tray(tmp_path)
    plan_file = write_plan(tmp_path)

    tray._load_plan(plan_file)  # good load
    good_plan = tray.plan
    assert good_plan is not None

    monkeypatch.setattr("daywatch.tray.parse_file", _raise_permission_error)
    tray._load_plan(plan_file)  # now fails to read

    # A transient read failure must not wipe a previously-good plan.
    assert tray.plan is good_plan
    assert tray.error is not None


def test_generic_parse_error_is_distinct_from_permission(tmp_path, monkeypatch, caplog):
    tray = make_tray(tmp_path)
    plan_file = write_plan(tmp_path)

    def raise_value_error(path, plan_date=None):
        raise ValueError("malformed")

    monkeypatch.setattr("daywatch.tray.parse_file", raise_value_error)

    with caplog.at_level(logging.ERROR):
        tray._load_plan(plan_file)

    assert tray.error is not None
    # Generic parse failures must NOT claim it's a permissions problem.
    assert "Full Disk Access" not in tray.error.summary
    assert "Full Disk Access" not in tray.error.hint


def test_permission_error_logged_once_across_repeats(tmp_path, monkeypatch, caplog):
    tray = make_tray(tmp_path)
    plan_file = write_plan(tmp_path)
    monkeypatch.setattr("daywatch.tray.parse_file", _raise_permission_error)

    with caplog.at_level(logging.ERROR):
        tray._load_plan(plan_file)
        tray._load_plan(plan_file)
        tray._load_plan(plan_file)

    perm_logs = [r for r in caplog.records if "Full Disk Access" in r.getMessage()]
    assert len(perm_logs) == 1


def test_missing_file_is_not_an_error_state(tmp_path):
    tray = make_tray(tmp_path)
    missing = tmp_path / "does-not-exist.md"

    tray._load_plan(missing)

    # A genuinely absent file is "no plan", not an error.
    assert tray.plan is None
    assert tray.error is None


def test_create_icon_error_variant_returns_image():
    img = _create_icon(error=True)
    assert img.size == (64, 64)
