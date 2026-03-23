#!/usr/bin/env python3
"""
Backtest: Golden Cross on SPY — last 3 years
─────────────────────────────────────────────
Identifies every golden cross event (50-day SMA crossing above 200-day SMA)
in the past 3 years and shows how SPY performed in the 1, 3, 6, and 12
months following each signal.

To compute valid SMAs at the start of the 3-year window the script fetches
5 years of history but only reports crossovers from the last 3 years.

Usage:
    cd market-monitor
    python scripts/backtest_golden_cross.py
"""
from __future__ import annotations

import sys
import warnings
from datetime import date, timedelta

# Suppress library noise that isn't actionable for end users
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")

import pandas as pd
import yfinance as yf

# ── Parameters ──────────────────────────────────────────────────────────────

SYMBOL        = "SPY"
SHORT_WINDOW  = 50
LONG_WINDOW   = 200
BACKTEST_YEARS = 3   # how far back to report crossovers
FETCH_YEARS    = 5   # must be > BACKTEST_YEARS + LONG_WINDOW/252 to warm up SMAs

FORWARD_PERIODS = [
    ("+1M",  21),
    ("+3M",  63),
    ("+6M",  126),
    ("+12M", 252),
]

# ── Data ─────────────────────────────────────────────────────────────────────

def fetch_data(symbol: str, years: int) -> pd.DataFrame:
    print(f"  Downloading {years}y of {symbol} daily data from Yahoo Finance …", flush=True)
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=f"{years}y", interval="1d")

    # Strip timezone so comparisons with plain Timestamps work cleanly
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)

    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.sort_index(inplace=True)
    return df


# ── Signal computation ────────────────────────────────────────────────────────

def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["SMA50"]  = df["Close"].rolling(SHORT_WINDOW).mean()
    df["SMA200"] = df["Close"].rolling(LONG_WINDOW).mean()

    # True when SMA50 > SMA200
    above = df["SMA50"] > df["SMA200"]
    # Golden cross: above today AND not above yesterday (first day the cross holds)
    df["golden_cross"] = above & ~above.shift(1).fillna(False)
    # Death cross: the inverse, shown in the summary for context
    df["death_cross"]  = ~above & above.shift(1).fillna(True)

    return df


# ── Forward returns ────────────────────────────────────────────────────────────

def forward_return(df: pd.DataFrame, position: int, offset: int) -> float | None:
    target = position + offset
    if target >= len(df):
        return None
    entry = df["Close"].iloc[position]
    exit_ = df["Close"].iloc[target]
    return (exit_ - entry) / entry * 100


def fmt_ret(val: float | None) -> str:
    if val is None:
        return "  n/a  "
    sign = "+" if val >= 0 else ""
    colour = "\033[92m" if val >= 0 else "\033[91m"  # green / red
    reset  = "\033[0m"
    return f"{colour}{sign}{val:5.1f}%{reset}"


def fmt_price(val: float) -> str:
    return f"${val:7.2f}"


# ── Report ────────────────────────────────────────────────────────────────────

def print_divider(width: int = 80) -> None:
    print("  " + "─" * width)


