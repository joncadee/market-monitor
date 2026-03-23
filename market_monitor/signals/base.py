"""
Base classes shared by all signals.

Alert  — the data object a signal returns when it fires.
BaseSignal — the abstract interface every signal must implement.

To add a new signal:
  1. Create a new .py file inside market_monitor/signals/
  2. Define a class that inherits from BaseSignal
  3. Set the `name` class attribute to something unique
  4. Implement the `check` method
  That's it — no other files need to change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from market_monitor.fetcher import SymbolData


@dataclass
class Alert:
    signal_name: str
    symbol: str
    message: str
    severity: str = "warning"          # "info" | "warning" | "critical"
    timestamp: datetime = field(default_factory=datetime.now)
    data: dict[str, Any] = field(default_factory=dict)


class BaseSignal(ABC):
    """
    Abstract base class for all market signals.

    Subclasses only need to set `name` and implement `check`.
    The registry in signals/__init__.py discovers them automatically.
    """

    #: Human-readable identifier used in logs and alerts.
    name: str = "unnamed_signal"

    def __init__(self, config: dict) -> None:
        """Receives the full config dict so each signal can read its own section."""
        self.config = config

    @abstractmethod
    def check(self, market_data: dict[str, "SymbolData"], symbol: str) -> list[Alert]:
        """
        Evaluate the signal for `symbol` and return any triggered alerts.

        Parameters
        ----------
        market_data:
            Keys are ticker symbols; values are SymbolData objects from the fetcher.
            Each SymbolData exposes:
              .current_price  — latest trade price (float)
              .current_volume — latest session volume (int)
              .daily          — pd.DataFrame of daily OHLCV for the past 30 days
        symbol:
            The specific ticker to evaluate in this call.

        Returns
        -------
        A (possibly empty) list of Alert objects.
        Return [] if the signal did not fire.
        """
        ...
