#!/usr/bin/env python3
"""
Daily summary entry point — called once at ~17:05 ET by launchd.

Reads today's event journal and sends a formatted HTML summary email
covering scans run, signals fired, and any errors encountered.
"""
import sys
from pathlib import Path

# Ensure the project root is on sys.path when run directly by launchd
sys.path.insert(0, str(Path(__file__).parents[1]))

from market_monitor.summarizer import run

if __name__ == "__main__":
    run()
