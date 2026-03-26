"""CLI entry point for DayWatch.

Commands:
    daywatch run       Start the tray application (default)
    daywatch init      Bootstrap templates and folder structure
    daywatch new       Create a new plan from template
    daywatch config    Open or create the config file
    daywatch status    Print today's progress (for scripts/status bars)
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import date, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import click

from daywatch import __version__
from daywatch.config import (
    DEFAULT_CONFIG_PATH,
    load_config,
    save_default_config,
)


def _get_log_dir() -> Path:
    """Return the platform-appropriate log directory."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "daywatch"
    elif sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(local) / "daywatch" / "logs"
    else:
        state = os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
        return Path(state) / "daywatch"


def _setup_logging(verbose: bool) -> None:
    """Configure logging: always to file (INFO), optionally to console."""
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler: always INFO level, 5 MB max, 3 backups
    log_dir = _get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "daywatch.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(fmt)

    # Console handler: DEBUG if verbose, WARNING otherwise
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    )

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="daywatch")
@click.option("--config", "-c", type=click.Path(), default=None, help="Path to config file.")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging.")
@click.pass_context
def main(ctx: click.Context, config: str | None, verbose: bool) -> None:
    """DayWatch — Daily Plan Notifier.

    A lightweight tray app that reads time-blocked markdown plans
    and sends native notifications when it's time to switch tasks.
    """
    _setup_logging(verbose)

    # Store config path in context
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = Path(config) if config else None

    # Default to 'run' if no subcommand given
    if ctx.invoked_subcommand is None:
        ctx.invoke(run)


@main.command()
@click.pass_context
def run(ctx: click.Context) -> None:
    """Start the DayWatch tray application."""
    config_path = ctx.obj.get("config_path")
    cfg = load_config(config_path)

    if not cfg.vault.path:
        click.echo("Error: No vault path configured.", err=True)
        click.echo(
            f"Run 'daywatch config' to set up your config at {DEFAULT_CONFIG_PATH}",
            err=True,
        )
        sys.exit(1)

    if not cfg.vault.vault_path.exists():
        click.echo(f"Error: Vault path does not exist: {cfg.vault.path}", err=True)
        sys.exit(1)

    from daywatch.tray import DayWatchTray

    app = DayWatchTray(config=cfg)
    app.run()


@main.command()
@click.option(
    "--vault",
    "-p",
    type=click.Path(),
    required=True,
    help="Path to your vault/markdown folder.",
)
@click.pass_context
def init(ctx: click.Context, vault: str) -> None:
    """Bootstrap templates and folder structure in your vault."""
    from daywatch.config import Config, VaultConfig
    from daywatch.templates import init_vault

    vault_path = Path(vault).expanduser().resolve()

    cfg = Config(vault=VaultConfig(path=str(vault_path)))
    actions = init_vault(cfg)

    click.echo(f"Initialized DayWatch in: {vault_path}\n")
    for action in actions:
        click.echo(f"  • {action}")

    # Save/update config
    config_path = ctx.obj.get("config_path") or DEFAULT_CONFIG_PATH
    save_default_config(config_path)

    # Update vault path in config
    if config_path.exists():
        content = config_path.read_text()
        content = content.replace('path = ""', f'path = "{vault_path}"')
        config_path.write_text(content)
        click.echo(f"\nConfig saved to: {config_path}")


@main.command("new")
@click.argument("plan_type", type=click.Choice(["daily", "weekly", "monthly", "yearly"]))
@click.argument("target_date", required=False, default=None)
@click.pass_context
def new_plan(ctx: click.Context, plan_type: str, target_date: str | None) -> None:
    """Create a new plan file from a template.

    PLAN_TYPE is one of: daily, weekly, monthly, yearly.
    TARGET_DATE is optional (e.g., 2026-03-25). Defaults to today.
    """
    from daywatch.templates import create_plan

    config_path = ctx.obj.get("config_path")
    cfg = load_config(config_path)

    if not cfg.vault.path:
        click.echo("Error: No vault path configured. Run 'daywatch init' first.", err=True)
        sys.exit(1)

    # Parse target date
    if target_date:
        try:
            parsed = datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError:
            click.echo(f"Error: Invalid date format '{target_date}'. Use YYYY-MM-DD.", err=True)
            sys.exit(1)
    else:
        parsed = date.today()

    result = create_plan(plan_type, cfg, parsed)

    if result:
        click.echo(f"Created: {result}")
    else:
        click.echo(f"Already exists. No file created for {plan_type} ({parsed}).")


@main.command()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Open or create the DayWatch config file."""
    config_path = ctx.obj.get("config_path") or DEFAULT_CONFIG_PATH
    path = save_default_config(config_path)
    click.echo(f"Config file: {path}")

    # Try to open in $EDITOR
    editor = os.environ.get("EDITOR", os.environ.get("VISUAL"))
    if editor:
        click.echo(f"Opening in {editor}...")
        subprocess.run([editor, str(path)])
    else:
        click.echo("Set $EDITOR to auto-open, or edit the file manually.")


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Print today's progress (for scripts, polybar, waybar, etc.)."""
    from daywatch.parser import parse_file
    from daywatch.ui.preview import format_status_line

    config_path = ctx.obj.get("config_path")
    cfg = load_config(config_path)

    if not cfg.vault.path:
        click.echo("DW: no config")
        return

    today = date.today()
    plan_path = cfg.resolve_daily_plan_path(today.year, today.month, today.day)

    if not plan_path.exists():
        click.echo("DW: no plan")
        return

    plan = parse_file(plan_path)
    click.echo(format_status_line(plan))


@main.command("test-notification")
def test_notification() -> None:
    """Send a test notification to verify system permissions.

    Use this after installation to ensure notifications are working
    and to register DayWatch in your OS notification settings.
    """
    from daywatch.scheduler import _send_notification

    click.echo("Sending test notification...")
    _send_notification(
        title="✅ DayWatch — Test Notification",
        message="Notifications are working! You can configure alerts in your system settings.",
    )
    click.echo("Done! If you didn't see a notification:")
    click.echo()
    click.echo("  macOS: System Settings → Notifications → look for 'Script Editor'")
    click.echo("         or 'Python', and set Alert style to 'Alerts' or 'Banners'.")
    click.echo("  Linux: Check that a notification daemon is running (dunst, mako, etc.).")
    click.echo("  Windows: Settings → System → Notifications → ensure they're enabled.")


if __name__ == "__main__":
    main()
