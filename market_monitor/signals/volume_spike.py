"""
Volume Spike Signal

Fires when today's volume exceeds N times the trailing 20-session average.
A volume spike often precedes or accompanies a large price move.

Config section (config.yaml):
  signals:
    volume_spike:
      multiplier: 2.5   # alert if volume > 2.5× the 20-day average

The multiplier defaults to 2.0 if not specified.
"""
from __future__ import annotations

from .base import Alert, BaseSignal


class VolumeSpikeSignal(BaseSignal):
    name = "volume_spike"

    def check(self, market_data: dict, symbol: str) -> list[Alert]:
        cfg = self.config.get("signals", {}).get("volume_spike", {})
        multiplier = float(cfg.get("multiplier", 2.0))

        sd = market_data.get(symbol)
        if sd is None or sd.daily.empty:
            return []

        # Exclude the current (incomplete) session from the baseline
        history = sd.daily["Volume"].iloc[:-1]
        if len(history) < 5:
            return []  # Not enough history to establish a reliable baseline

        avg_volume = history.tail(20).mean()
        current_vol = sd.current_volume

        if avg_volume > 0 and current_vol > multiplier * avg_volume:
            ratio = current_vol / avg_volume
            return [Alert(
                signal_name=self.name,
                symbol=symbol,
                message=(
                    f"{symbol} volume spike: {current_vol:,} "
                    f"= {ratio:.1f}× the 20-day avg ({int(avg_volume):,})"
                ),
                severity="warning",
                data={
                    "current_volume": current_vol,
                    "avg_volume": round(avg_volume),
                    "ratio": round(ratio, 2),
                    "multiplier_threshold": multiplier,
                },
            )]

        return []
