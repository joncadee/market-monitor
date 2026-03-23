#!/usr/bin/env python3
"""
Backtest: RSI Oversold on SPY — last 3 years
─────────────────────────────────────────────
For every event where RSI(14) crossed below 30 in the past 3 years, shows:
  - Entry date and price
  - RSI value at entry and the trough RSI reached during the oversold period
  - Recovery date (when RSI climbed back above 30) and duration in days
  - Forward returns at +1M, +3M, +6M, +12M measured from the entry date

A 5-year fetch window ensures the RSI series is fully warmed up at the start
of the 3-year reporting window.

Usage:
    cd market-monitor
    python scripts/backtest_rsi_oversold.py
"""
from __future__ import annotations

import sys
import warnings
from datetime import date, timedelta

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")

import pandas as pd
import yfinance as yf

# ── Parameters ───────────────────────────────────────────────────────────────

SYMBOL         = "SPY"
RSI_PERIOD     = 14
THRESHOLD      = 30.0
BACKTEST_YEARS = 3
FETCH_YEARS    = 5

FORWARD_PERIODS = [
    ("+1M",  21),
    ("+3M",  63),
    ("+6M",  126),
    ("+12M", 252),
]

# ── Data helpers ─────────────────────────────────────────────────────────────

def fetch_data(symbol: str, years: int) -> pd.DataFrame:
    print(f"  Downloading {years}y of {symbol} daily data from Yahoo Finance …", flush=True)
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=f"{years}y", interval="1d")
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.sort_index(inplace=True)
    return df


def compute_rsi(close: pd.Series, period: int) -> pd.Series:
    """Wilder's RSI — matches the live signal implementation exactly."""
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    alpha    = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, float("nan"))
    return 100.0 - (100.0 / (1.0 + rs))


def add_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["RSI"] = compute_rsi(df["Close"], RSI_PERIOD)
    oversold  = df["RSI"] < THRESHOLD
    # Entry: first day RSI crosses below threshold
    df["rsi_entry"] = oversold & ~oversold.shift(1).fillna(False)
    return df


# ── Forward return helpers ────────────────────────────────────────────────────

def forward_return(df: pd.DataFrame, pos: int, offset: int) -> float | None:
    target = pos + offset
    if target >= len(df):
        return None
    return (df["Close"].iloc[target] - df["Close"].iloc[pos]) / df["Close"].iloc[pos] * 100


def recovery_info(df: pd.DataFrame, entry_pos: int) -> tuple[str, int, float]:
    """
    Starting from entry_pos, scan forward until RSI climbs back above THRESHOLD.
    Returns (recovery_date_str, days_oversold, trough_rsi).
    """
    trough   = df["RSI"].iloc[entry_pos]
    end_pos  = entry_pos

    for i in range(entry_pos, len(df)):
        rsi_i = df["RSI"].iloc[i]
        if rsi_i < trough:
            trough = rsi_i
        if i > entry_pos and rsi_i >= THRESHOLD:
            end_pos = i
            break
    else:
        # Reached end of data without recovering
        end_pos = len(df) - 1

    days_oversold  = end_pos - entry_pos
    recovery_date  = str(df.index[end_pos].date()) if end_pos < len(df) else "ongoing"
    return recovery_date, days_oversold, trough


# ── Formatting ────────────────────────────────────────────────────────────────

def fmt_ret(val: float | None) -> str:
    if val is None:
        return "   n/a  "
    colour = "\033[92m" if val >= 0 else "\033[91m"
    return f"{colour}{'+' if val >= 0 else ''}{val:5.1f}%\033[0m"


def fmt_price(val: float) -> str:
    return f"${val:7.2f}"


def fmt_rsi(val: float) -> str:
    colour = "\033[91m" if val < THRESHOLD else "\033[93m" if val < 50 else "\033[92m"
    return f"{colour}{val:5.1f}\033[0m"


def print_div(w: int = 88) -> None:
    print("  " + "─" * w)


# ── Report ────────────────────────────────────────────────────────────────────

