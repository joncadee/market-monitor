"""
Daily Summary

Reads today's event journal (logs/events_YYYY-MM-DD.jsonl) and sends a
formatted HTML email summarising:
  - Total scans run
  - Every signal that fired (time, signal name, symbol, message)
  - Every error encountered (time, context, message)

Called once a day at ~17:05 ET by the launchd summary job.
If no journal exists for today (market was closed, or monitor never ran)
a brief "nothing to report" email is sent instead.
"""
from __future__ import annotations

from datetime import datetime

from .config import load_config
from .journal import read_today
from .logger import get_logger
from .notifier import send_email

log = get_logger(__name__)

_SEVERITY_COLOUR = {
    "WARNING":  "#d97706",
    "CRITICAL": "#dc2626",
    "INFO":     "#3b82f6",
}


def run() -> None:
    config = load_config()
    today  = datetime.now().strftime("%Y-%m-%d")
    events = read_today()

    scans  = [e for e in events if e["type"] == "scan"]
    alerts = [e for e in events if e["type"] == "alert"]
    errors = [e for e in events if e["type"] == "error"]

    log.info(
        "Daily summary: %d scan(s), %d alert(s), %d error(s) — sending email.",
        len(scans), len(alerts), len(errors),
    )

    send_email(
        subject   = f"Market Monitor Daily Summary — {today}",
        html_body = _build_html(today, scans, alerts, errors),
        config    = config,
    )


# ── HTML builder ──────────────────────────────────────────────────────────────

def _build_html(today: str, scans: list, alerts: list, errors: list) -> str:
    total_scans  = len(scans)
    alert_count  = len(alerts)
    error_count  = len(errors)
    alert_colour = "#d97706" if alert_count > 0 else "#16a34a"
    error_colour = "#dc2626" if error_count > 0 else "#16a34a"

    alerts_section = _alerts_html(alerts)
    errors_section = _errors_html(errors)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:32px 12px;">
<table width="100%" style="max-width:640px;" cellpadding="0" cellspacing="0">

  <!-- Header -->
  <tr><td style="background:#1e3a5f;border-radius:8px 8px 0 0;padding:24px 28px;">
    <span style="color:rgba(255,255,255,.7);font-size:11px;font-weight:bold;letter-spacing:1.5px;text-transform:uppercase;">Daily Summary</span>
    <h1 style="color:#fff;font-size:22px;font-weight:bold;margin:6px 0 0;">Market Monitor</h1>
    <p style="color:rgba(255,255,255,.75);font-size:13px;margin:4px 0 0;">{today} &mdash; End-of-day report</p>
  </td></tr>

  <!-- Stats tiles -->
  <tr><td style="background:#fff;padding:24px 28px 16px;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td align="center" style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:18px 12px;">
          <div style="font-size:30px;font-weight:bold;color:#111827;">{total_scans}</div>
          <div style="font-size:12px;color:#6b7280;margin-top:4px;">Scans run</div>
        </td>
        <td width="14"></td>
        <td align="center" style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:18px 12px;">
          <div style="font-size:30px;font-weight:bold;color:{alert_colour};">{alert_count}</div>
          <div style="font-size:12px;color:#6b7280;margin-top:4px;">Alert{'s' if alert_count != 1 else ''} fired</div>
        </td>
        <td width="14"></td>
        <td align="center" style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:18px 12px;">
          <div style="font-size:30px;font-weight:bold;color:{error_colour};">{error_count}</div>
          <div style="font-size:12px;color:#6b7280;margin-top:4px;">Error{'s' if error_count != 1 else ''}</div>
        </td>
      </tr>
    </table>
  </td></tr>

  <!-- Signals fired -->
  <tr><td style="background:#fff;padding:16px 28px 8px;">
    <h2 style="margin:0 0 12px;font-size:15px;font-weight:bold;color:#111827;">Signals Fired</h2>
    {alerts_section}
  </td></tr>

  <!-- Errors -->
  <tr><td style="background:#fff;padding:16px 28px 28px;">
    <h2 style="margin:0 0 12px;font-size:15px;font-weight:bold;color:#111827;">Errors</h2>
    {errors_section}
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#f9fafb;padding:14px 28px;border-top:1px solid #e5e7eb;border-radius:0 0 8px 8px;">
    <p style="margin:0;color:#9ca3af;font-size:12px;">Market Monitor &middot; Automated daily summary &middot; {today}</p>
  </td></tr>

