"""
Notifier — dispatches Alert objects to configured output channels.

Active channels:
  - Console  (coloured log lines to stdout)
  - Email    (Gmail SMTP via TLS — credentials loaded from .env)

Stub:
  - Slack    (incoming webhook — see _slack docstring)

Credentials are never stored in config.yaml. They are read at send-time
from environment variables, which python-dotenv loads from a .env file:

  GMAIL_ADDRESS       your sending Gmail address
  GMAIL_APP_PASSWORD  16-character App Password (not your login password)

Email sending failures are caught, logged, and swallowed so they never
crash the main loop.
"""
from __future__ import annotations

import json
import os
import smtplib
import textwrap
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

from .logger import get_logger
from .signals.base import Alert

# Load .env once at import time so os.getenv() sees the values everywhere
load_dotenv()

log = get_logger(__name__)

# ── Email throttle state ──────────────────────────────────────────────────────
_THROTTLE_STATE = Path(__file__).parents[1] / "state" / "email_throttle.json"


def _load_throttle() -> dict[str, str]:
    if not _THROTTLE_STATE.exists():
        return {}
    with open(_THROTTLE_STATE) as fh:
        return json.load(fh)


def _save_throttle(state: dict[str, str]) -> None:
    _THROTTLE_STATE.parent.mkdir(parents=True, exist_ok=True)
    with open(_THROTTLE_STATE, "w") as fh:
        json.dump(state, fh, indent=2)


def _already_sent_today(signal_name: str, symbol: str) -> bool:
    """Return True if an email was already sent today for this signal+symbol."""
    key   = f"{signal_name}|{symbol}"
    today = date.today().isoformat()
    return _load_throttle().get(key) == today


def _record_sent_today(signal_name: str, symbol: str) -> None:
    key   = f"{signal_name}|{symbol}"
    today = date.today().isoformat()
    state = _load_throttle()
    state[key] = today
    _save_throttle(state)


# ── Console colour codes ──────────────────────────────────────────────────────
_COLOUR = {
    "info":     ("\033[94m", "\033[0m"),   # bright blue
    "warning":  ("\033[93m", "\033[0m"),   # bright yellow
    "critical": ("\033[91m", "\033[0m"),   # bright red
}

# ── Email severity → header colour (hex) ─────────────────────────────────────
_SEVERITY_HEX = {
    "info":     "#3b82f6",   # blue
    "warning":  "#d97706",   # amber
    "critical": "#dc2626",   # red
}

# ── Human-readable field labels for the email detail table ───────────────────
_FIELD_LABELS: dict[str, str] = {
    "rsi":                "RSI",
    "sma50":              "SMA-50",
    "sma200":             "SMA-200",
    "price":              "Current Price",
    "threshold":          "Signal Threshold",
    "period":             "RSI Period (days)",
    "direction":          "Direction",
    "current_volume":     "Current Volume",
    "avg_volume":         "20-Day Avg Volume",
    "ratio":              "Volume Ratio",
    "multiplier_threshold": "Alert Threshold (×)",
    "date":               "Signal Date",
}


# ── Notifier ──────────────────────────────────────────────────────────────────

class Notifier:
    def __init__(self, config: dict) -> None:
        self._cfg         = config.get("notifier", {})
        self._full_config = config   # needed so _email can call send_email()

    def dispatch(self, alert: Alert) -> None:
        """Send `alert` to every enabled channel."""
        if self._cfg.get("console", {}).get("enabled", True):
            self._console(alert)
        if self._cfg.get("email", {}).get("enabled", False):
            self._email(alert)
        if self._cfg.get("slack", {}).get("enabled", False):
            self._slack(alert)

    # ── Console ───────────────────────────────────────────────────────────────

    def _console(self, alert: Alert) -> None:
        start, end = _COLOUR.get(alert.severity, ("", ""))
        ts   = alert.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        line = (
            f"{start}"
            f"[ALERT] {ts}  severity={alert.severity.upper():<8}  "
            f"signal={alert.signal_name:<20}  symbol={alert.symbol:<6}  "
            f"{alert.message}"
            f"{end}"
        )
        log.warning(line)

    # ── Email ─────────────────────────────────────────────────────────────────

    def _email(self, alert: Alert) -> None:
        if _already_sent_today(alert.signal_name, alert.symbol):
            log.info(
                "Email throttled: already sent today for signal=%s symbol=%s",
                alert.signal_name, alert.symbol,
            )
            return
        send_email(
            subject   = subject_text(alert),
            html_body = _build_html(alert),
            config    = self._full_config,
        )
        _record_sent_today(alert.signal_name, alert.symbol)

    # ── Slack stub ────────────────────────────────────────────────────────────

    def _slack(self, alert: Alert) -> None:
        """
        Post an alert to Slack via an incoming webhook.

        TODO: implement with the `requests` library:
          import requests
          payload = {
              "text": f"*[{alert.severity.upper()}]* {alert.message}",
              "channel": self._cfg["slack"]["channel"],
          }
          requests.post(self._cfg["slack"]["webhook_url"], json=payload, timeout=10)

        Required config.yaml keys under notifier.slack:
          webhook_url, channel
        """
        log.debug("[slack stub] Would send: %s", alert.message)


