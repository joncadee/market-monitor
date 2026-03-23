"""
Golden Cross Signal

A "golden cross" occurs when the 50-day simple moving average (SMA) of a
security's closing price crosses ABOVE its 200-day SMA. It is one of the
most widely followed technical signals, historically associated with the
start of a sustained bullish trend.

Behaviour
---------
- Fires exactly ONCE per crossover event, not on every scan while the
  condition holds.  State (last known SMA relationship) is persisted to
  <project_root>/state/golden_cross.json between restarts.
- On the very first run for a symbol the state is simply recorded; the
  alert fires only on the NEXT observed transition from below → above.

Config section (config.yaml):
  signals:
    golden_cross:
      symbols: [SPY]     # list of tickers to evaluate (default: [SPY])

Alert message includes: symbol, date, current price, SMA-50, SMA-200.

NOTE: requires at least 200 bars of daily history in SymbolData.daily.
The fetcher's default of 2y provides ≈504 trading days, which is plenty.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .base import Alert, BaseSignal

# State file lives at <project_root>/state/golden_cross.json
# parents[0] = signals/  parents[1] = market_monitor/  parents[2] = project root
_STATE_FILE = Path(__file__).parents[2] / "state" / "golden_cross.json"

_SHORT_WINDOW = 50
_LONG_WINDOW  = 200


class GoldenCrossSignal(BaseSignal):
    name = "golden_cross"

    def check(self, market_data: dict, symbol: str) -> list[Alert]:
        cfg = self.config.get("signals", {}).get("golden_cross", {})
        watched_symbols = cfg.get("symbols", ["SPY"])

        if symbol not in watched_symbols:
            return []

        sd = market_data.get(symbol)
        if sd is None or len(sd.daily) < _LONG_WINDOW:
            return []

        # ── Compute SMAs ──────────────────────────────────────────────
        close    = sd.daily["Close"]
        sma50    = float(close.rolling(_SHORT_WINDOW).mean().iloc[-1])
        sma200   = float(close.rolling(_LONG_WINDOW).mean().iloc[-1])
        is_above = sma50 > sma200

        # ── Load persisted state ──────────────────────────────────────
        state        = self._load_state()
        symbol_state = state.get(symbol, {})
        # None means first run — we record state but do NOT fire
        was_above = symbol_state.get("sma50_above_sma200")  # bool | None

        # ── Persist current state ─────────────────────────────────────
        state[symbol] = {
            "sma50_above_sma200": is_above,
            "sma50":  round(sma50,  2),
            "sma200": round(sma200, 2),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._save_state(state)

        # ── Fire only on the exact below → above transition ───────────
        if was_above is False and is_above is True:
            price = sd.current_price
            today = datetime.now().strftime("%Y-%m-%d")
            return [Alert(
                signal_name=self.name,
                symbol=symbol,
                message=(
                    f"GOLDEN CROSS detected on {symbol} ({today})  |  "
                    f"Price=${price:.2f}  SMA50=${sma50:.2f}  SMA200=${sma200:.2f}  "
                    f"(SMA50 is {((sma50 - sma200) / sma200 * 100):+.2f}% above SMA200)"
                ),
                severity="info",
                data={
                    "price":  price,
                    "sma50":  sma50,
                    "sma200": sma200,
                    "date":   today,
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
