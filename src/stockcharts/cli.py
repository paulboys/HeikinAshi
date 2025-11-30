"""Command-line interface for stockcharts screener."""

import argparse
import os
import sys

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from stockcharts.charts.heiken_ashi import heiken_ashi
from stockcharts.data.fetch import fetch_ohlc
from stockcharts.screener.rsi_divergence import (save_results_to_csv,
                                                 screen_rsi_divergence)
from stockcharts.screener.screener import screen_nasdaq


def _print_disclaimer_once(args: argparse.Namespace) -> None:
    """Print a one-line disclaimer unless suppressed."""
    if getattr(args, "no_disclaimer", False):
        return
    if os.environ.get("STOCKCHARTS_NO_DISCLAIMER") == "1":
        return
    print(
        "[Disclaimer] Educational tool; not financial advice. See DISCLAIMER.md or docs/disclaimer.md. Use --no-disclaimer to hide."
    )


def main_screen() -> int:
    """Screen NASDAQ tickers for Heiken Ashi reversals.

    Side Effects:
        Prints progress/status lines; writes CSV to ``--output`` if results found.

    Returns:
        int: 0 success, non-zero on input/IO errors.
    """
    parser = argparse.ArgumentParser(
        description="Screen NASDAQ stocks for Heiken Ashi color changes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Screen for green reversals (red→green) on daily charts
  stockcharts-screen --color green --changed-only

  # Find red reversals with volume filter (swing trading)
  stockcharts-screen --color red --changed-only --min-volume 500000

  # Day trading setup: 1-hour charts with high volume
  stockcharts-screen --color green --period 1h --lookback 1mo --min-volume 2000000

  # Weekly analysis over 6 months
  stockcharts-screen --color green --period 1wk --lookback 6mo

  # Custom date range
  stockcharts-screen --color green --start 2024-01-01 --end 2024-12-31

  # Filter by pre-screened ticker list from RSI divergence
  stockcharts-screen --color green --changed-only --input-filter bullish_div.csv
        """,
    )

    parser.add_argument(
        "--color",
        choices=["red", "green"],
        default="green",
        help="Filter by current Heiken Ashi candle color (default: green)",
    )

    parser.add_argument(
        "--period",
        default="1d",
        help="Data aggregation period: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo (default: 1d)",
    )

    parser.add_argument(
        "--lookback",
        default="3mo",
        help="How far back to fetch data: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max (default: 3mo)",
    )

    parser.add_argument(
        "--start", help="Start date in YYYY-MM-DD format (overrides --lookback)"
    )

    parser.add_argument(
        "--end", help="End date in YYYY-MM-DD format (defaults to today)"
    )

    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Only show stocks where color changed in the most recent candle",
    )

    parser.add_argument(
        "--min-volume",
        type=int,
        default=0,
        help="Minimum average daily volume (e.g., 500000 for swing trading)",
    )

    parser.add_argument(
        "--min-price",
        type=float,
        default=None,
        help="Minimum stock price in dollars (e.g., 5.0 or 10.0 to filter out penny stocks)",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of tickers to screen (default: all ~5,120 NASDAQ stocks)",
    )

    parser.add_argument(
        "--output",
        default="results/nasdaq_screen.csv",
        help="Output CSV file path (default: results/nasdaq_screen.csv)",
    )

    parser.add_argument(
        "--input-filter",
        default=None,
        help='CSV file with tickers to screen (must have "Ticker" column). Only screens these tickers instead of all NASDAQ.',
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show detailed error messages for each ticker",
    )

    parser.add_argument(
        "--no-disclaimer",
        action="store_true",
        help="Suppress one-line non-advice disclaimer banner",
    )
    parser.add_argument(
        "--version", action="store_true", help="Print package version and exit"
    )
    args = parser.parse_args()

    if args.version:
        from stockcharts import __version__

        print(f"stockcharts {__version__}")
        return 0

    _print_disclaimer_once(args)

    # Load ticker filter if provided
    ticker_filter = None
    if args.input_filter:
        import os

        import pandas as pd

        if not os.path.exists(args.input_filter):
            print(f"Error: Input filter file not found: {args.input_filter}")
            return 1

        try:
            filter_df = pd.read_csv(args.input_filter)
            if "Ticker" not in filter_df.columns:
                print("Error: Input filter CSV must have a 'Ticker' column")
                return 1

            ticker_filter = filter_df["Ticker"].tolist()
            print(f"Loaded {len(ticker_filter)} tickers from {args.input_filter}")
        except Exception as e:
            print(f"Error loading input filter: {e}")
            return 1

    print(
        f"Screening {'filtered list' if ticker_filter else 'NASDAQ stocks'} for {args.color} Heiken Ashi candles..."
    )
    print(f"Period: {args.period}, Lookback: {args.lookback}")
    if args.min_volume > 0:
        print(f"Minimum volume: {args.min_volume:,} shares/day")
    if args.min_price is not None:
        print(f"Minimum price: ${args.min_price:.2f}")
    if args.changed_only:
        print("Filtering for color changes only")
    if args.limit:
        print(f"Limiting to first {args.limit} tickers")
    print()

    results = screen_nasdaq(
        color_filter=args.color,
        period=args.period,
        lookback=args.lookback,
        start=args.start,
        end=args.end,
        changed_only=args.changed_only,
        min_volume=args.min_volume,
        min_price=args.min_price,
        limit=args.limit,
        debug=args.debug,
        ticker_filter=ticker_filter,
    )

    # Save results to CSV
    if results:
        import os

        import pandas as pd

        os.makedirs(os.path.dirname(args.output), exist_ok=True)

        df = pd.DataFrame(
            [
                {
                    "ticker": r.ticker,
                    "color": r.color,
                    "ha_open": r.ha_open,
                    "ha_close": r.ha_close,
                    "last_date": r.last_date,
                    "period": r.interval,
                    "color_changed": r.color_changed,
                    "avg_volume": r.avg_volume,
                }
                for r in results
            ]
        )

        df.to_csv(args.output, index=False)
        print(f"\nFound {len(results)} stocks matching criteria")
        print(f"Results saved to: {args.output}")
    else:
        print("\nNo stocks found matching criteria")

    return 0


def main_plot() -> int:
    """Generate Heiken Ashi charts from screener CSV output.

    Expects an input CSV containing a ``Ticker`` or ``ticker`` column.
    Produces PNG files under ``--output-dir``.
    """
    parser = argparse.ArgumentParser(
        description="Generate Heiken Ashi charts from screener results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Plot all results from default location
  stockcharts-plot

  # Plot from specific CSV file
  stockcharts-plot --input results/green_reversals.csv

  # Save charts to specific directory
  stockcharts-plot --output-dir my_charts/
        """,
    )

    parser.add_argument(
        "--input",
        default="results/nasdaq_screen.csv",
        help="Input CSV file from screener (default: results/nasdaq_screen.csv)",
    )

    parser.add_argument(
        "--output-dir",
        default="charts/",
        help="Output directory for chart images (default: charts/)",
    )

    parser.add_argument(
        "--period", default="1d", help="Data aggregation period (default: 1d)"
    )

    parser.add_argument(
        "--lookback", default="3mo", help="Historical data lookback (default: 3mo)"
    )

    parser.add_argument(
        "--no-disclaimer",
        action="store_true",
        help="Suppress one-line non-advice disclaimer banner",
    )
    parser.add_argument(
        "--version", action="store_true", help="Print package version and exit"
    )
    args = parser.parse_args()

    if args.version:
        from stockcharts import __version__

        print(f"stockcharts {__version__}")
        return 0

    _print_disclaimer_once(args)

    import os

    import pandas as pd

    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        return 1

    os.makedirs(args.output_dir, exist_ok=True)

    df = pd.read_csv(args.input)

    # Handle both 'Ticker' and 'ticker' column names (case-insensitive)
    ticker_col = None
    if "Ticker" in df.columns:
        ticker_col = "Ticker"
    elif "ticker" in df.columns:
        ticker_col = "ticker"
    else:
        print("Error: CSV must have a 'Ticker' or 'ticker' column")
        print(f"Available columns: {', '.join(df.columns)}")
        return 1

    tickers = df[ticker_col].tolist()

    print(f"Generating Heiken Ashi charts for {len(tickers)} stocks...")
    print(f"Output directory: {args.output_dir}")
    print()

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] Plotting {ticker}...", end=" ")

        try:
            data = fetch_ohlc(ticker, interval=args.period, lookback=args.lookback)
            if data is None or data.empty:
                print("❌ No data")
                continue

            ha_data = heiken_ashi(data)

            # Create chart
            fig, ax = plt.subplots(figsize=(14, 7))

            # Convert index to datetime explicitly for matplotlib
            dates = mdates.date2num(pd.to_datetime(ha_data.index).to_pydatetime())

            for idx in range(len(ha_data)):
                date = dates[idx]
                row = ha_data.iloc[idx]
                color = "green" if row["HA_Close"] >= row["HA_Open"] else "red"

                # Candle body
                body_height = abs(row["HA_Close"] - row["HA_Open"])
                body_bottom = min(row["HA_Open"], row["HA_Close"])
                rect = Rectangle(
                    (date - 0.4, body_bottom),
                    0.8,
                    body_height,
                    facecolor=color,
                    edgecolor="black",
                    linewidth=0.5,
                )
                ax.add_patch(rect)

                # Wicks
                ax.plot(
                    [date, date],
                    [row["HA_Low"], body_bottom],
                    color="black",
                    linewidth=0.5,
                )
                ax.plot(
                    [date, date],
                    [body_bottom + body_height, row["HA_High"]],
                    color="black",
                    linewidth=0.5,
                )

            # Format x-axis with dates
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

            ax.set_xlim(dates[0] - 1, dates[-1] + 1)
            ax.set_ylim(ha_data["HA_Low"].min() * 0.95, ha_data["HA_High"].max() * 1.05)
            ax.set_xlabel("Date")
            ax.set_ylabel("Price ($)")
            ax.set_title(f"{ticker} - Heiken Ashi ({args.period})")
            ax.grid(True, alpha=0.3)

            output_path = os.path.join(args.output_dir, f"{ticker}_{args.period}.png")
            plt.savefig(output_path, dpi=150, bbox_inches="tight")
            plt.close()

            print(f"✓ Saved to {output_path}")

        except Exception as e:
            print(f"❌ Error: {e}")

    print(f"\nCompleted! Charts saved to {args.output_dir}")
    return 0