# ── Standalone email sender ───────────────────────────────────────────────────
# Importable by summarizer.py, watchdog.py, or any future module that needs
# to send an email without going through the Notifier class.

def send_email(subject: str, html_body: str, config: dict) -> None:
    """
    Send an HTML email via Gmail SMTP.

    Credentials: GMAIL_ADDRESS + GMAIL_APP_PASSWORD from .env.
    Recipients:  notifier.email.to_addrs from config.yaml.
    All failures are caught and logged — this function never raises.
    """
    gmail_addr   = os.getenv("GMAIL_ADDRESS", "").strip()
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()

    if not gmail_addr or not app_password:
        log.error("Email not sent: GMAIL_ADDRESS or GMAIL_APP_PASSWORD missing from .env")
        return

    email_cfg = config.get("notifier", {}).get("email", {})
    to_addrs  = email_cfg.get("to_addrs", [])
    if not to_addrs:
        log.error("Email not sent: notifier.email.to_addrs is empty in config.yaml")
        return

    smtp_host = email_cfg.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(email_cfg.get("smtp_port", 587))

    msg            = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = gmail_addr
    msg["To"]      = ", ".join(to_addrs)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(gmail_addr, app_password)
            smtp.sendmail(gmail_addr, to_addrs, msg.as_string())
        log.info("Email sent to %s  subject=%r", to_addrs, subject)
    except smtplib.SMTPAuthenticationError:
        log.error(
            "Email failed: authentication error — check GMAIL_ADDRESS and "
            "GMAIL_APP_PASSWORD in .env (must be an App Password, not your login password)"
        )
    except smtplib.SMTPException as exc:
        log.error("Email failed (SMTP error): %s", exc)
    except OSError as exc:
        log.error("Email failed (network error): %s", exc)


# ── HTML email builder ────────────────────────────────────────────────────────

