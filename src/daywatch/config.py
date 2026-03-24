"""Configuration loader for DayWatch.

Reads settings from ~/.config/daywatch/config.toml with sensible defaults.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "daywatch"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"

DEFAULT_DAILY_PATTERN = "plans/{YYYY}/{MM}/{YYYY}-{MM}-{DD}.md"
DEFAULT_WEEKLY_PATTERN = "plans/{YYYY}/{MM}/week-{WW}.md"
DEFAULT_MONTHLY_PATTERN = "plans/{YYYY}/{MM}/{YYYY}-{MM}.md"
DEFAULT_YEARLY_PATTERN = "plans/{YYYY}/{YYYY}.md"


@dataclass
class VaultConfig:
    """Vault location and plan file patterns."""

    path: str = ""
    daily_plan_pattern: str = DEFAULT_DAILY_PATTERN
    weekly_plan_pattern: str = DEFAULT_WEEKLY_PATTERN
    monthly_plan_pattern: str = DEFAULT_MONTHLY_PATTERN
    yearly_plan_pattern: str = DEFAULT_YEARLY_PATTERN

    @property
    def vault_path(self) -> Path:
        return Path(self.path).expanduser()


@dataclass
class NotificationConfig:
    """Notification preferences."""

    lead_time_minutes: int = 5
    notify_on_start: bool = True
    sound: bool = True


@dataclass
class DisplayConfig:
    """UI display preferences."""

    show_subtasks: bool = True
    show_yesterday_summary: bool = True
    theme: str = "auto"  # "light", "dark", "auto"


@dataclass
class GeneralConfig:
    """General app settings."""

    launch_at_login: bool = False


@dataclass
class Config:
    """Top-level DayWatch configuration."""

    vault: VaultConfig = field(default_factory=VaultConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    general: GeneralConfig = field(default_factory=GeneralConfig)

    def resolve_daily_plan_path(self, year: int, month: int, day: int) -> Path:
        """Resolve the path to a daily plan file for a given date."""
        pattern = self.vault.daily_plan_pattern
        resolved = (
            pattern.replace("{YYYY}", str(year))
            .replace("{MM}", f"{month:02d}")
            .replace("{DD}", f"{day:02d}")
        )
        return self.vault.vault_path / resolved

    def resolve_weekly_plan_path(self, year: int, month: int, week: int) -> Path:
        """Resolve the path to a weekly plan file."""
        pattern = self.vault.weekly_plan_pattern
        resolved = (
            pattern.replace("{YYYY}", str(year))
            .replace("{MM}", f"{month:02d}")
            .replace("{WW}", f"{week:02d}")
        )
        return self.vault.vault_path / resolved

    def resolve_monthly_plan_path(self, year: int, month: int) -> Path:
        """Resolve the path to a monthly plan file."""
        pattern = self.vault.monthly_plan_pattern
        resolved = pattern.replace("{YYYY}", str(year)).replace("{MM}", f"{month:02d}")
        return self.vault.vault_path / resolved

    def resolve_yearly_plan_path(self, year: int) -> Path:
        """Resolve the path to a yearly plan file."""
        pattern = self.vault.yearly_plan_pattern
        resolved = pattern.replace("{YYYY}", str(year))
        return self.vault.vault_path / resolved


def load_config(path: Path | None = None) -> Config:
    """Load configuration from a TOML file.

    Args:
        path: Path to the config file. Uses default if None.

    Returns:
        A Config object with loaded or default values.
    """
    if path is None:
        path = DEFAULT_CONFIG_PATH

    config = Config()

    if not path.exists():
        return config

    with open(path, "rb") as f:
        data = tomllib.load(f)

    # Vault settings
    if "vault" in data:
        v = data["vault"]
        config.vault = VaultConfig(
            path=v.get("path", config.vault.path),
            daily_plan_pattern=v.get("daily_plan_pattern", config.vault.daily_plan_pattern),
            weekly_plan_pattern=v.get("weekly_plan_pattern", config.vault.weekly_plan_pattern),
            monthly_plan_pattern=v.get("monthly_plan_pattern", config.vault.monthly_plan_pattern),
            yearly_plan_pattern=v.get("yearly_plan_pattern", config.vault.yearly_plan_pattern),
        )

    # Notification settings
    if "notifications" in data:
        n = data["notifications"]
        config.notifications = NotificationConfig(
            lead_time_minutes=n.get("lead_time_minutes", config.notifications.lead_time_minutes),
            notify_on_start=n.get("notify_on_start", config.notifications.notify_on_start),
            sound=n.get("sound", config.notifications.sound),
        )

    # Display settings
    if "display" in data:
        d = data["display"]
        config.display = DisplayConfig(
            show_subtasks=d.get("show_subtasks", config.display.show_subtasks),
            show_yesterday_summary=d.get(
                "show_yesterday_summary", config.display.show_yesterday_summary
            ),
            theme=d.get("theme", config.display.theme),
        )

    # General settings
    if "general" in data:
        g = data["general"]
        config.general = GeneralConfig(
            launch_at_login=g.get("launch_at_login", config.general.launch_at_login),
        )

    return config


def save_default_config(path: Path | None = None) -> Path:
    """Write a default config file if one doesn't exist.

    Returns:
        The path to the config file.
    """
    if path is None:
        path = DEFAULT_CONFIG_PATH

    if path.exists():
        return path

    path.parent.mkdir(parents=True, exist_ok=True)

    default_toml = """\
[vault]
# Path to your Obsidian vault or markdown folder
path = ""
# Supports {YYYY}, {MM}, {DD}, {WW} placeholders
daily_plan_pattern = "plans/{YYYY}/{MM}/{YYYY}-{MM}-{DD}.md"
weekly_plan_pattern = "plans/{YYYY}/{MM}/week-{WW}.md"
monthly_plan_pattern = "plans/{YYYY}/{MM}/{YYYY}-{MM}.md"
yearly_plan_pattern = "plans/{YYYY}/{YYYY}.md"

[notifications]
lead_time_minutes = 5
notify_on_start = true
sound = true

[display]
show_subtasks = true
show_yesterday_summary = true
theme = "auto"  # "light", "dark", "auto"

[general]
launch_at_login = false
"""
    path.write_text(default_toml, encoding="utf-8")
    return path