def main_rsi_divergence() -> int:
    """Screen NASDAQ tickers for price/RSI divergences.

    Supports price/volume filters, pivot method selection, and optional
    3-point sequence scoring with ATR normalization.
    """
    parser = argparse.ArgumentParser(
        description="Screen NASDAQ stocks for RSI/Price divergences",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Screen for all divergences
  stockcharts-rsi-divergence

  # Find only bullish divergences (potential buy signals)
  stockcharts-rsi-divergence --type bullish

  # Find bearish divergences (potential sell signals)
  stockcharts-rsi-divergence --type bearish

  # Filter by price range
  stockcharts-rsi-divergence --min-price 10 --max-price 100

  # Filter by price and volume (swing trading)
  stockcharts-rsi-divergence --min-price 10 --min-volume 500000

  # Day trading setup with high volume
  stockcharts-rsi-divergence --type bullish --min-volume 2000000

  # Use custom RSI period
  stockcharts-rsi-divergence --rsi-period 21

  # Use longer lookback period (6 months)
  stockcharts-rsi-divergence --period 6mo
        """,
    )

    parser.add_argument(
        "--type",
        choices=["bullish", "bearish", "all"],
        default="all",
        help="Type of divergence to screen for (default: all)",
    )

    parser.add_argument(
        "--period",
        default="3mo",
        help="Historical breadth period (1mo,3mo,6mo,1y,2y,5y,10y,ytd,max). Ignored if --start and --end provided.",
    )
    parser.add_argument(
        "--interval",
        default="1d",
        choices=["1d", "1wk", "1mo"],
        help="Candle interval for aggregation (default: 1d)",
    )
    parser.add_argument(
        "--start", help="Explicit start date YYYY-MM-DD (requires --end to take effect)"
    )
    parser.add_argument(
        "--end", help="Explicit end date YYYY-MM-DD (requires --start to take effect)"
    )

    parser.add_argument(
        "--rsi-period",
        type=int,
        default=14,
        help="RSI calculation period (default: 14)",
    )

    parser.add_argument(
        "--min-price",
        type=float,
        default=None,
        help="Minimum stock price in dollars (e.g., 5.0 or 10.0)",
    )

    parser.add_argument(
        "--max-price",
        type=float,
        default=None,
        help="Maximum stock price in dollars (e.g., 100.0)",
    )

    parser.add_argument(
        "--min-volume",
        type=float,
        default=None,
        help="Minimum average daily volume (e.g., 500000 for 500K shares/day)",
    )

    parser.add_argument(
        "--swing-window",
        type=int,
        default=5,
        help="Window for swing point detection (default: 5)",
    )

    parser.add_argument(
        "--lookback",
        type=int,
        default=60,
        help="Number of bars to look back for divergence (default: 60)",
    )

    parser.add_argument(
        "--min-swing-points",
        type=int,
        choices=[2, 3],
        default=2,
        help="Minimum swing points required for divergence (2 or 3, default: 2). Use 3 for stronger confirmation.",
    )

    parser.add_argument(
        "--output",
        default="results/rsi_divergence.csv",
        help="Output CSV file path (default: results/rsi_divergence.csv)",
    )

    parser.add_argument(
        "--exclude-breakouts",
        action="store_true",
        help="Exclude divergences where breakout already occurred (price moved past threshold)",
    )

    parser.add_argument(
        "--breakout-threshold",
        type=float,
        default=0.05,
        help="Percentage move to consider breakout complete (default: 0.05 = 5%%)",
    )

    parser.add_argument(
        "--exclude-failed-breakouts",
        action="store_true",
        help="Exclude divergences with failed breakout attempts (price reversed after trying)",
    )

    parser.add_argument(
        "--failed-lookback",
        type=int,
        default=10,
        help="Bars to check for failed breakout (default: 10)",
    )

    parser.add_argument(
        "--failed-attempt-threshold",
        type=float,
        default=0.03,
        help='Percentage move to consider breakout "attempted" (default: 0.03 = 3%%)',
    )

    parser.add_argument(
        "--failed-reversal-threshold",
        type=float,
        default=0.01,
        help='Percentage from divergence to consider breakout "failed" (default: 0.01 = 1%%)',
    )

    parser.add_argument(
        "--index-proximity-factor",
        type=int,
        default=2,
        help="Multiplier for swing window to allow bar index gap tolerance (default: 2)",
    )

    parser.add_argument(
        "--sequence-tolerance-pct",
        type=float,
        default=0.002,
        help="Relative tolerance for 3-point price sequences (default: 0.002 = 0.2%%)",
    )

    parser.add_argument(
        "--rsi-sequence-tolerance",
        type=float,
        default=0.0,
        help="Extra RSI tolerance in points for 3-point sequences (default: 0.0)",
    )

    parser.add_argument(
        "--pivot-method",
        choices=["swing", "ema-deriv"],
        default="swing",
        help="Pivot detection method: swing (window-based), ema-deriv (EMA derivative smoothing) (default: swing)",
    )

    parser.add_argument(
        "--ema-price-span",
        type=int,
        default=5,
        help="EMA smoothing span for price when using ema-deriv (default: 5)",
    )

    parser.add_argument(
        "--ema-rsi-span",
        type=int,
        default=5,
        help="EMA smoothing span for RSI when using ema-deriv (default: 5)",
    )

    parser.add_argument(
        "--use-sequence-scoring",
        action="store_true",
        help="Enable ATR-normalized 3-point sequence scoring for better quality filtering",
    )

    parser.add_argument(
        "--min-sequence-score",
        type=float,
        default=1.0,
        help="Minimum score to accept a 3-point sequence when --use-sequence-scoring enabled (default: 1.0)",
    )

    parser.add_argument(
        "--max-bar-gap",
        type=int,
        default=10,
        help="Max bar distance between price and RSI pivots for sequence scoring (default: 10)",
    )

    parser.add_argument(
        "--min-magnitude-atr-mult",
        type=float,
        default=0.5,
        help="Min price move as ATR multiple for sequence scoring (default: 0.5)",
    )

    parser.add_argument(
        "--atr-period",
        type=int,
        default=14,
        help="ATR period for magnitude filtering in sequence scoring (default: 14)",
    )

    parser.add_argument(
        "--no-disclaimer",
        action="store_true",
        help="Suppress one-line non-advice disclaimer banner",
    )
    parser.add_argument(
        "--version", action="store_true", help="Print package version and exit"
    )
    args = parser.parse_args()

    if args.version:
        from stockcharts import __version__

        print(f"stockcharts {__version__}")
        return 0

    _print_disclaimer_once(args)

    print("Screening NASDAQ stocks for RSI divergences...")
    print(f"Divergence type: {args.type}")
    print(
        f"Period: {args.period}, Interval: {args.interval}, RSI period: {args.rsi_period}"
    )
    print(f"Pivot method: {args.pivot_method}", end="")
    if args.pivot_method == "ema-deriv":
        print(f" (price span: {args.ema_price_span}, RSI span: {args.ema_rsi_span})")
    else:
        print(f" (window: {args.swing_window})")
    print(
        f"Min swing points: {args.min_swing_points} ({'3-point divergence required' if args.min_swing_points == 3 else '2-point divergence (standard)'})"
    )
    if args.use_sequence_scoring:
        print(
            f"Sequence scoring: ENABLED (min score: {args.min_sequence_score:.2f}, ATR mult: {args.min_magnitude_atr_mult:.2f}, max bar gap: {args.max_bar_gap})"
        )
    if args.start and args.end:
        print(f"Date range override: {args.start} → {args.end}")
    if args.min_price is not None:
        print(f"Minimum price: ${args.min_price:.2f}")
    if args.max_price is not None:
        print(f"Maximum price: ${args.max_price:.2f}")
    if args.min_volume is not None:
        print(f"Minimum volume: {args.min_volume:,.0f} shares/day")
    if args.exclude_breakouts:
        print(
            f"Excluding completed breakouts (threshold: {args.breakout_threshold*100:.1f}%)"
        )
    if args.exclude_failed_breakouts:
        print(
            f"Excluding failed breakouts (attempt: {args.failed_attempt_threshold*100:.1f}%, reversal: {args.failed_reversal_threshold*100:.1f}%)"
        )
    print()

    results = screen_rsi_divergence(
        tickers=None,  # Use all NASDAQ
        period=args.period,
        interval=args.interval,
        rsi_period=args.rsi_period,
        divergence_type=args.type,
        min_price=args.min_price,
        max_price=args.max_price,
        min_volume=args.min_volume,
        swing_window=args.swing_window,
        lookback=args.lookback,
        start=args.start,
        end=args.end,
        exclude_breakouts=args.exclude_breakouts,
        breakout_threshold=args.breakout_threshold,
        exclude_failed_breakouts=args.exclude_failed_breakouts,
        failed_lookback_window=args.failed_lookback,
        failed_attempt_threshold=args.failed_attempt_threshold,
        failed_reversal_threshold=args.failed_reversal_threshold,
        min_swing_points=args.min_swing_points,
        index_proximity_factor=args.index_proximity_factor,
        sequence_tolerance_pct=args.sequence_tolerance_pct,
        rsi_sequence_tolerance=args.rsi_sequence_tolerance,
        pivot_method=args.pivot_method,
        zigzag_pct=0.03,  # deprecated but kept for backward compat
        zigzag_atr_mult=2.0,  # deprecated but kept for backward compat
        zigzag_atr_period=14,  # deprecated but kept for backward compat
        ema_price_span=args.ema_price_span,
        ema_rsi_span=args.ema_rsi_span,
        use_sequence_scoring=args.use_sequence_scoring,
        min_sequence_score=args.min_sequence_score,
        max_bar_gap=args.max_bar_gap,
        min_magnitude_atr_mult=args.min_magnitude_atr_mult,
        atr_period=args.atr_period,
    )

    # Save results
    if results:
        import os

        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        save_results_to_csv(results, args.output)

        # Print summary
        print("\n" + "=" * 80)
        print(f"Found {len(results)} stocks with divergences:")
        print("=" * 80)

        for r in results[:10]:  # Show first 10
            print(f"\n{r.ticker} ({r.company_name})")
            print(f"  Price: ${r.close_price:.2f} | RSI: {r.rsi:.2f}")
            print(f"  Type: {r.divergence_type.upper()}")
            print(f"  {r.details}")

        if len(results) > 10:
            print(f"\n... and {len(results) - 10} more (see {args.output})")
    else:
        print("\nNo divergences found.")

    return 0


def main_plot_divergence() -> int:
    """Plot price + RSI divergence charts from screener results CSV.

    Uses precomputed divergence indices if present in CSV columns.
    Saves PNG charts under ``--output-dir``.
    """
    parser = argparse.ArgumentParser(
        description="Generate Price/RSI divergence charts from screener results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Plot divergences from default RSI screener output
  stockcharts-plot-divergence

  # Plot from specific CSV file
  stockcharts-plot-divergence --input results/rsi_all.csv

  # Save charts to specific directory
  stockcharts-plot-divergence --output-dir divergence_charts/

  # Use custom lookback period
  stockcharts-plot-divergence --lookback 6mo --rsi-period 21
        """,
    )

    parser.add_argument(
        "--input",
        default="results/rsi_divergence.csv",
        help="Input CSV file from RSI divergence screener (default: results/rsi_divergence.csv)",
    )

    parser.add_argument(
        "--output-dir",
        default="charts/divergence/",
        help="Output directory for chart images (default: charts/divergence/)",
    )

    parser.add_argument(
        "--interval", default="1d", help="Data aggregation interval (default: 1d)"
    )

    parser.add_argument(
        "--lookback",
        default="3mo",
        help="Historical data lookback period (default: 3mo)",
    )

    parser.add_argument(
        "--rsi-period",
        type=int,
        default=14,
        help="RSI calculation period (default: 14)",
    )

    parser.add_argument(
        "--swing-window",
        type=int,
        default=5,
        help="Window for swing point detection (default: 5)",
    )

    parser.add_argument(
        "--divergence-lookback",
        type=int,
        default=60,
        help="Number of bars to look back for divergence detection (default: 60)",
    )

    parser.add_argument(
        "--min-swing-points",
        type=int,
        choices=[2, 3],
        default=2,
        help="Minimum number of swing points required for divergence (2 or 3, default: 2)",
    )

    parser.add_argument(
        "--max-plots",
        type=int,
        default=None,
        help="Maximum number of charts to generate (default: all)",
    )

    parser.add_argument(
        "--no-disclaimer",
        action="store_true",
        help="Suppress one-line non-advice disclaimer banner",
    )
    parser.add_argument(
        "--version", action="store_true", help="Print package version and exit"
    )
    args = parser.parse_args()

    if args.version:
        from stockcharts import __version__

        print(f"stockcharts {__version__}")
        return 0

    _print_disclaimer_once(args)

    import os

    import pandas as pd

    from stockcharts.charts.divergence import plot_price_rsi

    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        return 1

    os.makedirs(args.output_dir, exist_ok=True)

    df = pd.read_csv(args.input)

    # Handle both 'Ticker' and 'ticker' column names (case-insensitive)
    ticker_col = None
    if "Ticker" in df.columns:
        ticker_col = "Ticker"
    elif "ticker" in df.columns:
        ticker_col = "ticker"
    else:
        print("Error: CSV must have a 'Ticker' or 'ticker' column")
        print(f"Available columns: {', '.join(df.columns)}")
        return 1

    tickers = df[ticker_col].unique().tolist()

    if args.max_plots:
        tickers = tickers[: args.max_plots]

    print(f"Generating Price/RSI divergence charts for {len(tickers)} stocks...")
    print(f"Output directory: {args.output_dir}")
    print(
        f"Interval: {args.interval}, Lookback: {args.lookback}, RSI Period: {args.rsi_period}"
    )
    print()

    import json

    success_count = 0
    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] Plotting {ticker}...", end=" ")

        try:
            data = fetch_ohlc(ticker, interval=args.interval, lookback=args.lookback)

            # Try to get precomputed divergence indices from CSV
            precomputed = None
            ticker_row = df[df[ticker_col] == ticker]
            if not ticker_row.empty:
                row = ticker_row.iloc[0]
                precomputed = {}

                # Parse bullish indices if present
                if "Bullish_Indices" in row and row["Bullish_Indices"]:
                    try:
                        indices_list = json.loads(row["Bullish_Indices"])
                        if indices_list:
                            precomputed["bullish_indices"] = tuple(
                                pd.to_datetime(idx) for idx in indices_list
                            )
                    except Exception:
                        pass

                # Parse bearish indices if present
                if "Bearish_Indices" in row and row["Bearish_Indices"]:
                    try:
                        indices_list = json.loads(row["Bearish_Indices"])
                        if indices_list:
                            precomputed["bearish_indices"] = tuple(
                                pd.to_datetime(idx) for idx in indices_list
                            )
                    except Exception:
                        pass

                if not precomputed:
                    precomputed = None  # type: ignore[assignment]

            # Create divergence chart
            fig = plot_price_rsi(
                data,
                ticker=ticker,
                rsi_period=args.rsi_period,
                show_divergence=True,
                divergence_window=args.swing_window,
                divergence_lookback=args.divergence_lookback,
                precomputed_divergence=precomputed,
            )

            output_path = os.path.join(args.output_dir, f"{ticker}_{args.interval}.png")
            fig.savefig(output_path, dpi=150, bbox_inches="tight")
            plt.close(fig)

            print(f"✓ Saved to {output_path}")
            success_count += 1

        except Exception as e:
            print(f"❌ Error: {e}")

    print(
        f"\nCompleted! {success_count}/{len(tickers)} charts saved to {args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main_screen())