def _build_html(alert: Alert) -> str:
    """Render a fully self-contained HTML email for the given alert."""
    colour    = _SEVERITY_HEX.get(alert.severity, "#6b7280")
    ts        = alert.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    sig_title = alert.signal_name.replace("_", " ").title()
    yf_url    = f"https://finance.yahoo.com/quote/{alert.symbol}"

    data_rows_html = _build_data_rows(alert.data)

    return textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>{subject_text(alert)}</title>
        </head>
        <body style="margin:0; padding:0; background-color:#f3f4f6;
                     font-family:Arial, Helvetica, sans-serif; -webkit-text-size-adjust:100%;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td align="center" style="padding:32px 12px;">

                <table role="presentation" width="100%" style="max-width:580px;"
                       cellpadding="0" cellspacing="0" border="0">

                  <!-- ── Header ── -->
                  <tr>
                    <td style="background-color:{colour}; border-radius:8px 8px 0 0;
                                padding:24px 28px;">
                      <span style="display:inline-block;
                                   background:rgba(255,255,255,0.22);
                                   color:#ffffff; font-size:11px; font-weight:bold;
                                   letter-spacing:1.5px; text-transform:uppercase;
                                   padding:3px 10px; border-radius:12px;">
                        {alert.severity}
                      </span>
                      <h1 style="color:#ffffff; font-size:22px; font-weight:bold;
                                 margin:8px 0 0; line-height:1.3;">
                        {sig_title} &mdash; {alert.symbol}
                      </h1>
                      <p style="color:rgba(255,255,255,0.85); font-size:13px;
                                margin:5px 0 0;">
                        {ts}
                      </p>
                    </td>
                  </tr>

                  <!-- ── Body ── -->
                  <tr>
                    <td style="background:#ffffff; padding:28px;">

                      <!-- Message callout -->
                      <p style="margin:0 0 24px; padding:13px 16px;
                                background:#f9fafb; border-left:4px solid {colour};
                                border-radius:0 5px 5px 0;
                                color:#374151; font-size:14px; line-height:1.65;">
                        {alert.message}
                      </p>

                      <!-- Detail table -->
                      <table role="presentation" width="100%" cellpadding="0"
                             cellspacing="0" border="0"
                             style="border:1px solid #e5e7eb; border-radius:6px;
                                    border-collapse:separate; border-spacing:0;">
                        <tr style="background:#f9fafb;">
                          <td style="padding:9px 14px; font-size:11px; font-weight:bold;
                                     letter-spacing:0.8px; text-transform:uppercase;
                                     color:#6b7280; border-bottom:1px solid #e5e7eb;
                                     width:42%; border-radius:6px 0 0 0;">
                            Field
                          </td>
                          <td style="padding:9px 14px; font-size:11px; font-weight:bold;
                                     letter-spacing:0.8px; text-transform:uppercase;
                                     color:#6b7280; border-bottom:1px solid #e5e7eb;
                                     border-radius:0 6px 0 0;">
                            Value
                          </td>
                        </tr>
                        {data_rows_html}
                      </table>

                      <!-- Yahoo Finance button -->
                      <table role="presentation" width="100%" cellpadding="0"
                             cellspacing="0" border="0" style="margin-top:24px;">
                        <tr>
                          <td align="center">
                            <a href="{yf_url}"
                               style="display:inline-block; background-color:{colour};
                                      color:#ffffff; font-size:14px; font-weight:bold;
                                      text-decoration:none; padding:12px 30px;
                                      border-radius:6px; letter-spacing:0.3px;">
                              View {alert.symbol} on Yahoo Finance &rarr;
                            </a>
                          </td>
                        </tr>
                      </table>

                    </td>
                  </tr>

                  <!-- ── Footer ── -->
                  <tr>
                    <td style="background:#f9fafb; padding:14px 28px;
                                border-top:1px solid #e5e7eb;
                                border-radius:0 0 8px 8px;">
                      <p style="margin:0; color:#9ca3af; font-size:12px;">
                        Market Monitor &middot; Automated alert &middot; {ts}
                      </p>
                    </td>
                  </tr>

                </table>
              </td>
            </tr>
          </table>
        </body>
        </html>
    """)


def subject_text(alert: Alert) -> str:
    return (
        f"[{alert.severity.upper()}] "
        f"{alert.signal_name.replace('_', ' ').title()} fired on {alert.symbol}"
    )


def _build_data_rows(data: dict) -> str:
    """Convert the alert's data dict into alternating HTML table rows."""
    if not data:
        return ""

    rows: list[str] = []
    for i, (key, value) in enumerate(data.items()):
        label     = _FIELD_LABELS.get(key, key.replace("_", " ").title())
        formatted = _format_value(key, value)
        bg        = "#ffffff" if i % 2 == 0 else "#f9fafb"
        border    = "border-bottom:1px solid #e5e7eb;" if i < len(data) - 1 else ""
        rows.append(
            f'<tr style="background:{bg};">'
            f'<td style="padding:9px 14px; font-size:13px; color:#6b7280;'
            f'           font-weight:500; {border}">{label}</td>'
            f'<td style="padding:9px 14px; font-size:13px; color:#111827;'
            f'           font-weight:600; {border}">{formatted}</td>'
            f"</tr>"
        )
    return "\n                        ".join(rows)


def _format_value(key: str, value: object) -> str:
    """Format a data dict value for human-readable display in the email."""
    if value is None:
        return "—"

    key_lower = key.lower()

    if isinstance(value, float):
        # Dollar amounts — only fields that are unambiguously prices
        if any(key_lower == k or key_lower.endswith(f"_{k}")
               for k in ("price", "sma50", "sma200")):
            return f"${value:,.2f}"
        # Ratios / multipliers
        if "ratio" in key_lower or "multiplier" in key_lower:
            return f"{value:.2f}&times;"
        # RSI
        if key_lower == "rsi":
            return f"{value:.1f} / 100"
        # Generic float
        return f"{value:.2f}"

    if isinstance(value, int):
        return f"{value:,}"

    return str(value)
