"""
RSI Oversold Signal

Fires when a symbol's Relative Strength Index (RSI) drops below a configured
threshold, signalling that the asset may be oversold and due for a bounce.

RSI measures the speed and magnitude of recent price changes on a 0–100 scale.
  < 30  — conventionally "oversold"  (configurable via threshold)
  > 70  — conventionally "overbought"

This signal uses Wilder's smoothing (the original RSI definition), implemented
via pandas EWM with alpha = 1 / period.

Behaviour
---------
- Fires exactly ONCE when RSI crosses below the threshold (enters oversold).
- Stays silent while RSI remains below the threshold.
- Resets once RSI recovers above the threshold, so the next dip can fire again.
- State is persisted to <project_root>/state/rsi_oversold.json between restarts.
- On the very first run state is recorded but no alert fires.

Config section (config.yaml):
  signals:
    rsi_oversold:
      symbols: [SPY]    # tickers to evaluate (default: [SPY])
      period: 14        # RSI lookback in trading days (default: 14)
      threshold: 30.0   # fire when RSI drops below this (default: 30.0)
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from .base import Alert, BaseSignal

# parents[0] = signals/  parents[1] = market_monitor/  parents[2] = project root
_STATE_FILE = Path(__file__).parents[2] / "state" / "rsi_oversold.json"

_DEFAULT_PERIOD    = 14
_DEFAULT_THRESHOLD = 30.0


def _compute_rsi(close: pd.Series, period: int) -> float:
    """
    Return the most recent RSI value using Wilder's smoothing.

    Wilder's method is equivalent to an EWM with alpha = 1/period and
    adjust=False, which weights recent gains/losses more heavily.
    """
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)

    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    last_gain = avg_gain.iloc[-1]
    last_loss = avg_loss.iloc[-1]

    if last_loss == 0:
        return 100.0  # No losses in the window — fully overbought
    rs = last_gain / last_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


class RsiOversoldSignal(BaseSignal):
    name = "rsi_oversold"

    def check(self, market_data: dict, symbol: str) -> list[Alert]:
        cfg            = self.config.get("signals", {}).get("rsi_oversold", {})
        watched        = cfg.get("symbols", ["SPY"])
        period         = int(cfg.get("period", _DEFAULT_PERIOD))
        threshold      = float(cfg.get("threshold", _DEFAULT_THRESHOLD))

        if symbol not in watched:
            return []

        sd = market_data.get(symbol)
        # Need enough bars to warm up Wilder's EWM (a comfortable multiple of period)
        if sd is None or len(sd.daily) < period * 3:
            return []

        # ── Compute RSI ───────────────────────────────────────────────
        rsi         = _compute_rsi(sd.daily["Close"], period)
        is_oversold = rsi < threshold

        # ── Load persisted state ──────────────────────────────────────
        state        = self._load_state()
        symbol_state = state.get(symbol, {})
        # None on first run — record state but do NOT fire
        was_oversold = symbol_state.get("is_oversold")  # bool | None

        # ── Persist current state ─────────────────────────────────────
        state[symbol] = {
            "is_oversold":   is_oversold,
            "rsi":           round(rsi, 2),
            "threshold":     threshold,
            "last_updated":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._save_state(state)

        # ── Fire only on the exact not-oversold → oversold transition ─
        if was_oversold is False and is_oversold is True:
            price = sd.current_price
            today = datetime.now().strftime("%Y-%m-%d")
            return [Alert(
                signal_name=self.name,
                symbol=symbol,
                message=(
                    f"RSI OVERSOLD on {symbol} ({today})  |  "
                    f"RSI({period})={rsi:.1f} crossed below {threshold:.0f}  |  "
                    f"Price=${price:.2f}"
                ),
                severity="warning",
                data={
                    "rsi":       round(rsi, 2),
                    "threshold": threshold,
                    "period":    period,
                    "price":     price,
                    "date":      today,
                },
            )]

        return []

    # ── State helpers ─────────────────────────────────────────────────

    def _load_state(self) -> dict:
        if _STATE_FILE.exists():
            with open(_STATE_FILE) as fh:
                return json.load(fh)
        return {}

    def _save_state(self, state: dict) -> None:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STATE_FILE, "w") as fh:
            json.dump(state, fh, indent=2)
