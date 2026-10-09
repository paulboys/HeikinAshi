"""Wrappers over the analyses stockcharts already implements.

Each wrapper does three things and no more: obtain data through the
chokepoint, call an existing library function, and reduce the result to
scalars plus a one-line rendering. No wrapper computes an indicator itself
except where noted, and none formats prose -- the decision model reasons over
measurements, and the report renders them.

Public API:
    build_registry(include_absent: bool = True) -> ToolRegistry
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from stock_agent.conditions import Condition
from stock_agent.registry import (
    ToolContext,
    ToolCost,
    ToolRegistry,
    ToolResult,
    ToolSpec,
)
from stock_agent.state import JsonValue, summarize_frame
from stock_agent.tools.absent import absent_specs
from stock_agent.tools.analysis import analysis_specs
from stock_agent.tools.coerce import whole

__all__ = ["build_registry"]

Metrics = dict[str, JsonValue]


def _num(mapping: dict[str, JsonValue], key: str, default: float = 0.0) -> float:
    """Read a number out of a JSON-safe mapping.

    Args:
        mapping: Source mapping.
        key: Key to read.
        default: Value returned when absent or non-numeric.

    Returns:
        The number.
    """
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


# --- price history ----------------------------------------------------------


def _run_price_history(ctx: ToolContext) -> ToolResult:
    """Fetch price history and summarise it.

    Args:
        ctx: Execution context.

    Returns:
        The measurement, or a failure when no bars are available.
    """
    frame = ctx.ohlc()
    if frame.n_bars == 0:
        return ToolResult(
            tool="price_history.ohlc",
            success=False,
            error=f"no price history for {ctx.state.ticker}",
        )

    summary = summarize_frame(frame.df)
    metrics: Metrics = {f"ohlc.{k}": v for k, v in summary.items()}
    metrics["ohlc.sufficient"] = frame.sufficient
    metrics["ohlc.fetch_calls"] = frame.fetch_calls
    displays = {
        "ohlc.n_bars": (
            f"{_num(summary, 'n_bars'):.0f} bars "
            f"{summary.get('first_date')} to {summary.get('last_date')}"
        ),
        "ohlc.last_close": f"last close {_num(summary, 'last_close'):.2f}",
    }
    if "return_63" in summary:
        displays["ohlc.return_63"] = f"63-bar return {_num(summary, 'return_63') * 100:+.1f}%"
    if "range_low" in summary:
        displays["ohlc.range_low"] = (
            f"20-bar range {_num(summary, 'range_low'):.2f}-" f"{_num(summary, 'range_high'):.2f}"
        )
    if "median_volume" in summary:
        displays["ohlc.median_volume"] = f"median volume {_num(summary, 'median_volume'):,.0f}"

    # The hints, rendered as one line each so they reach the decision model.
    # A number held only in metrics is invisible to it: the prompt is built
    # from displays.
    if "return_5" in summary:
        displays["ohlc.return_5"] = (
            f"last 5 bars {_num(summary, 'return_5'):+.1f}%, "
            f"{_num(summary, 'up_days_10'):.0f} of the last 10 closes up"
        )
    if "range_position" in summary:
        where = _num(summary, "range_position")
        sits = "at the top of" if where >= 0.8 else ("at the bottom of" if where <= 0.2 else "mid-")
        displays["ohlc.range_position"] = f"last close sits {sits} its 20-bar range ({where:.1f})"
    if "drawdown_pct" in summary:
        displays["ohlc.drawdown_pct"] = (
            f"{_num(summary, 'drawdown_pct'):+.1f}% from the window high"
        )
    if "vol_ratio_20" in summary:
        ratio = _num(summary, "vol_ratio_20")
        displays["ohlc.vol_ratio_20"] = (
            f"recent 20-bar price movement is {ratio:.1f}x the window average"
        )
    if "volume_ratio_5" in summary:
        ratio = _num(summary, "volume_ratio_5")
        displays["ohlc.volume_ratio_5"] = (
            f"last 5 bars traded {ratio:.1f}x the volume of the 60 before them"
        )
    if not frame.sufficient:
        displays["ohlc.sufficient"] = (
            f"only {frame.n_bars} of the {frame.requested_bars} bars requested "
            f"are available, so the longer-window analyses are limited"
        )
    # Stale data is not a leak, but a replay answering with year-old prices is
    # not answering the question either, so the model is told.
    if frame.stale:
        metrics["ohlc.staleness_days"] = frame.staleness_days
        displays["ohlc.staleness_days"] = (
            f"the last bar is {frame.staleness_days} days before the end of "
            f"the requested window; this data is stale"
        )

    return ToolResult(
        tool="price_history.ohlc",
        success=True,
        metrics=metrics,
        displays={k: v for k, v in displays.items() if v},
        findings=(f"{_num(summary, 'n_bars'):.0f} bars available.",),
        network_calls=1 if frame.source == "live" else 0,
    )


# --- trend ------------------------------------------------------------------


def _run_trend(ctx: ToolContext) -> ToolResult:
    """Measure trend persistence from Heiken Ashi run length.

    Args:
        ctx: Execution context.

    Returns:
        The measurement, or a failure when there is too little history.
    """
    from stockcharts.charts.heiken_ashi import heiken_ashi
    from stockcharts.indicators.heiken_runs import compute_ha_run_stats

    frame = ctx.ohlc()
    if frame.n_bars < 10:
        return ToolResult(
            tool="trend.heiken_runs",
            success=False,
            error=f"only {frame.n_bars} bars; need at least 10",
        )

    stats = compute_ha_run_stats(heiken_ashi(frame.df))
    return ToolResult(
        tool="trend.heiken_runs",
        success=True,
        metrics={
            "trend.run_length": int(stats["run_length"]),
            "trend.run_colour": str(stats["run_color"]),
            "trend.run_percentile": float(stats["run_percentile"]),
            "trend.total_runs": int(stats["total_runs"]),
        },
        displays={
            "trend.run_length": (
                f"Heiken Ashi run: {stats['run_length']} consecutive "
                f"{stats['run_color']} candles"
            ),
            "trend.run_percentile": (
                f"{stats['run_percentile']:.0f}th percentile of this ticker's "
                f"historical run lengths"
            ),
        },
        findings=(
            f"Current run is {stats['run_length']} {stats['run_color']} candles, "
            f"at the {stats['run_percentile']:.0f}th percentile.",
        ),
    )


# --- momentum ---------------------------------------------------------------


def _run_momentum(ctx: ToolContext) -> ToolResult:
    """Measure momentum with RSI and the slow Stochastic.

    The RSI series is kept as an artifact because divergence analysis needs
    the column, which is the one real prerequisite edge in this registry.

    Args:
        ctx: Execution context.

    Returns:
        The measurement, or a failure when there is too little history.
    """
    from stockcharts.indicators.rsi import compute_rsi
    from stockcharts.indicators.stochastic import compute_stochastic

    frame = ctx.ohlc()
    period = whole(ctx.params.get("period"), 14)
    if frame.n_bars < period + 2:
        return ToolResult(
            tool="momentum.rsi_stochastic",
            success=False,
            error=f"only {frame.n_bars} bars; need more than {period + 1}",
        )

    rsi = compute_rsi(frame.df["Close"], period=period).dropna()
    if rsi.empty:
        return ToolResult(
            tool="momentum.rsi_stochastic",
            success=False,
            error="RSI could not be computed",
        )

    metrics: Metrics = {"momentum.rsi": round(float(rsi.iloc[-1]), 2)}
    displays = {
        "momentum.rsi": (
            f"RSI({period}) = {rsi.iloc[-1]:.1f}"
            f"{' (overbought)' if rsi.iloc[-1] > 70 else ''}"
            f"{' (oversold)' if rsi.iloc[-1] < 30 else ''}"
        )
    }

    # Columns are pctK/pctD despite what the upstream docstring claims.
    stoch = compute_stochastic(frame.df["High"], frame.df["Low"], frame.df["Close"])
    k = stoch["pctK"].dropna()
    d = stoch["pctD"].dropna()
    if not k.empty and not d.empty:
        metrics["momentum.stoch_k"] = round(float(k.iloc[-1]), 2)
        metrics["momentum.stoch_d"] = round(float(d.iloc[-1]), 2)
        displays["momentum.stoch_k"] = f"Stochastic %K {k.iloc[-1]:.1f} / %D {d.iloc[-1]:.1f}"

    ctx.state.artifacts["rsi_series"] = rsi
    metrics["momentum.rsi_available"] = True

    return ToolResult(
        tool="momentum.rsi_stochastic",
        success=True,
        metrics=metrics,
        displays=displays,
        findings=(f"RSI({period}) is {rsi.iloc[-1]:.1f}.",),
    )


# --- volatility (computed here, not wrapped) --------------------------------


def _run_volatility(ctx: ToolContext) -> ToolResult:
    """Measure realised volatility and drawdown.

    Computed in the agent rather than wrapped: stockcharts exposes no public
    ATR or realised-volatility function, and a router with no volatility
    signal at all could not be fairly evaluated.

    Args:
        ctx: Execution context.

    Returns:
        The measurement, or a failure when there is too little history.
    """
    frame = ctx.ohlc()
    window = whole(ctx.params.get("window"), 20)
    if frame.n_bars < window + 2:
        return ToolResult(
            tool="volatility.realised",
            success=False,
            error=f"only {frame.n_bars} bars; need more than {window + 1}",
        )

    close = frame.df["Close"].dropna()
    returns = np.log(close).diff().dropna()
    recent = float(returns.tail(window).std() * np.sqrt(252) * 100)
    full = float(returns.std() * np.sqrt(252) * 100)
    drawdown = float((close / close.cummax() - 1.0).min() * 100)

    return ToolResult(
        tool="volatility.realised",
        success=True,
        metrics={
            "volatility.recent_ann_pct": round(recent, 2),
            "volatility.full_ann_pct": round(full, 2),
            "volatility.max_drawdown_pct": round(drawdown, 2),
            "volatility.ratio": round(recent / full, 2) if full > 0 else None,
        },
        displays={
            "volatility.recent_ann_pct": (
                f"{window}-bar realised volatility {recent:.0f}% annualised "
                f"(vs {full:.0f}% over the full window)"
            ),
            "volatility.max_drawdown_pct": f"max drawdown {drawdown:.1f}%",
        },
        findings=(f"Realised volatility is {recent:.0f}% annualised.",),
    )


# --- registry ---------------------------------------------------------------


def build_registry(
    include_absent: bool = True,
    exclude: Sequence[str] = (),
) -> ToolRegistry:
    """Assemble the registry of analyses.

    Args:
        include_absent: Register the analyses this system cannot perform, so
            that the decision model is told they are unavailable rather than
            left to infer it.
        exclude: Tool names to leave out entirely. Unlike withholding a tool
            at decision time, this removes it from the catalogue, so the
            decision model is never told it exists. Intended for keeping an
            expensive analysis out of a fast test, not for routing.

    Returns:
        The validated registry.
    """
    specs: list[ToolSpec] = [
        ToolSpec(
            name="price_history.ohlc",
            category="price_history",
            title="Price history",
            jev_description=(
                "loads the price bars and reports how much history is available, "
                "the last close, the recent range and typical volume. This is "
                "most informative at the start of an analysis, when nothing "
                "about the series is known yet."
            ),
            # Only the keys a frame of any length yields. The range, return
            # and volume figures need more than one bar, and staleness only
            # applies to live data, so listing them would make a satisfied
            # measurement look unsatisfied and invite a second fetch.
            produces=frozenset(
                {
                    "ohlc.n_bars",
                    "ohlc.last_close",
                    "ohlc.first_date",
                    "ohlc.last_date",
                    "ohlc.sufficient",
                    "ohlc.fetch_calls",
                }
            ),
            cost=ToolCost(est_seconds=0.4, network=True, network_calls=1),
            run=_run_price_history,
        ),
        ToolSpec(
            name="trend.heiken_runs",
            category="trend",
            title="Trend persistence",
            jev_description=(
                "counts how many consecutive Heiken Ashi candles share one "
                "colour and ranks that run against the ticker's own history, "
                "showing whether a move is unusually extended. This is most "
                "informative when price has been moving one way without "
                "interruption for many sessions, and least informative when "
                "direction has been changing back and forth."
            ),
            produces=frozenset(
                {
                    "trend.run_length",
                    "trend.run_colour",
                    "trend.run_percentile",
                    "trend.total_runs",
                }
            ),
            requires=frozenset({"ohlc.n_bars"}),
            applicable_when=(Condition("ohlc.n_bars", "gte", 10),),
            # 1.3s measured on NVDA's full history, against 0.02s on a
            # 400-bar synthetic series: it ranks the current run against
            # every run the ticker has ever made, so cost tracks how much
            # history exists rather than how much was requested.
            cost=ToolCost(est_seconds=1.3),
            run=_run_trend,
        ),
        ToolSpec(
            name="momentum.rsi_stochastic",
            category="momentum",
            title="Momentum (RSI and Stochastic)",
            jev_description=(
                "computes RSI and the slow Stochastic, showing whether the "
                "stock is overbought or oversold and whether momentum is "
                "turning. This is most informative when price has moved far "
                "and fast enough recently that it may be stretched, or sits "
                "at an edge of its recent range, and least informative when "
                "it has been drifting gently."
            ),
            produces=frozenset(
                {
                    "momentum.rsi",
                    "momentum.stoch_k",
                    "momentum.stoch_d",
                    "momentum.rsi_available",
                }
            ),
            requires=frozenset({"ohlc.n_bars"}),
            applicable_when=(Condition("ohlc.n_bars", "gte", 20),),
            cost=ToolCost(est_seconds=0.02),
            default_params={"period": 14},
            run=_run_momentum,
        ),
        ToolSpec(
            name="volatility.realised",
            category="volatility",
            title="Volatility and drawdown",
            jev_description=(
                "measures realised volatility over a recent window against the "
                "full period, and the deepest peak-to-trough fall. This is "
                "most informative when the character of the moves appears to "
                "have changed recently -- a quiet stretch giving way to sharp "
                "bars, or the reverse -- and least informative when movement "
                "has been steady throughout."
            ),
            produces=frozenset(
                {
                    "volatility.recent_ann_pct",
                    "volatility.full_ann_pct",
                    "volatility.max_drawdown_pct",
                    "volatility.ratio",
                }
            ),
            requires=frozenset({"ohlc.n_bars"}),
            applicable_when=(Condition("ohlc.n_bars", "gte", 25),),
            cost=ToolCost(est_seconds=0.02),
            computed_in_agent=True,
            default_params={"window": 20},
            run=_run_volatility,
        ),
        *analysis_specs(),
    ]

    if include_absent:
        specs.extend(absent_specs())

    dropped = set(exclude)
    return ToolRegistry([s for s in specs if s.name not in dropped])
