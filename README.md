# DayWatch

A lightweight, cross-platform desktop tray app that reads time-blocked markdown plans and sends native notifications when it's time to switch tasks.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## What it does

DayWatch lives in your system tray and watches your daily plan files (plain markdown). When a time block is about to start, it sends a native desktop notification. Click the tray icon to see your day at a glance with live progress.

```
┌──────────────────────────────────┐
│  Tuesday, 24 Mar 2026       75%  │
│  ━━━━━━━━━━━━━━━━━━━━━░░░░░░░░   │
│                                  │
│  ✅  8:30–9:00   Planning        │
│  ✅  9:00–11:00  Deep work       │
│  ▶  11:00–11:45  Gym       ← now │
│  ○  11:45–12:30  Swedish         │
│  ○  12:30–13:00  Lunch           │
│  ○  13:00–15:30  Uni             │
└──────────────────────────────────┘
```

## Features

- **Native notifications** — get reminded before each time block starts (configurable lead time)
- **System tray icon** — shows progress ring and current block status
- **Live reload** — edits to your plan file are picked up instantly
- **Template system** — ships with yearly/monthly/weekly/daily templates, `daywatch init` bootstraps your vault
- **Cross-platform** — works on macOS, Linux, and Windows
- **Zero lock-in** — your plans are plain markdown. Works with Obsidian, any editor, or no editor at all
- **Status bar integration** — `daywatch status` outputs a one-liner for polybar, waybar, i3status, etc.

## Installation

### From GitHub Releases (no Python needed)

Download the latest binary for your platform from [Releases](https://github.com/DiyazY/daywatch/releases).

**macOS:**
```bash
chmod +x daywatch-macos-arm64
xattr -d com.apple.quarantine daywatch-macos-arm64
mv daywatch-macos-arm64 /usr/local/bin/daywatch
```

**Linux:**
```bash
chmod +x daywatch-linux-amd64
mv daywatch-linux-amd64 /usr/local/bin/daywatch
```

**Windows:** Move `daywatch-windows-amd64.exe` to a folder on your `PATH`, or just run it directly.

### From PyPI

```bash
pip install daywatch
```

### From source

```bash
git clone https://github.com/DiyazY/daywatch.git
cd daywatch
pip install -e .
```

## Quick Start

### 1. Bootstrap your vault

```bash
daywatch init --vault ~/my-notes
```

This creates a `templates/` folder with default templates and a `plans/` folder structure. It also generates today's daily plan if it doesn't exist.

### 2. Configure

```bash
daywatch config
```

Opens `~/.config/daywatch/config.toml` in your editor. Set your vault path:

```toml
[vault]
path = "/Users/you/my-notes"
```

### 3. Edit your daily plan

Open today's plan file and add your time blocks:

```markdown
## Day Planner
- [ ] 08:00 - 08:30 planning
- [ ] 08:30 - 11:00 deep work
    - [ ] write tests
    - [ ] review PR
- [ ] 11:00 - 11:45 gym
- [ ] 12:00 - 13:00 lunch
- [ ] 13:00 - 17:00 project work
```

### 4. Run DayWatch

```bash
daywatch run
```

The tray icon appears. Notifications will fire automatically.

## CLI Commands

```
daywatch run              # Start the tray app (default)
daywatch init --vault .   # Bootstrap templates + folder structure
daywatch new daily        # Create today's plan from template
daywatch new weekly       # Create this week's plan
daywatch new monthly      # Current month
daywatch new yearly       # Current year
daywatch config           # Open config file in $EDITOR
daywatch status           # One-line progress (for scripts/status bars)
```

## Plan Format

DayWatch parses time blocks in this format:

```
- [ ] HH:MM - HH:MM label
- [x] HH:MM - HH:MM label    (completed)
```

Subtasks are indented under a block:

```
- [ ] 09:00 - 11:00 project work
    - [ ] subtask one
    - [x] subtask two (done)
```

Status markers:
- `[x]` — completed (✅)
- `🔴` on a line — marks a task as failed
- Unchecked past blocks — shown as missed (⚠) in the UI

## Template System

DayWatch ships with templates for yearly, monthly, weekly, and daily plans. Run `daywatch init` to copy them into your vault, then customize as needed.

Templates support these variables:

| Variable    | Example   | Description         |
|-------------|-----------|---------------------|
| `{YYYY}`    | 2026      | Four-digit year     |
| `{MM}`      | 03        | Zero-padded month   |
| `{DD}`      | 24        | Zero-padded day     |
| `{WEEKDAY}` | Tuesday   | Full weekday name   |
| `{WW}`      | 13        | ISO week number     |

## Configuration

Config file: `~/.config/daywatch/config.toml`

```toml
[vault]
path = "/path/to/vault"
daily_plan_pattern = "plans/{YYYY}/{MM}/{YYYY}-{MM}-{DD}.md"

[notifications]
lead_time_minutes = 5
notify_on_start = true
sound = true

[display]
show_subtasks = true
show_yesterday_summary = true
theme = "auto"

[general]
launch_at_login = false
```

## Development

```bash
git clone https://github.com/DiyazY/daywatch.git
cd daywatch
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).
