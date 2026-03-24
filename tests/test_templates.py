"""Tests for the template system."""

from datetime import date

from daywatch.config import Config, VaultConfig
from daywatch.templates import _resolve_variables, create_plan, init_vault


class TestResolveVariables:
    def test_basic_replacement(self):
        result = _resolve_variables("{YYYY}-{MM}-{DD}", date(2026, 3, 24))
        assert result == "2026-03-24"

    def test_weekday(self):
        result = _resolve_variables("{WEEKDAY}", date(2026, 3, 24))
        assert result == "Tuesday"

    def test_week_number(self):
        result = _resolve_variables("week-{WW}", date(2026, 3, 24))
        assert result == "week-13"

    def test_zero_padding(self):
        result = _resolve_variables("{MM}/{DD}", date(2026, 1, 5))
        assert result == "01/05"


class TestInitVault:
    def test_creates_structure(self, tmp_path):
        vault = tmp_path / "test_vault"
        cfg = Config(vault=VaultConfig(path=str(vault)))

        actions = init_vault(cfg)

        assert (vault / "templates" / "daily.md").exists()
        assert (vault / "templates" / "weekly.md").exists()
        assert (vault / "templates" / "monthly.md").exists()
        assert (vault / "templates" / "yearly.md").exists()
        assert len(actions) > 0

    def test_non_destructive(self, tmp_path):
        vault = tmp_path / "test_vault"
        cfg = Config(vault=VaultConfig(path=str(vault)))

        # First init
        init_vault(cfg)

        # Write custom content to a template
        custom = vault / "templates" / "daily.md"
        custom.write_text("MY CUSTOM TEMPLATE")

        # Second init should not overwrite
        init_vault(cfg)
        assert custom.read_text() == "MY CUSTOM TEMPLATE"


class TestCreatePlan:
    def test_creates_daily(self, tmp_path):
        vault = tmp_path / "test_vault"
        cfg = Config(vault=VaultConfig(path=str(vault)))

        result = create_plan("daily", cfg, date(2026, 3, 24))

        assert result is not None
        assert result.exists()
        content = result.read_text()
        assert "2026-03-24" in content
        assert "Tuesday" in content

    def test_skips_existing(self, tmp_path):
        vault = tmp_path / "test_vault"
        cfg = Config(vault=VaultConfig(path=str(vault)))

        # Create once
        create_plan("daily", cfg, date(2026, 3, 24))
        # Try again — should return None
        result = create_plan("daily", cfg, date(2026, 3, 24))
        assert result is None

    def test_creates_weekly(self, tmp_path):
        vault = tmp_path / "test_vault"
        cfg = Config(vault=VaultConfig(path=str(vault)))

        result = create_plan("weekly", cfg, date(2026, 3, 24))
        assert result is not None
        content = result.read_text()
        assert "Week 13" in content

    def test_creates_monthly(self, tmp_path):
        vault = tmp_path / "test_vault"
        cfg = Config(vault=VaultConfig(path=str(vault)))

        result = create_plan("monthly", cfg, date(2026, 3, 24))
        assert result is not None
        content = result.read_text()
        assert "2026-03" in content

    def test_creates_yearly(self, tmp_path):
        vault = tmp_path / "test_vault"
        cfg = Config(vault=VaultConfig(path=str(vault)))

        result = create_plan("yearly", cfg, date(2026, 3, 24))
        assert result is not None
        content = result.read_text()
        assert "2026" in content