def run_backtest() -> None:
    print()
    df      = add_signals(fetch_data(SYMBOL, FETCH_YEARS))
    today   = pd.Timestamp(date.today())
    cutoff  = pd.Timestamp(date.today() - timedelta(days=BACKTEST_YEARS * 365))
    events  = df[(df["rsi_entry"]) & (df.index >= cutoff)]

    print()
    print_div()
    print(f"  RSI Oversold Backtest  ·  {SYMBOL}  ·  RSI({RSI_PERIOD}) crosses below {THRESHOLD:.0f}")
    print(f"  Reporting window : {cutoff.date()} → {today.date()}")
    print(f"  Fetch window     : {df.index[0].date()} → {df.index[-1].date()}  "
          f"({len(df):,} trading sessions)")
    print_div()

    # ── Current RSI ───────────────────────────────────────────────────────────
    last     = df.iloc[-1]
    cur_rsi  = last["RSI"]
    cur_col  = "\033[91m" if cur_rsi < THRESHOLD else "\033[92m"
    status   = "OVERSOLD" if cur_rsi < THRESHOLD else "not oversold"
    print(f"  Current state ({df.index[-1].date()}):")
    print(f"    Price   = {fmt_price(last['Close'])}")
    print(f"    RSI(14) = {cur_col}{cur_rsi:.2f}\033[0m  ({status})")
    print_div()

    if events.empty:
        print(f"  No RSI oversold events found between {cutoff.date()} and {today.date()}.")
        print_div()
        return

    # ── Event table header ────────────────────────────────────────────────────
    hdr = (f"  {'Entry date':<12}  {'Price':>8}  {'RSI@entry':>9}  "
           f"{'Trough RSI':>10}  {'Recovery':>12}  {'Days':>5}")
    for lbl, _ in FORWARD_PERIODS:
        hdr += f"  {lbl:>8}"
    print(hdr)

    sep = (f"  {'─'*12}  {'─'*8}  {'─'*9}  {'─'*10}  {'─'*12}  {'─'*5}")
    for _ in FORWARD_PERIODS:
        sep += f"  {'─'*8}"
    print(sep)

    fwd_buckets: dict[str, list[float]] = {lbl: [] for lbl, _ in FORWARD_PERIODS}

    for ts, row in events.iterrows():
        pos             = df.index.get_loc(ts)
        rec_date, days, trough = recovery_info(df, pos)
        fwds            = [forward_return(df, pos, off) for _, off in FORWARD_PERIODS]

        # Flag still-ongoing oversold periods
        days_str = f"{days:>4}d" if rec_date != "ongoing" else "  --"
        rec_str  = rec_date if rec_date != "ongoing" else "   ongoing"

        line = (f"  {str(ts.date()):<12}  "
                f"{fmt_price(row['Close'])}  "
                f"  {fmt_rsi(row['RSI']):>9}  "
                f"    {fmt_rsi(trough):>10}  "
                f"  {rec_str:>12}  "
                f"{days_str:>5}")
        for i, (lbl, _) in enumerate(FORWARD_PERIODS):
            line += f"  {fmt_ret(fwds[i]):>8}"
            if fwds[i] is not None:
                fwd_buckets[lbl].append(fwds[i])

        print(line)

    print_div()
    n = len(events)
    print(f"  {n} oversold event(s) in the last {BACKTEST_YEARS} years.\n")

    # ── Summary stats ─────────────────────────────────────────────────────────
    print("  Forward-return summary from entry date (where data available):")
    print(f"  {'Period':<6}  {'Avg return':>11}  {'Median':>8}  "
          f"{'Best':>8}  {'Worst':>8}  {'Win%':>6}  {'N':>4}")
    print(f"  {'─'*6}  {'─'*11}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*6}  {'─'*4}")

    for lbl, _ in FORWARD_PERIODS:
        vals = sorted(fwd_buckets[lbl])
        if not vals:
            print(f"  {lbl:<6}  {'n/a':>11}")
            continue
        avg    = sum(vals) / len(vals)
        median = vals[len(vals) // 2]
        best   = max(vals)
        worst  = min(vals)
        wins   = sum(1 for v in vals if v > 0) / len(vals) * 100
        def _f(v: float) -> str:
            return f"{'+' if v>=0 else ''}{v:.1f}%"
        print(f"  {lbl:<6}  {_f(avg):>11}  {_f(median):>8}  "
              f"{_f(best):>8}  {_f(worst):>8}  {wins:>5.0f}%  {len(vals):>4}")

    print_div()

    # ── ASCII RSI chart ───────────────────────────────────────────────────────
    _print_rsi_chart(df[df.index >= cutoff], events)


def _print_rsi_chart(df: pd.DataFrame, events: pd.DataFrame) -> None:
    """
    Compact RSI sparkline.  Each character represents ~1 week of trading.
    Colour coding:
      red    ▼  RSI < 30 (oversold)
      yellow ─  RSI 30–50
      green  ▲  RSI > 50
      bright ✦  entry point (first day crossing below 30)
    """
    print("  RSI level — weekly snapshot  "
          "(\033[91m▼\033[0m oversold  \033[93m─\033[0m 30–50  "
          "\033[92m▲\033[0m >50  \033[93m✦\033[0m entry)")
    print("  ", end="")

    step        = max(1, len(df) // 52)
    sampled     = df.iloc[::step]
    entry_dates = set(events.index.normalize())

    for ts, row in sampled.iterrows():
        rsi = row["RSI"]
        if pd.isna(rsi):
            print(" ", end="")
            continue
        if ts.normalize() in entry_dates:
            print("\033[93m✦\033[0m", end="")
        elif rsi < THRESHOLD:
            print("\033[91m▼\033[0m", end="")
        elif rsi < 50:
            print("\033[93m─\033[0m", end="")
        else:
            print("\033[92m▲\033[0m", end="")

    print()
    if not sampled.empty:
        n = len(sampled)
        print(f"  {str(sampled.index[0].date()):<20}"
              f"{'':^{max(0, n - 40)}}"
              f"{str(sampled.index[-1].date()):>20}")
    print()


if __name__ == "__main__":
    try:
        run_backtest()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
