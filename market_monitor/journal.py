"""
Event journal — structured JSON Lines log written by the main loop.

Each scan, alert, and error is appended as a single JSON object to
  logs/events_YYYY-MM-DD.jsonl

The daily summarizer reads this file at market close. Using a separate
structured file (rather than parsing the human-readable log) makes the
summarizer robust to log format changes.

All writes are silent-on-failure so a disk error never crashes the loop.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

_LOG_DIR = Path(__file__).parents[1] / "logs"


def _today_path() -> Path:
    return _LOG_DIR / f"events_{datetime.now().strftime('%Y-%m-%d')}.jsonl"


def log(event_type: str, **kwargs: Any) -> None:
    """Append one structured event to today's journal. Never raises."""
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts":   datetime.now().isoformat(timespec="seconds"),
            "type": event_type,
            **kwargs,
        }
        with open(_today_path(), "a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def read_today() -> list[dict]:
    """Return all events from today's journal. Returns [] if not yet created."""
    path = _today_path()
    if not path.exists():
        return []
    events: list[dict] = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events
