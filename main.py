#!/usr/bin/env python3
"""
Market Monitor — entry point.

Run:
  python main.py
  python main.py --config /path/to/other/config.yaml

The loop:
  1. Check whether the market is currently open.
  2. If closed (and run_outside_hours is false), sleep 60 s and check again.
  3. If open, fetch data for every configured symbol.
  4. Pass data through every registered signal.
  5. Dispatch any resulting alerts to all enabled notifier channels.
  6. Sleep for interval_minutes, then repeat.
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime

import pytz

from market_monitor.config import load_config
from market_monitor.fetcher import DataFetcher
from market_monitor import heartbeat, journal
from market_monitor.logger import get_logger
from market_monitor.notifier import Notifier
from market_monitor.signals import load_all_signals

log = get_logger(__name__)


# ── Market-hours helpers ───────────────────────────────────────────────

def is_market_open(config: dict) -> bool:
    """Return True if the current wall-clock time falls within market hours."""
    mh = config["market_hours"]
    tz = pytz.timezone(mh["timezone"])
    now = datetime.now(tz)

    # Skip weekends
    if now.weekday() >= 5:
        return False

    start_h, start_m = map(int, mh["start"].split(":"))
    end_h,   end_m   = map(int, mh["end"].split(":"))

    market_open  = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    market_close = now.replace(hour=end_h,   minute=end_m,   second=0, microsecond=0)

    return market_open <= now <= market_close


# ── Main loop ──────────────────────────────────────────────────────────

def run(config_path: str | None = None) -> None:
    config   = load_config(config_path) if config_path else load_config()
    fetcher  = DataFetcher(config)
    notifier = Notifier(config)
    signals  = load_all_signals(config)

    interval_secs     = config.get("interval_minutes", 5) * 60
    run_outside_hours = config["market_hours"].get("run_outside_hours", False)
    scan_count        = 0

    log.info("Market monitor started.")
    log.info("Symbols   : %s", config["symbols"])
    log.info("Signals   : %s", [s.name for s in signals])
    log.info("Interval  : %s min", config.get("interval_minutes", 5))
    log.info("After hours: %s", run_outside_hours)

    while True:
        if not run_outside_hours and not is_market_open(config):
            log.info("Market is closed. Sleeping 60 s …")
            time.sleep(60)
            continue

        log.info("─" * 60)
        log.info("Starting scan …")

        try:
            market_data = fetcher.fetch(config["symbols"])
        except Exception as exc:
            log.error("Fetch failed: %s — retrying in %s s", exc, interval_secs)
            journal.log("error", context="fetch", message=str(exc))
            time.sleep(interval_secs)
            continue

        alert_count = 0
        for symbol in config["symbols"]:
            if symbol not in market_data:
                log.warning("No data returned for %s — skipping", symbol)
                continue

            for signal in signals:
                try:
                    alerts = signal.check(market_data, symbol)
                except Exception as exc:
                    log.error("Signal %s failed on %s: %s", signal.name, symbol, exc)
                    journal.log("error", context=f"signal.{signal.name}", message=str(exc))
                    continue

                for alert in alerts:
                    notifier.dispatch(alert)
                    journal.log(
                        "alert",
                        signal   = alert.signal_name,
                        symbol   = alert.symbol,
                        severity = alert.severity,
                        message  = alert.message,
                    )
                    alert_count += 1

        scan_count += 1
        journal.log("scan", symbols_checked=len(config["symbols"]), alerts_fired=alert_count)
        heartbeat.write(scan_count)

        log.info("Scan complete. %d alert(s) fired. Next run in %s min.",
                 alert_count, config.get("interval_minutes", 5))
        time.sleep(interval_secs)


# ── CLI ────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Financial market monitor")
    parser.add_argument(
        "--config", metavar="PATH",
        help="Path to config YAML (default: config.yaml in project root)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(config_path=args.config)
