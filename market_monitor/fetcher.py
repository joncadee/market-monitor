"""
Data fetcher — wraps yfinance to produce a clean SymbolData object per ticker.

Swap this module out (or add additional fetchers) if you ever want to pull
from a different source (Polygon, Alpha Vantage, etc.) without touching
anything else.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import yfinance as yf

from .logger import get_logger

log = get_logger(__name__)


@dataclass
class SymbolData:
    symbol: str
    daily: pd.DataFrame           # Daily OHLCV — see fetch_period in config.yaml
    current_price: float = 0.0   # Latest trade price
    current_volume: int = 0      # Latest session volume
    info: dict = field(default_factory=dict)  # Raw yfinance fast_info fields


class DataFetcher:
    def __init__(self, config: dict) -> None:
        self.config = config

    def fetch(self, symbols: list[str]) -> dict[str, SymbolData]:
        """
        Fetch data for every symbol and return a dict keyed by ticker.

        Symbols that fail to fetch are skipped and logged as errors.
        """
        results: dict[str, SymbolData] = {}

        for symbol in symbols:
            try:
                results[symbol] = self._fetch_one(symbol)
            except Exception as exc:
                log.error("Failed to fetch %s: %s", symbol, exc)

        return results

    def _fetch_one(self, symbol: str) -> SymbolData:
        ticker = yf.Ticker(symbol)

        # Default 2y so signals that need a 200-day SMA have enough history.
        # Override with fetch_period in config.yaml if desired.
        period = self.config.get("fetch_period", "2y")
        daily = ticker.history(period=period, interval="1d")
        if daily.empty:
            raise ValueError(f"yfinance returned no data for {symbol}")

        fast_info = ticker.fast_info

        # fast_info attributes may not exist for all instruments, fall back
        # to the last row of the daily bars when they are absent.
        current_price = float(
            getattr(fast_info, "last_price", None) or daily["Close"].iloc[-1]
        )
        current_volume = int(
            getattr(fast_info, "last_volume", None) or daily["Volume"].iloc[-1]
        )

        log.info("  %-6s  $%8.2f   vol=%12s", symbol, current_price, f"{current_volume:,}")

        return SymbolData(
            symbol=symbol,
            daily=daily,
            current_price=current_price,
            current_volume=current_volume,
        )
