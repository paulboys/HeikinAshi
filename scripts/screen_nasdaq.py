#!/usr/bin/env python
"""CLI to screen NASDAQ stocks for Heiken Ashi candle patterns.

Example:
    # SWING TRADER: Find reversals with minimum volume filter (recommended)
    python scripts/screen_nasdaq.py --color green --changed-only --lookback 3mo --period 1d --min-volume 500000

    # DAY TRADER: High volume stocks only, last 5 days
    python scripts/screen_nasdaq.py --color green --changed-only --lookback 5d --period 1d --min-volume 1000000 --limit 100

    # POSITION TRADER: Weekly candles with volume filter
    python scripts/screen_nasdaq.py --color green --changed-only --lookback 1y --period 1wk --min-volume 500000

    # Custom date range with volume filter
    python scripts/screen_nasdaq.py --color green --changed-only --start 2024-01-01 --end 2025-10-14 --period 1d --min-volume 500000

    # Find all green candles (not just reversals) with volume filter
    python scripts/screen_nasdaq.py --color green --lookback 6mo --period 1wk --min-volume 1000000

    # Export results to CSV with volume data
    python scripts/screen_nasdaq.py --color green --changed-only --lookback 3mo --period 1d --min-volume 500000 --output green_reversals.csv

    # Filter by minimum price (e.g., stocks above $10)
    python scripts/screen_nasdaq.py --color green --changed-only --lookback 3mo --period 1d --min-volume 500000 --min-price 10
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from stockcharts.screener.screener import screen_nasdaq


def main() -> None:
    """Entry point: screen NASDAQ stocks for Heiken Ashi patterns."""
    parser = argparse.ArgumentParser(
        description="Screen NASDAQ stocks for Heiken Ashi candle patterns"
    )
    parser.add_argument(
        "--color",
        choices=["green", "red", "all"],
        default="green",
        help="Filter by candle color: green (bullish), red (bearish), or all",
    )
    parser.add_argument(
        "--period",
        choices=["1d", "1wk", "1mo"],
        default="1d",
        help="Aggregation period (how data is grouped): 1d (daily), 1wk (weekly), 1mo (monthly)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of tickers to screen (for testing)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay in seconds between API calls (default: 0.5)",
    )
    parser.add_argument("--output", type=str, default=None, help="Output CSV file path (optional)")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress messages")
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Only show tickers where candle color just changed (e.g., red to green)",
    )
    parser.add_argument(
        "--lookback",
        type=str,
        default=None,
        help="How far back to fetch data: '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', etc. "
        "Day traders: 5d/1mo. Swing traders: 3mo/6mo. Position traders: 1y/5y. "
        "Cannot be used with --start/--end.",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date YYYY-MM-DD. Cannot be used with --period.",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date YYYY-MM-DD. Cannot be used with --period.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show detailed error messages for debugging",
    )
    parser.add_argument(
        "--min-volume",
        type=float,
        default=None,
        help="Minimum average daily volume (in shares). Filters out low-volume stocks. "
        "Recommended: 500000 (500K) for swing trading, 1000000 (1M) for day trading.",
    )
    parser.add_argument(
        "--min-price",
        type=float,
        default=None,
        help="Minimum stock price (in dollars). Filters out stocks below this price. "
        "Useful for avoiding penny stocks (e.g., --min-price 5 or --min-price 10).",
    )

    args = parser.parse_args()

    # Validate parameter combinations
    if args.lookback and (args.start or args.end):
        parser.error("Cannot specify both --lookback and --start/--end parameters")

    # Run the screener
    results = screen_nasdaq(
        color_filter=args.color,
        period=args.period,
        limit=args.limit,
        delay=args.delay,
        verbose=not args.quiet,
        changed_only=args.changed_only,
        lookback=args.lookback,
        start=args.start,
        end=args.end,
        debug=args.debug,
        min_volume=args.min_volume,
        min_price=args.min_price,
    )

    if not results:
        print(f"\nNo {args.color} candles found.")
        sys.exit(0)

    # Display results
    print(
        f"\n{'Ticker':<10} {'Color':<8} {'Previous':<10} {'Changed':<10} {'Price':<10} {'Avg Volume':<15} {'HA_Open':<12} {'HA_Close':<12} {'Last Date':<12}"
    )
    print("=" * 115)

    for result in results:
        changed_symbol = "✓" if result.color_changed else ""
        volume_str = f"{result.avg_volume:,.0f}"
        price_str = f"${result.ha_close:.2f}"
        print(
            f"{result.ticker:<10} {result.color:<8} {result.previous_color:<10} {changed_symbol:<10} "
            f"{price_str:<10} {volume_str:<15} {result.ha_open:<12.2f} {result.ha_close:<12.2f} "
            f"{result.last_date:<12}"
        )

    print("=" * 115)
    changed_count = sum(1 for r in results if r.color_changed)
    print(
        f"Total: {len(results)} tickers with {args.color} candles ({changed_count} just changed)\n"
    )

    # Export to CSV if requested
    if args.output:
        df = pd.DataFrame(
            [
                {
                    "ticker": r.ticker,
                    "color": r.color,
                    "previous_color": r.previous_color,
                    "color_changed": r.color_changed,
                    "price": r.ha_close,
                    "avg_volume": r.avg_volume,
                    "ha_open": r.ha_open,
                    "ha_close": r.ha_close,
                    "last_date": r.last_date,
                    "interval": r.interval,
                }
                for r in results
            ]
        )

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        print(f"Results exported to {output_path}")


if __name__ == "__main__":  # pragma: no cover
    main()
