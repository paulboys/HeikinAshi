#!/usr/bin/env python
"""Generate Heiken Ashi charts for all tickers in a CSV file.

Example:
    # Generate charts for all tickers in green_reversals.csv
    python scripts/plot_reversals.py --input green_reversals.csv --output charts/reversals

    # Specify custom interval
    python scripts/plot_reversals.py --input green_reversals.csv --interval 1d --output charts/daily
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from stockcharts.charts.heiken_ashi import heiken_ashi
from stockcharts.data.fetch import fetch_ohlc


def plot_heiken_ashi_chart(ha: pd.DataFrame, ticker: str, interval: str) -> None:
    """Create a Heiken Ashi chart.

    Parameters
    ----------
    ha : pd.DataFrame
        Heiken Ashi DataFrame with HA_Open, HA_High, HA_Low, HA_Close columns
    ticker : str
        Stock symbol for chart title
    interval : str
        Data interval for chart title

    Returns:
    -------
    tuple
        (fig, ax) matplotlib figure and axis objects
    """
    fig, ax = plt.subplots(figsize=(12, 6))

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

    # Determine colors (green if close >= open, red otherwise)
    colors = [
        "green" if ha_close >= ha_open else "red"
        for ha_open, ha_close in zip(ha["HA_Open"], ha["HA_Close"])
    ]

    # Draw candlesticks
    for i, (date_num, (_idx, row)) in enumerate(zip(dates, ha.iterrows())):
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
        height = upper - lower if upper - lower != 0 else 0.001
        ax.add_patch(
            plt.Rectangle((date_num - width / 2, lower), width, height, color=colors[i], alpha=0.7)
        )

    # Format x-axis as dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate()  # Rotate date labels for better readability

    # Ensure dates are visible at the bottom
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    ax.set_title(f"Heiken Ashi: {ticker} ({interval})", fontsize=14, fontweight="bold")
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Price", fontsize=12)
    ax.grid(True, alpha=0.3)

    return fig, ax


def generate_chart(
    ticker: str, interval: str = "1d", output_dir: Path = None, show: bool = False
) -> bool:
    """Generate and save a Heiken Ashi chart for a ticker.

    Parameters
    ----------
    ticker : str
        Stock symbol
    interval : str
        Data interval: "1d", "1wk", or "1mo"
    output_dir : Path
        Directory to save the chart
    show : bool
        Whether to display the chart interactively

    Returns:
    -------
    bool
        True if chart was generated successfully, False otherwise
    """
    try:
        # Fetch data
        df = fetch_ohlc(ticker, interval=interval)

        if df.empty or len(df) < 2:
            print(f"  ⚠ Skipping {ticker}: Insufficient data")
            return False

        # Compute Heiken Ashi
        ha = heiken_ashi(df)

        if ha.empty:
            print(f"  ⚠ Skipping {ticker}: Could not compute Heiken Ashi")
            return False

        # Create the plot
        fig, ax = plot_heiken_ashi_chart(ha, ticker=ticker, interval=interval)

        # Save the chart
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"{ticker}_{interval}.png"
            plt.savefig(output_file, dpi=150, bbox_inches="tight")
            print(f"  ✓ Saved chart: {output_file}")

        # Show if requested
        if show:
            plt.show()
        else:
            plt.close(fig)

        return True

    except Exception as e:
        print(f"  ✗ Error generating chart for {ticker}: {e}")
        return False


def main() -> None:
    """Entry point: parse args and create Heiken Ashi reversal charts."""
    parser = argparse.ArgumentParser(
        description="Generate Heiken Ashi charts for all tickers in a CSV file"
    )
    parser.add_argument(
        "--input", type=str, required=True, help="Input CSV file with ticker column"
    )
    parser.add_argument(
        "--interval",
        type=str,
        default=None,
        help="Data interval: 1d (daily), 1wk (weekly), 1mo (monthly). "
        "If not specified, uses interval from CSV if available.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="charts/reversals",
        help="Output directory for charts (default: charts/reversals)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display charts interactively (default: save only)",
    )

    args = parser.parse_args()

    # Read the CSV file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    df = pd.read_csv(input_path)

    if "ticker" not in df.columns:
        print("Error: CSV file must have a 'ticker' column")
        sys.exit(1)

    tickers = df["ticker"].tolist()

    # Determine interval
    if args.interval:
        interval = args.interval
    elif "interval" in df.columns and not df["interval"].isna().all():
        # Use interval from CSV (assuming all rows have same interval)
        interval = df["interval"].iloc[0]
    else:
        interval = "1d"

    print(f"Generating Heiken Ashi charts for {len(tickers)} tickers ({interval} interval)...")
    print(f"Output directory: {args.output}")
    print("-" * 70)

    output_dir = Path(args.output)
    success_count = 0

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] Processing {ticker}...")
        if generate_chart(ticker, interval=interval, output_dir=output_dir, show=args.show):
            success_count += 1

    print("-" * 70)
    print(f"Complete: {success_count}/{len(tickers)} charts generated successfully")
    print(f"Charts saved to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