</table></td></tr></table>
</body></html>"""


def _alerts_html(alerts: list) -> str:
    if not alerts:
        return "<p style='margin:0;padding:12px 16px;background:#f0fdf4;border-radius:6px;color:#15803d;font-size:13px;'>No signals fired today.</p>"

    rows = ""
    for i, a in enumerate(alerts):
        bg       = "#fff" if i % 2 == 0 else "#f9fafb"
        sev      = a.get("severity", "info").upper()
        sev_col  = _SEVERITY_COLOUR.get(sev, "#6b7280")
        signal   = a.get("signal", "").replace("_", " ").title()
        symbol   = a.get("symbol", "")
        msg      = a.get("message", "")
        ts       = a.get("ts", "")
        rows += f"""
        <tr style="background:{bg};">
          <td style="padding:10px 14px;font-size:12px;color:#6b7280;border-bottom:1px solid #e5e7eb;white-space:nowrap;">{ts}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #e5e7eb;">
            <span style="font-size:11px;font-weight:bold;color:{sev_col};text-transform:uppercase;">{sev}</span><br>
            <span style="font-size:13px;color:#374151;">{signal} &mdash; {symbol}</span>
          </td>
          <td style="padding:10px 14px;font-size:12px;color:#6b7280;border-bottom:1px solid #e5e7eb;">{msg}</td>
        </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border:1px solid #e5e7eb;border-radius:6px;border-collapse:separate;border-spacing:0;">
      <tr style="background:#f9fafb;">
        <td style="padding:9px 14px;font-size:11px;font-weight:bold;letter-spacing:.8px;text-transform:uppercase;color:#6b7280;border-bottom:1px solid #e5e7eb;white-space:nowrap;width:155px;">Time</td>
        <td style="padding:9px 14px;font-size:11px;font-weight:bold;letter-spacing:.8px;text-transform:uppercase;color:#6b7280;border-bottom:1px solid #e5e7eb;width:200px;">Signal</td>
        <td style="padding:9px 14px;font-size:11px;font-weight:bold;letter-spacing:.8px;text-transform:uppercase;color:#6b7280;border-bottom:1px solid #e5e7eb;">Message</td>
      </tr>
      {rows}
    </table>"""


def _errors_html(errors: list) -> str:
    if not errors:
        return "<p style='margin:0;padding:12px 16px;background:#f0fdf4;border-radius:6px;color:#15803d;font-size:13px;'>No errors recorded today.</p>"

    rows = ""
    for i, e in enumerate(errors):
        bg  = "#fef2f2" if i % 2 == 0 else "#fff1f2"
        rows += f"""
        <tr style="background:{bg};">
          <td style="padding:9px 14px;font-size:12px;color:#991b1b;border-bottom:1px solid #fecaca;white-space:nowrap;">{e.get('ts','')}</td>
          <td style="padding:9px 14px;font-size:12px;color:#991b1b;border-bottom:1px solid #fecaca;white-space:nowrap;">{e.get('context','')}</td>
          <td style="padding:9px 14px;font-size:12px;color:#991b1b;border-bottom:1px solid #fecaca;">{e.get('message','')}</td>
        </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border:1px solid #fecaca;border-radius:6px;border-collapse:separate;border-spacing:0;">
      <tr style="background:#fee2e2;">
        <td style="padding:9px 14px;font-size:11px;font-weight:bold;letter-spacing:.8px;text-transform:uppercase;color:#991b1b;border-bottom:1px solid #fecaca;width:155px;">Time</td>
        <td style="padding:9px 14px;font-size:11px;font-weight:bold;letter-spacing:.8px;text-transform:uppercase;color:#991b1b;border-bottom:1px solid #fecaca;width:160px;">Context</td>
        <td style="padding:9px 14px;font-size:11px;font-weight:bold;letter-spacing:.8px;text-transform:uppercase;color:#991b1b;border-bottom:1px solid #fecaca;">Message</td>
      </tr>
      {rows}
    </table>"""
