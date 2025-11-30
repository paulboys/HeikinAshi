#!/usr/bin/env python
"""CLI to fetch OHLC data, compute Heiken Ashi candles, and save a chart.

Example:
    python scripts/plot_heiken_ashi.py --ticker AAPL --start 2024-01-01 --end 2024-06-01 --output aapl_ha.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from stockcharts.charts.heiken_ashi import heiken_ashi
from stockcharts.data.fetch import fetch_ohlc


def plot_heiken_ashi(
    ticker: str, start: str | None, end: str | None, interval: str, output: Path
) -> None:
    df = fetch_ohlc(ticker, start=start, end=end, interval=interval)
    ha = heiken_ashi(df)

    fig, ax = plt.subplots(figsize=(10, 5))

    # Convert dates to matplotlib date numbers for x-axis
    dates = mdates.date2num(ha.index.to_pydatetime())

    # Calculate bar width based on data interval (in days)
    if interval == "1d":
        width = 0.6
    elif interval == "1wk":
        width = 5.0
    elif interval == "1mo":
        width = 20.0
    else:
        width = 0.6

    # Basic candlestick using HA values with dates
    colors = [
        "green" if ha_close >= ha_open else "red"
        for ha_open, ha_close in zip(ha["HA_Open"], ha["HA_Close"])
    ]

    for i, (date_num, (idx, row)) in enumerate(zip(dates, ha.iterrows())):
        # Vertical line for high-low range
        ax.plot(
            [date_num, date_num],
            [row["HA_Low"], row["HA_High"]],
            color=colors[i],
            linewidth=1,
        )
        # Rectangle for open-close body
        lower = min(row["HA_Open"], row["HA_Close"])
        upper = max(row["HA_Open"], row["HA_Close"])
        ax.add_patch(
            plt.Rectangle(
                (date_num - width / 2, lower),
                width,
                upper - lower if upper - lower != 0 else 0.001,
                color=colors[i],
                alpha=0.7,
            )
        )

    # Format x-axis as dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate()  # Rotate date labels for better readability

    # Ensure dates are visible at the bottom
    ax.set_xlabel("Date")
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    ax.set_title(f"Heiken Ashi: {ticker} ({interval})")
    ax.set_ylabel("Price")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output)
    print(f"Saved chart to {output}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate a Heiken Ashi chart for a ticker")
    p.add_argument("--ticker", required=True, help="Ticker symbol, e.g. AAPL")
    p.add_argument("--start", help="Start date YYYY-MM-DD", default=None)
    p.add_argument("--end", help="End date YYYY-MM-DD", default=None)
    p.add_argument("--interval", help="Data interval (1d,1wk,1mo)", default="1d")
    p.add_argument("--output", help="Output PNG file path", default="heiken_ashi.png")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    output_path = Path(args.output)
    plot_heiken_ashi(args.ticker, args.start, args.end, args.interval, output_path)


if __name__ == "__main__":  # pragma: no cover
    main()
