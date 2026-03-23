"""
Crash Watchdog

Runs every 5 minutes via launchd. During market hours it reads the
heartbeat file written by the main loop. If the heartbeat is stale
(older than STALE_MINUTES) it sends a "monitor is DOWN" email alert.

Design choices
--------------
- Only fires during market hours — no false alarms on weekends or evenings.
- Alert cooldown of COOLDOWN_HOURS prevents email spam if the monitor stays
  down for an extended period.
- Checks both heartbeat age AND whether the process PID is still alive, so
  it can distinguish a crash (process gone) from a hang (process stuck).
- launchd with KeepAlive=true will restart a crashed process automatically,
  but it won't tell you — this watchdog does.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytz

from .config import load_config
from .heartbeat import read as read_heartbeat
from .logger import get_logger
from .notifier import send_email

log = get_logger(__name__)

_STALE_MINUTES   = 15    # alert if heartbeat is older than this
_COOLDOWN_HOURS  = 2     # minimum hours between repeated alerts
_ALERT_STATE     = Path(__file__).parents[1] / "state" / "watchdog_alert.json"


# ── Market-hours check ────────────────────────────────────────────────────────

def _is_market_hours(config: dict) -> bool:
    mh  = config["market_hours"]
    tz  = pytz.timezone(mh["timezone"])
    now = datetime.now(tz)
    if now.weekday() >= 5:
        return False
    sh, sm = map(int, mh["start"].split(":"))
    eh, em = map(int, mh["end"].split(":"))
    open_  = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    close_ = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    return open_ <= now <= close_


# ── PID check ─────────────────────────────────────────────────────────────────

def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


# ── Alert cooldown ────────────────────────────────────────────────────────────

def _last_alert_at() -> datetime | None:
    if not _ALERT_STATE.exists():
        return None
    with open(_ALERT_STATE) as fh:
        ts = json.load(fh).get("last_alert")
    return datetime.fromisoformat(ts) if ts else None


def _record_alert() -> None:
    _ALERT_STATE.parent.mkdir(parents=True, exist_ok=True)
    with open(_ALERT_STATE, "w") as fh:
        json.dump({"last_alert": datetime.now().isoformat(timespec="seconds")}, fh)


def _clear_alert() -> None:
    if _ALERT_STATE.exists():
        _ALERT_STATE.unlink()


# ── HTML email ────────────────────────────────────────────────────────────────

def _build_alert_html(heartbeat: dict | None, stale_for: str) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if heartbeat is None:
        details_rows = """
            <tr>
              <td colspan="2" style="padding:14px;font-size:13px;color:#991b1b;">
                No heartbeat file found — the monitor may never have started,
                or the state/ directory was deleted.
              </td>
            </tr>"""
    else:
        pid      = heartbeat.get("pid", "unknown")
        alive    = _pid_alive(int(pid)) if isinstance(pid, int) else False
        pid_col  = "#16a34a" if alive else "#dc2626"
        pid_text = "Running (process is hung)" if alive else "Not running (crashed)"
        details_rows = f"""
            <tr>
              <td style="padding:9px 14px;font-size:13px;color:#6b7280;border-bottom:1px solid #fecaca;">Last heartbeat</td>
              <td style="padding:9px 14px;font-size:13px;font-weight:600;color:#111827;border-bottom:1px solid #fecaca;">{heartbeat.get('last_seen','unknown')}</td>
            </tr>
            <tr>
              <td style="padding:9px 14px;font-size:13px;color:#6b7280;border-bottom:1px solid #fecaca;">Silent for</td>
              <td style="padding:9px 14px;font-size:13px;font-weight:600;color:#dc2626;border-bottom:1px solid #fecaca;">{stale_for}</td>
            </tr>
            <tr>
              <td style="padding:9px 14px;font-size:13px;color:#6b7280;border-bottom:1px solid #fecaca;">Scans today</td>
              <td style="padding:9px 14px;font-size:13px;font-weight:600;color:#111827;border-bottom:1px solid #fecaca;">{heartbeat.get('scan_count','unknown')}</td>
            </tr>
            <tr>
              <td style="padding:9px 14px;font-size:13px;color:#6b7280;">Process (PID {pid})</td>
              <td style="padding:9px 14px;font-size:13px;font-weight:600;color:{pid_col};">{pid_text}</td>
            </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 12px;">
