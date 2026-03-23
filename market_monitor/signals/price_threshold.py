"""
Price Threshold Signal

Fires when a symbol's current price crosses a configured upper or lower bound.

Config section (config.yaml):
  signals:
    price_threshold:
      AAPL:
        above: 250.00   # alert if price rises above this level
        below: 180.00   # alert if price falls below this level
      SPY:
        above: 560.00

Symbols not listed under price_threshold are silently skipped.
"""
from __future__ import annotations

from .base import Alert, BaseSignal


class PriceThresholdSignal(BaseSignal):
    name = "price_threshold"

    def check(self, market_data: dict, symbol: str) -> list[Alert]:
        thresholds = (
            self.config
            .get("signals", {})
            .get("price_threshold", {})
            .get(symbol)
        )
        if not thresholds:
            return []

        sd = market_data.get(symbol)
        if sd is None:
            return []

        price = sd.current_price
        alerts: list[Alert] = []

        above = thresholds.get("above")
        if above is not None and price > above:
            alerts.append(Alert(
                signal_name=self.name,
                symbol=symbol,
                message=f"{symbol} ${price:.2f} is ABOVE threshold ${above:.2f}",
                severity="warning",
                data={"price": price, "threshold": above, "direction": "above"},
            ))

        below = thresholds.get("below")
        if below is not None and price < below:
            alerts.append(Alert(
                signal_name=self.name,
                symbol=symbol,
                message=f"{symbol} ${price:.2f} is BELOW threshold ${below:.2f}",
                severity="critical",
                data={"price": price, "threshold": below, "direction": "below"},
            ))

        return alerts
