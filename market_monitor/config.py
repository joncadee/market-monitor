"""
Config loader.

Reads config.yaml from the project root and returns it as a plain dict.
All other modules receive this dict so they stay decoupled from the file path.
"""
from __future__ import annotations

from pathlib import Path

import yaml

_DEFAULT_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config(path: Path | str = _DEFAULT_PATH) -> dict:
    """Load and minimally validate config.yaml."""
    with open(path) as fh:
        config = yaml.safe_load(fh)
    _validate(config)
    return config


def _validate(config: dict) -> None:
    required_keys = ("symbols", "market_hours", "interval_minutes")
    for key in required_keys:
        if key not in config:
            raise ValueError(f"config.yaml is missing required key: '{key}'")
    if not config["symbols"]:
        raise ValueError("'symbols' list must not be empty")
    mh = config["market_hours"]
    for key in ("timezone", "start", "end"):
        if key not in mh:
            raise ValueError(f"config.yaml market_hours is missing key: '{key}'")
