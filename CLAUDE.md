# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Run the app (system tray mode)
daywatch run

# CLI commands
daywatch init --vault <path>   # Bootstrap a vault directory
daywatch new daily             # Create today's plan from template
daywatch status                # Print one-line progress summary
daywatch config                # Open config in editor

# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/
ruff format --check src/ tests/   # Check only

# Test
pytest -v                          # All tests
pytest tests/test_parser.py        # Single file
pytest tests/test_parser.py::test_name -v  # Single test
pytest --cov=src/daywatch          # With coverage
```

## Architecture

DayWatch is a macOS/Linux/Windows system tray app that parses markdown day-plans and sends timed desktop notifications.

### Core Pipeline

**File change → Parser → Scheduler → Notifications**

1. **Watcher** (`watcher.py`) — `watchdog.Observer` monitors the plan file, triggers reload on save
2. **Parser** (`parser.py`) — Regex-based markdown parser produces `DailyPlan` (dataclass) containing `TimeBlock` and `SubTask` objects. Blocks have a `BlockStatus` enum (UPCOMING/ACTIVE/COMPLETED/MISSED/FAILED)
3. **Scheduler** (`scheduler.py`) — Uses `threading.Timer` to fire two notifications per block: "coming up" (configurable lead time) and "now starting". Callback-based design
4. **Tray** (`tray.py`) — Orchestrator that ties parser + scheduler + watcher together. Generates dynamic PIL icons with a progress ring. Refreshes every 60s

### Supporting Modules

- **Config** (`config.py`) — TOML-based config at `~/.config/daywatch/config.toml`. Nested dataclasses (`VaultConfig`, `NotificationConfig`, `DisplayConfig`, `GeneralConfig`). Template variables: `{YYYY}`, `{MM}`, `{DD}`, `{WEEKDAY}`, `{WW}`
- **Templates** (`templates.py`) — Default templates in `default_templates/` (daily/weekly/monthly/yearly markdown). Users override in `vault/templates/`. Uses `importlib.resources` for bundled defaults
- **CLI** (`cli.py`) — Click-based with commands: `run`, `init`, `new`, `config`, `status`. Debug logging via `-v` flag
- **UI Preview** (`ui/preview.py`) — Text formatters for plan display: `format_block_line()`, `format_plan_summary()`, `format_status_line()`

### Plan Markdown Format

```markdown
# Day Planner
- [ ] 08:00 - 09:00 Morning routine
- [x] 09:00 - 11:00 Deep work
    - [x] subtask 1
    - [ ] subtask 2
- [ ] 12:00 - 13:00 Failed task 🔴
```

Status markers: `[x]` = completed, `[ ]` = pending, `🔴` suffix = failed.

## Code Style

- **Ruff** for linting and formatting (line length 100, target Python 3.10)
- Lint rules: E, F, I, W
- Dataclasses for domain models, no ORMs
- `threading.Timer` for async scheduling (no asyncio)

## CI

- **CI** (`ci.yml`): Lint on Ubuntu/3.12 + test matrix (3.10/3.11/3.12 × Ubuntu/macOS/Windows)
- **Release** (`release.yml`): Tag-triggered, builds PyInstaller binaries for 3 platforms
