"""Retrospective bull/bear regime segmentation of price history.

Uses aeon time-series segmentation to split a price series into contiguous
regimes, then classifies each regime from its own trend statistics.

WARNING: RETROSPECTIVE ONLY.  The segmenter is fitted once on the entire
series, so every label is hindsight.  The final segment is the least stable:
appending new bars can move or delete the last change point.  These labels are
not a trading signal and could not have been produced in real time.

Boundaries locate shifts in the *return distribution*, not price pivots.
Validation on 33 years of SPY placed a change point 5 days from the February
2020 top but 97 days from the October 2022 bottom, so treat the dates as
approximate.

Public API:
    RETROSPECTIVE_WARNING: str
    SEGMENTATION_METHODS: tuple[str, ...]
    PERIODS_PER_YEAR: dict[str, int]
    build_regime_features(close, vol_window=20, clip_sigma=5.0, scale="zscore")
        -> pd.DataFrame
    detect_regimes(df, price_col="Close", method="ggs", k_max=None,
                   min_segment=21, vol_window=20, lamb=1.0, max_shuffles=250,
                   sideways_band=0.10, periods_per_year=252, scale="zscore",
                   clip_sigma=5.0, random_state=0) -> dict[str, Any]
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "PERIODS_PER_YEAR",
    "RETROSPECTIVE_WARNING",
    "SEGMENTATION_METHODS",
    "build_regime_features",
    "detect_regimes",
]

RETROSPECTIVE_WARNING = (
    "Regime labels are fitted retrospectively on the whole series. The most "
    "recent segment is the least stable - adding new bars can move or remove "
    "the final change point. Not a signal; for research and education only."
)

SEGMENTATION_METHODS: tuple[str, ...] = ("ggs",)

PERIODS_PER_YEAR: dict[str, int] = {"1d": 252, "1wk": 52, "1mo": 12}

_SCALES: tuple[str, ...] = ("zscore", "minmax", "none")

# Methods aeon exposes that cannot work here.  Rejected before any aeon import
# so the message names the missing package rather than an aeon internal.
_UNSUPPORTED_METHODS: dict[str, str] = {
    "clasp": (
        "aeon's ClaSPSegmenter matches repeating subsequence shapes, and "
        "financial returns have no such motif. Measured head-to-head on 10 "
        "years of SPY it matched at best 1 of 6 known market turns against "
        "3 of 4 for the default, and merged the 2022 bear market into a "
        "'sideways' segment. It is univariate, so it also cannot use the "
        "volatility channel."
    ),
    "binseg": (
        "aeon's BinSegmenter requires the optional 'ruptures' package, which "
        "stockcharts does not depend on."
    ),
    "fluss": (
        "aeon's FLUSSSegmenter requires the optional 'stumpy' package, which "
        "stockcharts does not depend on."
    ),
    "hmm": (
        "aeon's HMMSegmenter only performs Viterbi decoding against a "
        "hand-specified emission and transition model; it cannot be fitted "
        "from data, so it cannot label price regimes."
    ),
}


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------


def build_regime_features(
    close: pd.Series,
    vol_window: int = 20,
    clip_sigma: float | None = 5.0,
    scale: str = "zscore",
) -> pd.DataFrame:
    """Build the two-channel feature matrix a Gaussian segmenter needs.

    Channel 0 is the log return, whose per-segment mean is the drift.  Channel
    1 is the log of rolling return volatility, which lets a pure volatility
    shift with no change in drift register as a boundary.

    Both transformations were validated as load-bearing: on 33 years of SPY,
    raw volatility in place of log volatility matched 0 of 4 known market
    turns against 3 of 4 for log volatility, and leaving the channels unscaled
    produced no change points at all, because aeon's ``lamb`` regulariser acts
    on the scale of the covariance entries.

    Args:
        close: Price series indexed by time.
        vol_window: Bars in the rolling volatility window.
        clip_sigma: Clip each channel to this many standard deviations before
            scaling, so one crash day cannot become its own segment.  None
            disables clipping.
        scale: ``"zscore"``, ``"minmax"`` or ``"none"``.

    Returns:
        A frame with ``ret`` and ``vol`` columns and the warm-up rows dropped.
        Returns an empty frame when there is too little usable data.

    Raises:
        ValueError: If ``vol_window`` < 2, ``clip_sigma`` <= 0, or ``scale`` is
            not a recognised option.
    """
    if vol_window < 2:
        raise ValueError(f"vol_window must be >= 2, got {vol_window}")
    if clip_sigma is not None and clip_sigma <= 0:
        raise ValueError(f"clip_sigma must be > 0 or None, got {clip_sigma}")
    if scale not in _SCALES:
        raise ValueError(f"scale must be one of {_SCALES}, got {scale!r}")

    prices = pd.to_numeric(close, errors="coerce").dropna()
    prices = prices[prices > 0]
    if len(prices) < vol_window + 2:
        return pd.DataFrame(columns=["ret", "vol"], dtype="float64")

    returns = np.log(prices).diff()
    vol = returns.rolling(vol_window, min_periods=vol_window).std()
    # A constant stretch gives zero volatility; log(0) is -inf, so drop it.
    vol = np.log(vol.where(vol > 0))

    frame = pd.DataFrame({"ret": returns, "vol": vol}).replace([np.inf, -np.inf], np.nan).dropna()
    if frame.empty:
        return pd.DataFrame(columns=["ret", "vol"], dtype="float64")

    if clip_sigma is not None:
        for column in frame.columns:
            mean, std = frame[column].mean(), frame[column].std()
            if std > 0:
                frame[column] = frame[column].clip(mean - clip_sigma * std, mean + clip_sigma * std)

    if scale == "zscore":
        spread = frame.std().replace(0.0, 1.0)
        frame = (frame - frame.mean()) / spread
    elif scale == "minmax":
        span = (frame.max() - frame.min()).replace(0.0, 1.0)
        frame = (frame - frame.min()) / span

    return frame


# ---------------------------------------------------------------------------
# Segmenters
# ---------------------------------------------------------------------------


def _segment_ggs(
    features: np.ndarray,
    k_max: int,
    lamb: float,
    max_shuffles: int,
    random_state: int,
) -> np.ndarray:
    """Segment a multivariate matrix with aeon's GreedyGaussianSegmenter.

    A fresh segmenter is constructed per call because aeon builds its internal
    ``_GGS`` object in ``__init__``, making instance reuse unsafe.

    Args:
        features: Matrix shaped ``(n_timepoints, n_channels)``.
        k_max: Maximum change points; the segmenter uses its full budget.
        lamb: Covariance regularisation strength.
        max_shuffles: Reordering attempts during change-point adjustment.
        random_state: Seed for those shuffles.

    Returns:
        Per-bar integer segment ids, one per row of ``features``.
    """
    from aeon.segmentation import GreedyGaussianSegmenter

    segmenter = GreedyGaussianSegmenter(
        k_max=k_max,
        lamb=lamb,
        max_shuffles=max_shuffles,
        random_state=random_state,
    )
    return np.asarray(segmenter.fit_predict(features, axis=0), dtype=int)


# ---------------------------------------------------------------------------
# Interval helpers
# ---------------------------------------------------------------------------


def _ids_to_intervals(ids: np.ndarray) -> list[tuple[int, int]]:
    """Convert per-bar segment ids into half-open positional intervals.

    Args:
        ids: Per-bar integer segment ids.

    Returns:
        ``(start, end)`` pairs with ``end`` exclusive, covering every bar.
    """
    if len(ids) == 0:
        return []
    boundaries = [0, *(int(i) + 1 for i in np.flatnonzero(np.diff(ids))), len(ids)]
    return [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]


def _merge_short(
    intervals: list[tuple[int, int]],
    min_segment: int,
) -> list[tuple[int, int]]:
    """Absorb intervals shorter than the minimum into a neighbour.

    The shortest offender is merged into its longer neighbour each pass, ties
    going left, until nothing is too short or only one interval remains.

    Args:
        intervals: Half-open ``(start, end)`` pairs.
        min_segment: Minimum bars an interval may have.

    Returns:
        The merged intervals.
    """
    work = list(intervals)
    while len(work) > 1:
        lengths = [end - start for start, end in work]
        shortest = min(range(len(work)), key=lambda i: (lengths[i], i))
        if lengths[shortest] >= min_segment:
            break
        if shortest == 0:
            target = 1
        elif shortest == len(work) - 1:
            target = shortest - 1
        else:
            left, right = lengths[shortest - 1], lengths[shortest + 1]
            target = shortest - 1 if left >= right else shortest + 1
        low, high = sorted((shortest, target))
        work[low : high + 1] = [(work[low][0], work[high][1])]
    return work


def _slope_annualised(prices: pd.Series, periods_per_year: int) -> tuple[float, float]:
    """Fit a log-price trend and return its annualised slope and t-statistic.

    Args:
        prices: Segment prices.
        periods_per_year: Bars per year, used to annualise.

    Returns:
        ``(slope_annualised, t_stat)``.  Both are 0.0 when the segment is too
        short or flat to fit.
    """
    n = len(prices)
    if n < 3:
        return 0.0, 0.0
    values = np.log(prices.to_numpy(dtype=float))
    x = np.arange(n, dtype=float)
    if not np.isfinite(values).all() or np.ptp(values) == 0.0:
        # np.std accumulates float error on a large constant (~9e-16 for 300
        # identical logs), so an exact std()==0 test never fires; ptp is exact.
        return 0.0, 0.0
    slope, intercept = np.polyfit(x, values, 1)
    residuals = values - (slope * x + intercept)
    dof = n - 2
    resid_std = float(np.sqrt((residuals**2).sum() / dof)) if dof > 0 else 0.0
    x_std = float(x.std())
    if resid_std == 0 or x_std == 0:
        t_stat = 0.0
    else:
        standard_error = resid_std / (x_std * np.sqrt(n))
        t_stat = float(slope / standard_error) if standard_error > 0 else 0.0
    return float(slope) * periods_per_year, t_stat


def _segment_stats(
    close: pd.Series,
    start: int,
    end: int,
    periods_per_year: int,
) -> dict[str, Any]:
    """Compute the descriptive statistics for one segment.

    Args:
        close: Full price series.
        start: Inclusive start position.
        end: Exclusive end position.
        periods_per_year: Bars per year.

    Returns:
        A mapping of segment statistics, excluding the label.
    """
    prices = close.iloc[start:end]
    slope_ann, t_stat = _slope_annualised(prices, periods_per_year)
    returns = np.log(prices).diff().dropna()
    vol_ann = float(returns.std() * np.sqrt(periods_per_year)) if len(returns) > 1 else 0.0
    cum_return = float(prices.iloc[-1] / prices.iloc[0] - 1.0) if len(prices) > 1 else 0.0
    drawdown = float((prices / prices.cummax() - 1.0).min()) if len(prices) else 0.0
    return {
        "start": prices.index[0],
        "end": prices.index[-1],
        "start_pos": int(start),
        "end_pos": int(end),
        "n_bars": int(end - start),
        "cum_return": cum_return,
        "slope_ann": slope_ann,
        "t_stat": t_stat,
        "confidence": float(min(1.0, abs(t_stat) / 3.0)),
        "vol_ann": vol_ann,
        "max_drawdown": drawdown,
    }


def _classify(slope_ann: float, sideways_band: float) -> str:
    """Label a segment from its annualised log-price slope.

    Args:
        slope_ann: Annualised slope of log price.
        sideways_band: Half-width of the dead band around zero.

    Returns:
        ``"bull"``, ``"bear"`` or ``"sideways"``.
    """
    if slope_ann > sideways_band:
        return "bull"
    if slope_ann < -sideways_band:
        return "bear"
    return "sideways"


def _merge_same_label(
    segments: list[dict[str, Any]],
) -> list[tuple[int, int]]:
    """Collapse runs of identically labelled segments into single intervals.

    A Gaussian segmenter routinely splits one long advance into a low- and a
    high-volatility half; for a regime band chart those are one band.

    Args:
        segments: Labelled segments in chronological order.

    Returns:
        Merged half-open ``(start, end)`` pairs.
    """
    if not segments:
        return []
    merged: list[tuple[int, int]] = [(segments[0]["start_pos"], segments[0]["end_pos"])]
    labels = [segments[0]["label"]]
    for segment in segments[1:]:
        if segment["label"] == labels[-1]:
            merged[-1] = (merged[-1][0], segment["end_pos"])
        else:
            merged.append((segment["start_pos"], segment["end_pos"]))
            labels.append(segment["label"])
    return merged


def _build_result(
    close: pd.Series,
    intervals: list[tuple[int, int]],
    index: pd.Index,
    sideways_band: float,
    periods_per_year: int,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the public result from final intervals.

    Args:
        close: Full price series.
        intervals: Final half-open ``(start, end)`` pairs.
        index: Index to reindex the per-bar labels onto.
        sideways_band: Dead-band half-width.
        periods_per_year: Bars per year.
        meta: Metadata to attach, mutated with derived counts.

    Returns:
        The ``detect_regimes`` result mapping.
    """
    segments: list[dict[str, Any]] = []
    for start, end in intervals:
        stats = _segment_stats(close, start, end, periods_per_year)
        stats["label"] = _classify(stats["slope_ann"], sideways_band)
        stats["provisional"] = False
        segments.append(stats)
    if segments:
        segments[-1]["provisional"] = True

    labels = pd.Series(pd.NA, index=close.index, dtype=object)
    for segment in segments:
        labels.iloc[segment["start_pos"] : segment["end_pos"]] = segment["label"]
    labels = labels.reindex(index).bfill().ffill()

    pivots: list[dict[str, Any]] = []
    for earlier, later in zip(segments, segments[1:], strict=False):
        pivots.append(
            {
                "date": later["start"],
                "pos": later["start_pos"],
                "from": earlier["label"],
                "to": later["label"],
                "price": float(close.iloc[later["start_pos"]]),
            }
        )

    meta["n_segments"] = len(segments)
    meta["retrospective"] = True
    meta["warning"] = RETROSPECTIVE_WARNING
    return {
        "segments": segments,
        "labels": labels,
        "pivots": pivots,
        "current": segments[-1]["label"] if segments else "insufficient-data",
        "meta": meta,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def detect_regimes(
    df: pd.DataFrame,
    price_col: str = "Close",
    method: str = "ggs",
    k_max: int | None = None,
    min_segment: int = 21,
    vol_window: int = 20,
    lamb: float = 1.0,
    max_shuffles: int = 250,
    sideways_band: float = 0.10,
    periods_per_year: int = 252,
    scale: str = "zscore",
    clip_sigma: float | None = 5.0,
    random_state: int = 0,
) -> dict[str, Any]:
    """Split a price series into bull, bear and sideways regimes.

    Warning:
        Retrospective only.  The segmenter sees the whole series, so labels are
        hindsight and the final segment can move or vanish as bars arrive.  See
        :data:`RETROSPECTIVE_WARNING`.

    Args:
        df: Frame containing ``price_col``, indexed by time.
        price_col: Column holding prices.
        method: Segmentation algorithm; only ``"ggs"`` is supported.
        k_max: Maximum change points to search for.  None auto-scales as
            ``max(2, min(40, max(12, n // 120)))`` -- about one per 120
            bars, floored at 12 so short windows keep enough resolution.
        min_segment: Minimum bars per regime; shorter ones are merged away.
        vol_window: Rolling volatility window for the second feature channel.
        lamb: Covariance regularisation passed to the segmenter.
        max_shuffles: Reordering attempts during change-point adjustment.
        sideways_band: Annualised slope within +/- this is labelled sideways.
        periods_per_year: Bars per year, for annualising.
        scale: Feature scaling, ``"zscore"``, ``"minmax"`` or ``"none"``.
        clip_sigma: Standard deviations at which to clip features, or None.
        random_state: Seed for the segmenter's shuffles.

    Returns:
        A mapping with ``segments``, ``labels``, ``pivots``, ``current`` and
        ``meta``.  Degenerate input yields a single segment rather than raising.

    Raises:
        ValueError: If a parameter is out of range, ``price_col`` is absent, or
            ``method`` is unknown or unsupported.
    """
    if price_col not in df.columns:
        raise ValueError(f"price_col {price_col!r} not in columns: {list(df.columns)}")
    if method in _UNSUPPORTED_METHODS:
        raise ValueError(
            f"{_UNSUPPORTED_METHODS[method]} " f"Use method='ggs', the only supported option."
        )
    if method not in SEGMENTATION_METHODS:
        raise ValueError(f"method must be one of {SEGMENTATION_METHODS}, got {method!r}")
    if min_segment < 2:
        raise ValueError(f"min_segment must be >= 2, got {min_segment}")
    if k_max is not None and k_max < 1:
        raise ValueError(f"k_max must be >= 1 or None, got {k_max}")
    if lamb < 0:
        raise ValueError(f"lamb must be >= 0, got {lamb}")
    if max_shuffles < 1:
        raise ValueError(f"max_shuffles must be >= 1, got {max_shuffles}")
    if sideways_band < 0:
        raise ValueError(f"sideways_band must be >= 0, got {sideways_band}")
    if periods_per_year < 1:
        raise ValueError(f"periods_per_year must be >= 1, got {periods_per_year}")

    close = pd.to_numeric(df[price_col], errors="coerce")
    # Prices <= 0 cannot be log-transformed; drop them before any fitting so
    # the slope helper never sees a -inf.
    close = close.where(close > 0)
    meta: dict[str, Any] = {
        "method": method,
        "n_bars": int(len(close)),
        "min_segment": min_segment,
        "vol_window": vol_window,
        "lamb": lamb,
        "max_shuffles": max_shuffles,
        "sideways_band": sideways_band,
        "periods_per_year": periods_per_year,
        "scale": scale,
        "clip_sigma": clip_sigma,
        "random_state": random_state,
        "warmup_bars": vol_window,
        "insufficient_data": False,
        "k_max": k_max,
    }

    usable = close.dropna()
    if usable.empty:
        meta.update({"insufficient_data": True, "k_max": 0, "method": "empty"})
        return {
            "segments": [],
            "labels": pd.Series(pd.NA, index=df.index, dtype=object),
            "pivots": [],
            "current": "insufficient-data",
            "meta": meta,
        }

    # Too little history to support two regimes: report one honest segment.
    if len(usable) < max(2 * min_segment, vol_window + min_segment):
        meta.update({"insufficient_data": True, "method": "fallback-single-segment"})
        return _build_result(
            usable, [(0, len(usable))], df.index, sideways_band, periods_per_year, meta
        )

    features = build_regime_features(
        usable, vol_window=vol_window, clip_sigma=clip_sigma, scale=scale
    )
    if features.empty or len(features) < 2 * min_segment:
        meta.update({"insufficient_data": True, "method": "fallback-single-segment"})
        return _build_result(
            usable, [(0, len(usable))], df.index, sideways_band, periods_per_year, meta
        )

    # One change point per ~120 bars, floored at 12 and capped at 40.
    #
    # The cap matters: a flat 12 saturated immediately, so a 33-year window
    # got the same budget as a 5-year one and averaged whole bear markets
    # away (the Feb 2020 top sat 709 days from the nearest pivot at k_max=12,
    # and 5 days at k_max=20).
    #
    # The floor matters just as much: without it a 5-year window drops to 10
    # and loses short events entirely (the April 2025 selloff moved from 2
    # days to 724 days away). Short windows need a budget that is generous
    # relative to their length, not proportional to it.
    resolved_k = k_max if k_max is not None else max(2, min(40, max(12, len(features) // 120)))
    meta["k_max"] = resolved_k

    ids = _segment_ggs(features.to_numpy(dtype=float), resolved_k, lamb, max_shuffles, random_state)

    # Features start vol_window bars in; map ids back onto the price positions.
    offset = usable.index.get_indexer(features.index[:1])[0]
    full_ids = np.zeros(len(usable), dtype=int)
    full_ids[offset : offset + len(ids)] = ids
    full_ids[:offset] = ids[0] if len(ids) else 0

    intervals = _merge_short(_ids_to_intervals(full_ids), min_segment)

    # Label once, collapse neighbours that agree, then recompute every statistic
    # on the bands actually drawn so the printed table matches the chart.
    provisional = []
    for start, end in intervals:
        stats = _segment_stats(usable, start, end, periods_per_year)
        stats["label"] = _classify(stats["slope_ann"], sideways_band)
        provisional.append(stats)
    final = _merge_same_label(provisional)

    return _build_result(usable, final, df.index, sideways_band, periods_per_year, meta)
