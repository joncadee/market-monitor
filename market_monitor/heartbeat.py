"""
Heartbeat — written by the main loop after every successful scan.

The watchdog reads this file every 5 minutes to confirm the monitor is
still alive. If the file is stale (not updated within `stale_minutes`
during market hours) the watchdog sends an email alert.

State file: state/heartbeat.json
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

_HEARTBEAT_FILE = Path(__file__).parents[1] / "state" / "heartbeat.json"


def write(scan_count: int) -> None:
    """Stamp the heartbeat file with the current time and PID."""
    _HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_HEARTBEAT_FILE, "w") as fh:
        json.dump(
            {
                "last_seen":  datetime.now().isoformat(timespec="seconds"),
                "pid":        os.getpid(),
                "scan_count": scan_count,
            },
            fh,
            indent=2,
        )


def read() -> dict | None:
    """Return the heartbeat dict, or None if the file doesn't exist."""
    if not _HEARTBEAT_FILE.exists():
        return None
    with open(_HEARTBEAT_FILE) as fh:
        return json.load(fh)
