"""Example script demonstrating the price/RSI divergence plotting module."""

from stockcharts.charts.divergence import plot_price_rsi
from stockcharts.data.fetch import fetch_ohlc


def main() -> None:
    """Demonstrate divergence chart plotting for a single ticker."""
    # Example ticker with known divergences
    ticker = "AAPL"

    print(f"Fetching data for {ticker}...")
    df = fetch_ohlc(ticker, interval="1d", lookback="6mo")

    print("Creating divergence chart...")
    fig = plot_price_rsi(
        df,
        ticker=ticker,
        rsi_period=14,
        show_divergence=True,
        divergence_window=5,
        divergence_lookback=120,  # Look back 120 bars for divergences
        figsize=(14, 10),
        overbought=70,
        oversold=30,
    )

    # Save the chart
    output_path = f"charts/{ticker}_divergence.png"
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Chart saved to: {output_path}")

    # Optionally display the chart
    # plt.show()


if __name__ == "__main__":
    main()
