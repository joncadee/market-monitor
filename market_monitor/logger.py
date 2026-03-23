"""
Logging setup for the market monitor.

Call get_logger(__name__) in any module to get a consistently
formatted logger. All loggers share the same root handler so
output stays in one stream.
"""
import logging
import sys

_LOG_FORMAT = "[%(asctime)s] %(levelname)-8s %(name)s — %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    root = logging.getLogger("market_monitor")
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger namespaced under 'market_monitor'."""
    _configure_root()
    # Ensure the name is always under our namespace
    if not name.startswith("market_monitor"):
        name = f"market_monitor.{name}"
    return logging.getLogger(name)
