"""Visualize Heiken Ashi run statistics from screening results.

This script loads a CSV produced by stockcharts-screen, applies optional volume
and price filters, and generates multiple visualizations:
- Run percentile histogram
- Color-split percentile distributions
- Top N extreme runs table
- Summary statistics

Usage:
    python examples/visualize_ha_runs.py --input results/ha_runs_top98_all_time.csv

Optional filters:
    python examples/visualize_ha_runs.py \
        --input results/ha_runs_top98_all_time.csv \
        --min-volume 500000 \
        --min-price 5.0 \
        --top 50
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import MaxNLocator


def load_and_filter(
    csv_path: str,
    min_volume: float | None = None,
    min_price: float | None = None,
    min_data_years: float | None = None,
) -> pd.DataFrame:
    """Load screening CSV and apply optional filters."""
    df = pd.read_csv(csv_path)

    initial_count = len(df)
    print(f"Loaded {initial_count} results from {csv_path}")

    if min_volume is not None:
        df = df[df["avg_volume"] >= min_volume]
        print(f"  After volume >= {min_volume:,.0f}: {len(df)} results")

    if min_price is not None:
        df = df[df["ha_close"] >= min_price]
        print(f"  After price >= ${min_price:.2f}: {len(df)} results")

    if min_data_years is not None:
        # Convert last_date to datetime and check age
        df["last_date"] = pd.to_datetime(df["last_date"])
        # Simple heuristic: filter stale data (older than 30 days)
        # Note: This doesn't verify full historical depth; use --start/--end in screening for that
        recent_cutoff = pd.Timestamp.now() - pd.DateOffset(days=30)
        df = df[df["last_date"] >= recent_cutoff]
        print(f"  After data recency (within 30 days): {len(df)} results")
        print(
            f"  Note: Use --start/--end with {min_data_years}-year range in screening for accurate data age filter"
        )

    if len(df) == 0:
        print("  WARNING: No results after filtering!")

    return df


def plot_percentile_histogram(df: pd.DataFrame, output_dir: Path) -> None:
    """Generate histogram of run percentiles."""
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(df["run_percentile"], bins=20, color="steelblue", edgecolor="white", alpha=0.8)
    ax.set_xlabel("Run Percentile (%)", fontsize=12)
    ax.set_ylabel("Count", fontsize=12)
    ax.set_title(
        f"Heiken Ashi Run Percentile Distribution (n={len(df)})", fontsize=14, fontweight="bold"
    )
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    out_path = output_dir / "ha_percentile_histogram.png"
    plt.savefig(out_path, dpi=150)
    print(f"  Saved: {out_path}")
    plt.close()


def plot_color_split(df: pd.DataFrame, output_dir: Path) -> None:
    """Generate side-by-side histograms for green vs red runs."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)

    for ax, (color, title, hist_color) in zip(
        axes,
        [
            ("green", "Green Runs", "seagreen"),
            ("red", "Red Runs", "indianred"),
        ],
        strict=False,
    ):
        subset = df[df["color"] == color]
        ax.hist(subset["run_percentile"], bins=20, color=hist_color, edgecolor="white", alpha=0.8)
        ax.set_xlabel("Run Percentile (%)", fontsize=11)
        ax.set_ylabel("Count", fontsize=11)
        ax.set_title(f"{title} (n={len(subset)})", fontsize=12, fontweight="bold")
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax.grid(axis="y", alpha=0.3)

    plt.suptitle("Run Percentile by Color", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()

    out_path = output_dir / "ha_percentile_by_color.png"
    plt.savefig(out_path, dpi=150)
    print(f"  Saved: {out_path}")
    plt.close()


def print_top_runs(df: pd.DataFrame, top_n: int = 50) -> None:
    """Print table of top N runs by percentile."""
    print(f"\nTop {top_n} Extreme Runs (by percentile):")
    print("=" * 80)

    top = df.nlargest(top_n, "run_percentile")[
        ["ticker", "color", "run_length", "run_percentile", "avg_volume", "ha_close"]
    ]

    # Format nicely
    top_formatted = top.copy()
    top_formatted["avg_volume"] = top_formatted["avg_volume"].apply(lambda x: f"{x:,.0f}")
    top_formatted["ha_close"] = top_formatted["ha_close"].apply(lambda x: f"${x:.2f}")
    top_formatted["run_percentile"] = top_formatted["run_percentile"].apply(lambda x: f"{x:.1f}%")

    print(top_formatted.to_string(index=False))
    print("=" * 80)


def print_summary_stats(df: pd.DataFrame) -> None:
    """Print summary statistics for run metrics."""
    print("\nSummary Statistics:")
    print("=" * 80)
    print(df[["run_length", "run_percentile", "avg_volume", "ha_close"]].describe())
    print("=" * 80)

    print("\nColor distribution:")
    print(df["color"].value_counts())
    print()


def main() -> int:
    """Entry point for visualization script."""
    parser = argparse.ArgumentParser(
        description="Visualize Heiken Ashi run statistics from screening results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic visualization
  python examples/visualize_ha_runs.py --input results/ha_runs_top98_all_time.csv

  # Apply volume and price filters
  python examples/visualize_ha_runs.py \\
      --input results/ha_runs_top98_all_time.csv \\
      --min-volume 500000 \\
      --min-price 5.0

  # Show top 30 and save charts to custom directory
  python examples/visualize_ha_runs.py \\
      --input results/ha_runs_top98_all_time.csv \\
      --top 30 \\
      --output-dir charts/analysis
        """,
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to CSV file from stockcharts-screen",
    )

    parser.add_argument(
        "--min-volume",
        type=float,
        default=None,
        help="Minimum average daily volume filter (e.g., 500000)",
    )

    parser.add_argument(
        "--min-price",
        type=float,
        default=None,
        help="Minimum stock price filter (e.g., 5.0)",
    )

    parser.add_argument(
        "--min-data-years",
        type=float,
        default=None,
        help="Require data recency (filter stale tickers); note: use --start/--end in screening for precise data age",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=50,
        help="Number of top runs to display in table (default: 50)",
    )

    parser.add_argument(
        "--output-dir",
        default="charts/analysis",
        help="Directory to save visualizations (default: charts/analysis)",
    )

    args = parser.parse_args()

    # Load and filter data
    df = load_and_filter(args.input, args.min_volume, args.min_price, args.min_data_years)

    if df.empty:
        print("\nNo data to visualize after filtering.")
        return 1

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nGenerating visualizations in {output_dir}...")

    # Generate visualizations
    plot_percentile_histogram(df, output_dir)
    plot_color_split(df, output_dir)

    # Print tables and stats
    print_top_runs(df, args.top)
    print_summary_stats(df)

    print(f"\n✓ Visualizations saved to {output_dir}/")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