<table width="100%" style="max-width:560px;" cellpadding="0" cellspacing="0">

  <tr><td style="background:#dc2626;border-radius:8px 8px 0 0;padding:22px 28px;">
    <span style="color:#fff;font-size:11px;font-weight:bold;letter-spacing:1.5px;text-transform:uppercase;background:rgba(255,255,255,.22);padding:3px 10px;border-radius:12px;">CRITICAL</span>
    <h1 style="color:#fff;font-size:22px;font-weight:bold;margin:8px 0 0;">Market Monitor is DOWN</h1>
    <p style="color:rgba(255,255,255,.85);font-size:13px;margin:5px 0 0;">Detected at {now_str}</p>
  </td></tr>

  <tr><td style="background:#fff;padding:28px;">
    <p style="margin:0 0 22px;padding:13px 16px;background:#fef2f2;border-left:4px solid #dc2626;border-radius:0 5px 5px 0;color:#374151;font-size:14px;line-height:1.65;">
      The main monitoring loop has not written a heartbeat in over <strong>{stale_for}</strong>
      during market hours. launchd will restart it automatically if it crashed,
      but check the logs if this alert keeps firing.
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border:1px solid #fecaca;border-radius:6px;border-collapse:separate;border-spacing:0;background:#fef2f2;">
      <tr style="background:#fee2e2;">
        <td style="padding:9px 14px;font-size:11px;font-weight:bold;letter-spacing:.8px;text-transform:uppercase;color:#991b1b;border-bottom:1px solid #fecaca;width:44%;">Detail</td>
        <td style="padding:9px 14px;font-size:11px;font-weight:bold;letter-spacing:.8px;text-transform:uppercase;color:#991b1b;border-bottom:1px solid #fecaca;">Value</td>
      </tr>
      {details_rows}
    </table>
    <p style="margin:20px 0 0;font-size:13px;color:#6b7280;">
      Logs: <code style="background:#f3f4f6;padding:2px 6px;border-radius:4px;">~/market-monitor/logs/</code>
    </p>
  </td></tr>

  <tr><td style="background:#f9fafb;padding:14px 28px;border-top:1px solid #e5e7eb;border-radius:0 0 8px 8px;">
    <p style="margin:0;color:#9ca3af;font-size:12px;">Market Monitor Watchdog &middot; {now_str}</p>
  </td></tr>

</table></td></tr></table>
</body></html>"""


# ── Main entry ────────────────────────────────────────────────────────────────

def run() -> None:
    config = load_config()

    if not _is_market_hours(config):
        log.info("Watchdog: outside market hours — skipping check.")
        return

    heartbeat = read_heartbeat()
    now       = datetime.now()

    if heartbeat is None:
        is_stale  = True
        stale_for = "unknown (no heartbeat file)"
    else:
        last_seen = datetime.fromisoformat(heartbeat["last_seen"])
        age_mins  = (now - last_seen).total_seconds() / 60
        is_stale  = age_mins > _STALE_MINUTES
        stale_for = f"{int(age_mins)} minute{'s' if int(age_mins) != 1 else ''}"

    if not is_stale:
        log.info("Watchdog: heartbeat is fresh. Monitor is healthy.")
        _clear_alert()   # reset cooldown so next outage alerts immediately
        return

    # Within cooldown window? Don't re-alert.
    last_alerted = _last_alert_at()
    if last_alerted and (now - last_alerted) < timedelta(hours=_COOLDOWN_HOURS):
        log.warning(
            "Watchdog: monitor is stale (%s) but alert cooldown active — next alert after %s.",
            stale_for,
            (last_alerted + timedelta(hours=_COOLDOWN_HOURS)).strftime("%H:%M"),
        )
        return

    log.error("Watchdog: monitor appears DOWN (stale for %s). Sending alert.", stale_for)
    send_email(
        subject   = f"[CRITICAL] Market Monitor is DOWN — no heartbeat for {stale_for}",
        html_body = _build_alert_html(heartbeat, stale_for),
        config    = config,
    )
    _record_alert()
