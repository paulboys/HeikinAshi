"""Beta and relative strength regime analysis module.

Implements Mike McGlone's approach to regime detection:
- Relative strength ratio (asset/benchmark) vs its moving average
- Rolling beta calculation using covariance/variance
- Regime signal: "risk-on" when ratio above MA, "risk-off" when below

Public API:
    compute_rolling_beta(asset_returns, benchmark_returns, window=60) -> pd.Series
    compute_relative_strength(asset_close, benchmark_close) -> pd.Series
    compute_regime_signal(ratio, ma_period=200) -> dict
    analyze_beta_regime(asset_df, benchmark_df, ma_period=200, beta_window=60) -> dict
"""

from __future__ import annotations

import pandas as pd

__all__ = [
    "compute_rolling_beta",
    "compute_relative_strength",
    "compute_regime_signal",
    "analyze_beta_regime",
]


def compute_rolling_beta(
    asset_returns: pd.Series,
    benchmark_returns: pd.Series,
    window: int = 60,
) -> pd.Series:
    """Compute rolling beta of asset relative to benchmark.

    Beta = Cov(asset_returns, benchmark_returns) / Var(benchmark_returns)

    Args:
        asset_returns: Series of asset percentage returns.
        benchmark_returns: Series of benchmark percentage returns.
        window: Rolling window size for beta calculation (default: 60 periods).

    Returns:
        Series of rolling beta values. NaN where insufficient history.

    Raises:
        ValueError: If window < 2.
    """
    if window < 2:
        raise ValueError("window must be >= 2")

    # Align the series by index
    aligned = pd.DataFrame(
        {
            "asset": asset_returns,
            "benchmark": benchmark_returns,
        }
    ).dropna()

    if len(aligned) < window:
        return pd.Series([float("nan")] * len(asset_returns), index=asset_returns.index)

    # Rolling covariance and variance
    rolling_cov = aligned["asset"].rolling(window=window).cov(aligned["benchmark"])
    rolling_var = aligned["benchmark"].rolling(window=window).var()

    # Beta = Cov / Var
    beta = rolling_cov / rolling_var

    # Reindex to original asset index
    return beta.reindex(asset_returns.index)


def compute_relative_strength(
    asset_close: pd.Series,
    benchmark_close: pd.Series,
) -> pd.Series:
    """Compute relative strength ratio of asset vs benchmark.

    Relative Strength = Asset Price / Benchmark Price

    This ratio shows whether the asset is outperforming (rising ratio)
    or underperforming (falling ratio) the benchmark.

    Args:
        asset_close: Series of asset closing prices.
        benchmark_close: Series of benchmark closing prices.

    Returns:
        Series of relative strength ratios.
    """
    # Align by index
    aligned = pd.DataFrame(
        {
            "asset": asset_close,
            "benchmark": benchmark_close,
        }
    ).dropna()

    if aligned.empty:
        return pd.Series(dtype=float)

    ratio = aligned["asset"] / aligned["benchmark"]
    return ratio


def compute_regime_signal(
    ratio: pd.Series,
    ma_period: int = 200,
) -> dict:
    """Determine regime signal based on ratio vs its moving average.

    Args:
        ratio: Series of relative strength ratios.
        ma_period: Moving average period for regime detection (default: 200).

    Returns:
        dict with keys:
            - 'ratio': current ratio value
            - 'ma': current moving average value
            - 'regime': "risk-on" if ratio > ma, "risk-off" if ratio <= ma
            - 'pct_from_ma': percentage distance from MA
            - 'ratio_series': full ratio series
            - 'ma_series': full MA series
    """
    if len(ratio) < ma_period:
        return {
            "ratio": float("nan"),
            "ma": float("nan"),
            "regime": "insufficient-data",
            "pct_from_ma": float("nan"),
            "ratio_series": ratio,
            "ma_series": pd.Series(dtype=float),
        }

    ma_series = ratio.rolling(window=ma_period).mean()

    current_ratio = ratio.iloc[-1]
    current_ma = ma_series.iloc[-1]

    if pd.isna(current_ratio) or pd.isna(current_ma):
        regime = "insufficient-data"
        pct_from_ma = float("nan")
    else:
        regime = "risk-on" if current_ratio > current_ma else "risk-off"
        pct_from_ma = ((current_ratio - current_ma) / current_ma) * 100

    return {
        "ratio": current_ratio,
        "ma": current_ma,
        "regime": regime,
        "pct_from_ma": pct_from_ma,
        "ratio_series": ratio,
        "ma_series": ma_series,
    }


def analyze_beta_regime(
    asset_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    ma_period: int = 200,
    beta_window: int = 60,
) -> dict:
    """Complete beta regime analysis for an asset vs benchmark.

    Combines relative strength ratio, regime signal, and rolling beta.

    Args:
        asset_df: DataFrame with 'Close' column for the asset.
        benchmark_df: DataFrame with 'Close' column for the benchmark.
        ma_period: Moving average period for regime detection (default: 200).
        beta_window: Rolling window for beta calculation (default: 60).

    Returns:
        dict with keys:
            - 'relative_strength': current RS ratio
            - 'rs_ma': RS moving average value
            - 'regime': "risk-on" or "risk-off"
            - 'pct_from_ma': percentage distance from MA
            - 'rolling_beta': current rolling beta value
            - 'asset_price': current asset price
            - 'benchmark_price': current benchmark price
            - 'rs_series': full RS ratio series
            - 'rs_ma_series': full RS MA series
            - 'beta_series': full rolling beta series
    """
    # Extract close prices
    asset_close = asset_df["Close"]
    benchmark_close = benchmark_df["Close"]

    # Compute relative strength
    rs_ratio = compute_relative_strength(asset_close, benchmark_close)

    # Compute regime signal
    regime_result = compute_regime_signal(rs_ratio, ma_period=ma_period)

    # Compute returns for beta calculation
    asset_returns = asset_close.pct_change()
    benchmark_returns = benchmark_close.pct_change()

    # Compute rolling beta
    beta_series = compute_rolling_beta(asset_returns, benchmark_returns, window=beta_window)
    current_beta = beta_series.iloc[-1] if len(beta_series) > 0 else float("nan")

    return {
        "relative_strength": regime_result["ratio"],
        "rs_ma": regime_result["ma"],
        "regime": regime_result["regime"],
        "pct_from_ma": regime_result["pct_from_ma"],
        "rolling_beta": current_beta,
        "asset_price": asset_close.iloc[-1] if len(asset_close) > 0 else float("nan"),
        "benchmark_price": benchmark_close.iloc[-1] if len(benchmark_close) > 0 else float("nan"),
        "rs_series": regime_result["ratio_series"],
        "rs_ma_series": regime_result["ma_series"],
        "beta_series": beta_series,
    }
