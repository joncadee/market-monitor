#!/usr/bin/env python3
"""
Watchdog entry point — called every 5 minutes by launchd.

Checks whether the main monitor loop is still alive during market hours
and sends an email alert if the heartbeat is stale.
"""
import sys
from pathlib import Path

# Ensure the project root is on sys.path when run directly by launchd
sys.path.insert(0, str(Path(__file__).parents[1]))

from market_monitor.watchdog import run

if __name__ == "__main__":
    run()