def run_backtest() -> None:
    print()
    df_full = fetch_data(SYMBOL, FETCH_YEARS)
    df      = compute_signals(df_full)

    today        = pd.Timestamp(date.today())
    cutoff_start = pd.Timestamp(date.today() - timedelta(days=BACKTEST_YEARS * 365))

    # Golden cross events within the reporting window
    events = df[(df["golden_cross"]) & (df.index >= cutoff_start)].copy()

    print()
    print_divider()
    print(f"  Golden Cross Backtest  ·  {SYMBOL}  ·  50-day SMA crosses above 200-day SMA")
    print(f"  Reporting window : {cutoff_start.date()} → {today.date()}")
    print(f"  Fetch window     : {df.index[0].date()} → {df.index[-1].date()}  "
          f"({len(df):,} trading sessions)")
    print_divider()

    # ── Current SMA state ─────────────────────────────────────────────────────
    last   = df.iloc[-1]
    gap    = (last["SMA50"] - last["SMA200"]) / last["SMA200"] * 100
    rel    = "ABOVE" if last["SMA50"] > last["SMA200"] else "BELOW"
    colour = "\033[92m" if rel == "ABOVE" else "\033[91m"
    reset  = "\033[0m"
    print(f"  Current state ({df.index[-1].date()}):")
    print(f"    Price  = {fmt_price(last['Close'])}")
    print(f"    SMA50  = {fmt_price(last['SMA50'])}")
    print(f"    SMA200 = {fmt_price(last['SMA200'])}")
    print(f"    SMA50 is {colour}{rel}{reset} SMA200 by {abs(gap):.2f}%")
    print_divider()

    # ── Event table ────────────────────────────────────────────────────────────
    if events.empty:
        print(f"  No golden cross events found between {cutoff_start.date()} and {today.date()}.")
        print_divider()
        return

    col_w = 7
    label_row  = "  " + f"{'Date':<12}  {'Price':>8}  {'SMA50':>8}  {'SMA200':>8}"
    for lbl, _ in FORWARD_PERIODS:
        label_row += f"  {lbl:>{col_w}}"
    print(label_row)

    sep_row = "  " + f"{'─'*12}  {'─'*8}  {'─'*8}  {'─'*8}"
    for _ in FORWARD_PERIODS:
        sep_row += f"  {'─'*col_w}"
    print(sep_row)

    # Accumulate forward returns for the summary
    fwd_buckets: dict[str, list[float]] = {lbl: [] for lbl, _ in FORWARD_PERIODS}

    for ts, row in events.iterrows():
        pos   = df.index.get_loc(ts)
        fwds  = [forward_return(df, pos, offset) for _, offset in FORWARD_PERIODS]

        data_row = (
            f"  {str(ts.date()):<12}  "
            f"{fmt_price(row['Close'])}  "
            f"{fmt_price(row['SMA50'])}  "
            f"{fmt_price(row['SMA200'])}"
        )
        for i, (lbl, _) in enumerate(FORWARD_PERIODS):
            data_row += f"  {fmt_ret(fwds[i]):>{col_w}}"
            if fwds[i] is not None:
                fwd_buckets[lbl].append(fwds[i])

        print(data_row)

    print_divider()
    n = len(events)
    print(f"  {n} golden cross event(s) in the last {BACKTEST_YEARS} years.\n")

    # ── Summary statistics ─────────────────────────────────────────────────────
    if n > 0:
        print("  Forward-return summary after golden cross (where data available):")
        print(f"  {'Period':<6}  {'Avg return':>11}  {'Win rate':>9}  {'Samples':>7}")
        print(f"  {'─'*6}  {'─'*11}  {'─'*9}  {'─'*7}")
        for lbl, _ in FORWARD_PERIODS:
            vals = fwd_buckets[lbl]
            if not vals:
                print(f"  {lbl:<6}  {'n/a':>11}  {'n/a':>9}  {'0':>7}")
                continue
            avg      = sum(vals) / len(vals)
            win_rate = sum(1 for v in vals if v > 0) / len(vals) * 100
            avg_str  = f"{'+' if avg >= 0 else ''}{avg:.1f}%"
            wr_str   = f"{win_rate:.0f}%"
            print(f"  {lbl:<6}  {avg_str:>11}  {wr_str:>9}  {len(vals):>7}")

    print_divider()

    # ── Also show all death crosses for context ───────────────────────────────
    deaths = df[(df["death_cross"]) & (df.index >= cutoff_start)]
    if not deaths.empty:
        print(f"\n  Death cross events in the same window (50-day crossed BELOW 200-day):")
        for ts, row in deaths.iterrows():
            print(f"    {str(ts.date()):<12}  price={fmt_price(row['Close'])}  "
                  f"SMA50={fmt_price(row['SMA50'])}  SMA200={fmt_price(row['SMA200'])}")
        print()

    # ── Chart (ASCII sparkline of SMA50 vs SMA200) ────────────────────────────
    _print_ascii_chart(df[df.index >= cutoff_start], events)


def _print_ascii_chart(df: pd.DataFrame, events: pd.DataFrame) -> None:
    """Print a simple ASCII line showing when SMA50 was above/below SMA200."""
    print("  SMA50 vs SMA200 — monthly snapshot (▲ = above, ▼ = below, ✦ = golden cross)")
    print("  ", end="")

    # Sample roughly one bar per month
    step    = max(1, len(df) // 36)
    sampled = df.iloc[::step]
    cross_dates = set(events.index.normalize())

    for ts, row in sampled.iterrows():
        is_cross = ts.normalize() in cross_dates
        if is_cross:
            print("\033[93m✦\033[0m", end="")
        elif row["SMA50"] > row["SMA200"]:
            print("\033[92m▲\033[0m", end="")
        else:
            print("\033[91m▼\033[0m", end="")

    print()
    # Date labels: start and end
    if not sampled.empty:
        print(f"  {str(sampled.index[0].date()):<20}"
              f"{'':^{max(0, len(sampled) - 40)}}"
              f"{str(sampled.index[-1].date()):>20}")
    print()


if __name__ == "__main__":
    try:
        run_backtest()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
