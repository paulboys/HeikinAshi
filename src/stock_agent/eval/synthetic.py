"""Deterministic synthetic price history with planted features.

Scenarios must be reproducible bit for bit, so every series comes from a
seeded generator rather than the global random state. Where a scenario
depends on a feature being present -- an extended run, a deep drawdown -- the
planter verifies it against the real stockcharts function before returning,
because a routing benchmark whose features are not actually detectable is
quietly measuring nothing.

Public API:
    synth_ohlc(n, seed, ...) -> pd.DataFrame
    plant_run(df, length, colour) -> pd.DataFrame
    verify_run(df) -> tuple[int, str]
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

__all__ = [
    "plant_divergence",
    "plant_momentum_push",
    "plant_run",
    "plant_volume_surge",
    "synth_ohlc",
    "synth_vix",
    "verify_divergence",
    "verify_regime_change",
    "verify_rsi",
    "verify_relative_strength",
    "verify_run",
    "verify_volatility_ratio",
    "verify_volume_surge",
]

_TRADING_DAYS = 252


def synth_ohlc(
    n: int,
    seed: int,
    start: str = "2020-01-02",
    drift_ann: float = 0.0,
    vol_ann: float = 0.20,
    s0: float = 100.0,
    segments: Sequence[tuple[int, float, float]] = (),
    volume_base: float = 2_000_000.0,
    volume_multipliers: Sequence[tuple[int, int, float]] = (),
    intrabar_range: float = 0.01,
) -> pd.DataFrame:
    """Generate reproducible OHLC bars.

    Args:
        n: Bars to generate, when no segments are given.
        seed: Seed for the generator; the same seed always gives the same
            series, on any platform.
        start: First business day.
        drift_ann: Annualised drift, when no segments are given.
        vol_ann: Annualised volatility, when no segments are given.
        s0: Starting price.
        segments: ``(bars, drift_ann, vol_ann)`` triples, so a regime change
            can be planted exactly rather than hoped for.
        volume_base: Typical volume.
        volume_multipliers: ``(start, end, multiplier)`` windows, for planting
            a volume event.
        intrabar_range: Fractional high/low spread around each close.

    Returns:
        A frame with exactly the OHLC columns on a business-day index.
    """
    rng = np.random.default_rng(seed)

    if segments:
        pieces: list[np.ndarray] = []
        for bars, seg_drift, seg_vol in segments:
            mu = seg_drift / _TRADING_DAYS
            sigma = seg_vol / np.sqrt(_TRADING_DAYS)
            pieces.append(rng.normal(mu, sigma, bars))
        returns = np.concatenate(pieces)
    else:
        mu = drift_ann / _TRADING_DAYS
        sigma = vol_ann / np.sqrt(_TRADING_DAYS)
        returns = rng.normal(mu, sigma, n)

    total = len(returns)
    close = s0 * np.exp(np.cumsum(returns))
    prev = np.concatenate([[s0], close[:-1]])

    high_frac = rng.uniform(0.0, intrabar_range, total)
    low_frac = rng.uniform(0.0, intrabar_range, total)
    high = np.maximum(close, prev) * (1.0 + high_frac)
    low = np.minimum(close, prev) * (1.0 - low_frac)

    volume = rng.lognormal(np.log(volume_base), 0.3, total)
    for begin, finish, multiplier in volume_multipliers:
        volume[begin:finish] *= multiplier

    return pd.DataFrame(
        {
            "Open": prev,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume.astype(np.int64),
        },
        index=pd.bdate_range(start=start, periods=total),
    )


def verify_run(df: pd.DataFrame) -> tuple[int, str]:
    """Measure the current Heiken Ashi run using the real implementation.

    Args:
        df: Price bars.

    Returns:
        The run length and its colour.
    """
    from stockcharts.charts.heiken_ashi import heiken_ashi
    from stockcharts.indicators.heiken_runs import compute_ha_run_stats

    stats = compute_ha_run_stats(heiken_ashi(df))
    return int(stats["run_length"]), str(stats["run_color"])


def plant_run(df: pd.DataFrame, length: int, colour: str = "green") -> pd.DataFrame:
    """Force an extended Heiken Ashi run at the end of a series.

    Heiken Ashi smooths across bars, so a run cannot be written directly; the
    closes are nudged until the real implementation reports the run, and the
    result is verified before it is returned.

    Args:
        df: Price bars to modify.
        length: Run length to plant.
        colour: ``"green"`` or ``"red"``.

    Returns:
        The modified bars.

    Raises:
        ValueError: If the planted run cannot be produced, which would make
            any scenario built on it meaningless.
    """
    out = df.copy()
    step = 0.012 if colour == "green" else -0.012
    tail = min(length + 6, len(out) - 1)

    closes = out["Close"].to_numpy(dtype=float).copy()
    anchor = closes[-tail - 1]
    for offset in range(tail):
        anchor *= 1.0 + step
        closes[-tail + offset] = anchor
    out["Close"] = closes
    out["Open"] = np.concatenate([[closes[0]], closes[:-1]])
    out["High"] = np.maximum(out["Close"], out["Open"]) * 1.004
    out["Low"] = np.minimum(out["Close"], out["Open"]) * 0.996

    found, found_colour = verify_run(out)
    if found < length or found_colour != colour:
        raise ValueError(
            f"planted a {length}-bar {colour} run but the detector reports "
            f"{found} {found_colour}; the scenario would not test what it claims"
        )
    return out


def synth_vix(
    df: pd.DataFrame,
    window: int = 20,
    floor: float = 9.5,
    premium: float = 1.15,
) -> pd.DataFrame:
    """Derive a plausible volatility index from a price series.

    A volatility index is not an independent random walk: it tracks realised
    volatility with a premium and does not wander to absurd levels. Generating
    it as its own geometric series produced readings near 5, which no real
    index reaches -- and which made the contrarian analyses untestable, since
    they key off absolute levels.

    Args:
        df: Price history to derive volatility from.
        window: Bars in the realised-volatility estimate.
        floor: Lowest level the index may print.
        premium: Multiplier applied to realised volatility, standing in for
            the implied-over-realised premium.

    Returns:
        An OHLC frame on the same index whose Close is the index level.
    """
    close = df["Close"].astype(float)
    log_close = pd.Series(np.log(close.to_numpy()), index=close.index)
    realised = (
        log_close.diff().rolling(window, min_periods=2).std() * np.sqrt(_TRADING_DAYS) * 100.0
    )
    level = (realised * premium).bfill().clip(lower=floor)

    # Daily ranges on a volatility index are wide; a flat fraction of the
    # level is enough for the tools that read it, none of which use the range.
    span = level * 0.04
    return pd.DataFrame(
        {
            "Open": level.shift(1).fillna(level),
            "High": level + span,
            "Low": (level - span).clip(lower=floor),
            "Close": level,
            "Volume": np.zeros(len(level)),
        },
        index=df.index,
    )


# --- RSI divergence ---------------------------------------------------------

# The detector looks back 60 bars, needs a bar strictly lower than the five on
# either side to call a swing, and will not call one within five bars of the
# edge. Both troughs therefore have to sit inside a 60-bar tail, be built from
# strictly monotonic legs, and keep clear of the end. A noisy close defeats the
# strictness, so the noise goes into the high and low instead.
_DIVERGENCE_SPAN = 60


def _divergence_path(level: float, sharp_drop: float, second_lower: float) -> np.ndarray:
    """Build the two-trough close path a bullish divergence needs.

    The first trough is reached by a short, steep fall, which drives RSI very
    low. The second is lower in price but reached by a long, shallow drift,
    which leaves RSI higher -- that gap is the divergence.

    Args:
        level: Starting price.
        sharp_drop: Fractional fall into the first trough.
        second_lower: How much further below the first trough the second sits.

    Returns:
        Exactly ``_DIVERGENCE_SPAN`` closes.
    """
    path = [level] * 8
    for _ in range(7):
        path.append(path[-1] * (1 - sharp_drop / 7))
    first_trough = path[-1]
    for _ in range(7):
        path.append(path[-1] * (1 + sharp_drop / 9))
    for _ in range(7):
        path.append(path[-1] * (1 - 0.001))

    target = first_trough * (1 - second_lower)
    start, steps = path[-1], 16
    for i in range(steps):
        path.append(start + (target - start) * ((i + 1) / steps))
    for _ in range(7):
        path.append(path[-1] * (1 + 0.010))
    while len(path) < _DIVERGENCE_SPAN:
        path.append(path[-1] * (1 + 0.001))
    return np.asarray(path[:_DIVERGENCE_SPAN], dtype=float)


def plant_divergence(
    df: pd.DataFrame,
    sharp_drop: float = 0.16,
    second_lower: float = 0.02,
    seed: int = 0,
) -> pd.DataFrame:
    """Write a bullish RSI divergence into the end of a series.

    Args:
        df: Base history; needs at least ``_DIVERGENCE_SPAN`` bars.
        sharp_drop: Fractional fall into the first trough.
        second_lower: How far below the first trough the second one sits.
        seed: Seed for the intrabar range.

    Returns:
        A new frame carrying the divergence.

    Raises:
        ValueError: If the series is too short to hold the shape.
    """
    if len(df) < _DIVERGENCE_SPAN:
        raise ValueError(
            f"need at least {_DIVERGENCE_SPAN} bars to plant a divergence, " f"got {len(df)}"
        )
    out = df.copy()
    close = out["Close"].to_numpy(dtype=float)
    cut = len(close) - _DIVERGENCE_SPAN
    close[cut:] = _divergence_path(float(close[cut]), sharp_drop, second_lower)

    rng = np.random.default_rng(seed)
    wiggle = np.abs(rng.normal(0.0, 0.003, len(close))) + 0.002
    out["Close"] = close
    out["High"] = close * (1 + wiggle)
    out["Low"] = close * (1 - wiggle)
    out["Open"] = np.concatenate([[close[0]], close[:-1]])
    return out


def verify_divergence(df: pd.DataFrame) -> tuple[bool, str]:
    """Ask the real detector whether a divergence is present.

    Without this, a routing benchmark can quietly be measuring nothing: a
    scenario labelled "divergence present" whose detector never fires makes
    every arm look equally and identically wrong.

    Args:
        df: History to test.

    Returns:
        Whether a divergence fires, and what the detector said.
    """
    from stockcharts.indicators.divergence import detect_divergence
    from stockcharts.indicators.rsi import compute_rsi

    enriched = df.copy()
    enriched["RSI"] = compute_rsi(enriched["Close"])
    enriched = enriched.dropna(subset=["RSI"])
    found = detect_divergence(enriched)
    fired = bool(found["bullish"] or found["bearish"])
    detail = str(found["bullish_details"] or found["bearish_details"] or "none")
    return fired, f"{found['last_signal']}: {detail}"


# --- volume -----------------------------------------------------------------


def plant_volume_surge(
    df: pd.DataFrame,
    multiple: float = 6.0,
    bars: int = 5,
) -> pd.DataFrame:
    """Multiply volume over the final bars.

    Args:
        df: Base history.
        multiple: Factor applied to the recent bars' volume.
        bars: How many final bars to lift.

    Returns:
        A new frame with the surge.
    """
    out = df.copy()
    volume = out["Volume"].to_numpy(dtype=float)
    volume[-bars:] = volume[-bars:] * multiple
    out["Volume"] = volume
    return out


def verify_volume_surge(df: pd.DataFrame, window: int = 5, baseline: int = 60) -> float:
    """Measure the volume ratio the way the agent's own tool does.

    Args:
        df: History to test.
        window: Recent bars averaged.
        baseline: Prior bars taken as the median.

    Returns:
        Recent mean over prior median, or zero when there is too little data.
    """
    volume = df["Volume"].dropna()
    if len(volume) < baseline + window:
        return 0.0
    prior = float(volume.iloc[-(baseline + window) : -window].median())
    if prior <= 0:
        return 0.0
    return float(volume.tail(window).mean()) / prior


# --- volatility, regime and relative strength -------------------------------


def verify_volatility_ratio(df: pd.DataFrame, window: int = 20) -> float:
    """Measure recent realised volatility against the full window.

    Args:
        df: History to test.
        window: Bars in the recent estimate.

    Returns:
        Recent annualised volatility divided by the full-period figure.
    """
    close = df["Close"].dropna().astype(float)
    log_close = pd.Series(np.log(close.to_numpy()), index=close.index, dtype=float)
    returns = log_close.diff().dropna().to_numpy(dtype=float)
    full = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    if full <= 0:
        return 1.0
    recent = returns[-window:]
    if len(recent) < 2:
        return 1.0
    return float(np.std(recent, ddof=1)) / full


def verify_regime_change(df: pd.DataFrame, max_shuffles: int = 40) -> tuple[int, str]:
    """Ask the real segmenter how many regime changes it finds.

    Args:
        df: History to test.
        max_shuffles: Permutations in the segmenter's test, lowered from the
            production default to keep a scenario check quick.

    Returns:
        The number of regime changes found, and the current label.
    """
    from stockcharts.indicators.segmentation import detect_regimes

    found = detect_regimes(df, max_shuffles=max_shuffles)
    return len(found.get("pivots") or []), str(found.get("current", "unknown"))


def verify_relative_strength(asset: pd.DataFrame, benchmark: pd.DataFrame) -> str:
    """Ask the real analysis which side of the benchmark a series sits on.

    Args:
        asset: The ticker's history.
        benchmark: The benchmark's history.

    Returns:
        The regime label: ``risk-on``, ``risk-off`` or ``insufficient-data``.
    """
    from stockcharts.indicators.beta import analyze_beta_regime

    return str(analyze_beta_regime(asset, benchmark).get("regime", "insufficient-data"))


# --- momentum ---------------------------------------------------------------


def plant_momentum_push(
    df: pd.DataFrame,
    bars: int = 5,
    pct: float = -0.03,
) -> pd.DataFrame:
    """Drive RSI to an extreme with a short, sharp move.

    Deliberately short. A longer or upward push also produces an extended
    Heiken Ashi run, because that indicator smooths across bars and carries
    the preceding trend -- which would plant two features at once and stop a
    minimal pair being minimal. Five bars downward moves RSI without moving
    the run length past its threshold.

    Args:
        df: Base history.
        bars: Final bars to overwrite.
        pct: Per-bar fractional move; negative drives RSI down.

    Returns:
        A new frame with the push.
    """
    out = df.copy()
    close = out["Close"].to_numpy(dtype=float)
    anchor = float(close[len(close) - bars - 1])
    for i in range(bars):
        close[len(close) - bars + i] = anchor * (1.0 + pct) ** (i + 1)
    out["Close"] = close
    out["High"] = close * 1.004
    out["Low"] = close * 0.996
    out["Open"] = np.concatenate([[close[0]], close[:-1]])
    return out


def verify_rsi(df: pd.DataFrame, period: int = 14) -> float:
    """Measure the latest RSI with the production implementation.

    Args:
        df: History to test.
        period: RSI period.

    Returns:
        The final RSI reading, or 50.0 when it cannot be computed.
    """
    from stockcharts.indicators.rsi import compute_rsi

    rsi = compute_rsi(df["Close"], period=period).dropna()
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0
