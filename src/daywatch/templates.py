"""Template engine for DayWatch.

Handles `daywatch init` (bootstrapping) and `daywatch new` (creating plan files
from templates). Ships with built-in default templates that users can override
by placing custom versions in their vault's templates/ folder.
"""

from __future__ import annotations

import importlib.resources
from datetime import date
from pathlib import Path

from daywatch.config import Config

# Mapping of template names to their default filenames
TEMPLATE_NAMES = ("yearly", "monthly", "weekly", "daily")

# Template variable placeholders
VARIABLES = {
    "{YYYY}": lambda d: str(d.year),
    "{MM}": lambda d: f"{d.month:02d}",
    "{DD}": lambda d: f"{d.day:02d}",
    "{WEEKDAY}": lambda d: d.strftime("%A"),
    "{WW}": lambda d: f"{d.isocalendar()[1]:02d}",
}


def _resolve_variables(content: str, target_date: date) -> str:
    """Replace template variables with actual values."""
    result = content
    for placeholder, resolver in VARIABLES.items():
        result = result.replace(placeholder, resolver(target_date))
    return result


def _get_default_template(name: str) -> str:
    """Load a built-in default template by name."""
    templates_pkg = importlib.resources.files("daywatch") / "default_templates"
    template_file = templates_pkg / f"{name}.md"
    return template_file.read_text(encoding="utf-8")


def get_template(name: str, vault_path: Path | None = None) -> str:
    """Get a template, preferring user overrides over defaults.

    Args:
        name: Template name (yearly, monthly, weekly, daily).
        vault_path: Path to the vault. If provided, checks for user templates first.

    Returns:
        The template content as a string.
    """
    if name not in TEMPLATE_NAMES:
        raise ValueError(f"Unknown template: {name}. Must be one of {TEMPLATE_NAMES}")

    # Check for user override
    if vault_path:
        user_template = vault_path / "templates" / f"{name}.md"
        if user_template.exists():
            return user_template.read_text(encoding="utf-8")

    return _get_default_template(name)


def init_vault(config: Config) -> list[str]:
    """Bootstrap a vault with templates and folder structure.

    Creates:
    - templates/ folder with default templates (won't overwrite existing)
    - plans/ folder structure for the current year/month
    - Today's daily plan if it doesn't exist

    Args:
        config: The DayWatch configuration.

    Returns:
        List of actions taken (for user feedback).
    """
    vault_path = config.vault.vault_path
    actions: list[str] = []

    if not vault_path.exists():
        vault_path.mkdir(parents=True, exist_ok=True)
        actions.append(f"Created vault directory: {vault_path}")

    # Create templates folder with defaults
    templates_dir = vault_path / "templates"
    templates_dir.mkdir(exist_ok=True)

    for name in TEMPLATE_NAMES:
        template_path = templates_dir / f"{name}.md"
        if not template_path.exists():
            content = _get_default_template(name)
            template_path.write_text(content, encoding="utf-8")
            actions.append(f"Created template: templates/{name}.md")
        else:
            actions.append(f"Skipped (exists): templates/{name}.md")

    # Create folder structure for current year/month
    today = date.today()
    plans_dir = vault_path / "plans" / str(today.year) / f"{today.month:02d}"
    plans_dir.mkdir(parents=True, exist_ok=True)
    actions.append(f"Created plans directory: plans/{today.year}/{today.month:02d}/")

    # Create today's daily plan if missing
    daily_path = config.resolve_daily_plan_path(today.year, today.month, today.day)
    if not daily_path.exists():
        result = create_plan("daily", config, today)
        if result:
            actions.append(f"Created today's plan: {daily_path.name}")
    else:
        actions.append(f"Skipped (exists): {daily_path.name}")

    return actions


def create_plan(
    plan_type: str,
    config: Config,
    target_date: date | None = None,
) -> Path | None:
    """Create a new plan file from a template.

    Args:
        plan_type: One of "yearly", "monthly", "weekly", "daily".
        config: The DayWatch configuration.
        target_date: The date to create the plan for. Defaults to today.

    Returns:
        Path to the created file, or None if it already exists.
    """
    if target_date is None:
        target_date = date.today()

    vault_path = config.vault.vault_path

    # Determine output path
    if plan_type == "daily":
        output_path = config.resolve_daily_plan_path(
            target_date.year, target_date.month, target_date.day
        )
    elif plan_type == "weekly":
        week_num = target_date.isocalendar()[1]
        output_path = config.resolve_weekly_plan_path(target_date.year, target_date.month, week_num)
    elif plan_type == "monthly":
        output_path = config.resolve_monthly_plan_path(target_date.year, target_date.month)
    elif plan_type == "yearly":
        output_path = config.resolve_yearly_plan_path(target_date.year)
    else:
        raise ValueError(f"Unknown plan type: {plan_type}")

    if output_path.exists():
        return None

    # Get template and resolve variables
    template = get_template(plan_type, vault_path)
    content = _resolve_variables(template, target_date)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

    return output_path
