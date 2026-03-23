"""
Signal registry — auto-discovers every BaseSignal subclass in this package.

How it works
------------
When load_all_signals() is called, it iterates over every .py file in this
directory (except base.py), imports each one, and finds every class that
inherits from BaseSignal. It then instantiates each one with the config dict.

Adding a new signal requires NO changes to this file or any other file:
  1. Create market_monitor/signals/my_new_signal.py
  2. Define a class that subclasses BaseSignal
  3. Restart the monitor — it appears automatically.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path

from .base import Alert, BaseSignal


def load_all_signals(config: dict) -> list[BaseSignal]:
    """
    Import every module in this package (except `base`) and return one
    instantiated instance of each BaseSignal subclass discovered.
    """
    instances: list[BaseSignal] = []
    package_dir = Path(__file__).parent

    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name == "base":
            continue

        module = importlib.import_module(f".{module_info.name}", package=__package__)

        for _, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, BaseSignal) and cls is not BaseSignal:
                instances.append(cls(config))

    return instances


__all__ = ["Alert", "BaseSignal", "load_all_signals"]
