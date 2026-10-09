"""The analyses that depend on other analyses, a benchmark, or the network.

These are kept apart from the self-contained wrappers because each carries a
complication worth naming:

* divergence needs an RSI column, which is the one real dependency edge in
  the registry;
* relative strength needs a second ticker, so it can be unavailable for
  reasons that have nothing to do with the primary history;
* price-regime segmentation is fitted with hindsight, which has to reach the
  decision model rather than be hidden from it;
* insider activity reaches the network and has genuine point-in-time support;
* the macro snapshot has none, so it withholds itself from any replay.

Public API:
    analysis_specs() -> list[ToolSpec]
"""

from __future__ import annotations

from stock_agent.conditions import Condition
from stock_agent.registry import ToolContext, ToolCost, ToolResult, ToolSpec
from stock_agent.state import JsonValue
from stock_agent.tools.coerce import maybe_number, number, text, whole

__all__ = ["analysis_specs"]

Metrics = dict[str, JsonValue]

# Volatility bands, restated here rather than imported: the only
# implementation lives in scripts/, which is not an importable package, and
# it is hardcoded to ^VIX with no as-of support and swallows every exception.
_VIX_BANDS = ((30.0, "extreme fear"), (25.0, "high fear"), (20.0, "elevated"))


def _run_divergence(ctx: ToolContext) -> ToolResult:
    """Look for RSI divergence against price.

    The underlying detector requires an RSI column already present on the
    frame, which is why this tool declares a dependency rather than computing
    RSI itself.

    Args:
        ctx: Execution context.

    Returns:
        The measurement, or a failure when its input is missing.
    """
    from stockcharts.indicators.divergence import detect_divergence

    frame = ctx.ohlc()
    rsi = ctx.state.artifacts.get("rsi_series")
    if rsi is None:
        return ToolResult(
            tool="pattern.rsi_divergence",
            success=False,
            error="no RSI series in state; momentum must run first",
        )

    enriched = frame.df.copy()
    enriched["RSI"] = rsi.reindex(enriched.index)
    enriched = enriched.dropna(subset=["RSI"])
    if len(enriched) < 60:
        return ToolResult(
            tool="pattern.rsi_divergence",
            success=False,
            error=f"only {len(enriched)} bars carry RSI; need at least 60",
        )

    found = detect_divergence(enriched, price_col="Close", rsi_col="RSI")
    bullish = bool(found.get("bullish"))
    bearish = bool(found.get("bearish"))
    signal = str(found.get("last_signal") or "none")

    if bullish or bearish:
        kind = "bullish" if bullish else "bearish"
        display = f"{kind} RSI divergence detected ({signal})"
    else:
        display = "no RSI divergence over the lookback"

    return ToolResult(
        tool="pattern.rsi_divergence",
        success=True,
        metrics={
            "pattern.bullish_divergence": bullish,
            "pattern.bearish_divergence": bearish,
            "pattern.last_signal": signal,
            "pattern.bullish_score": float(found.get("bullish_score") or 0.0),
            "pattern.bearish_score": float(found.get("bearish_score") or 0.0),
        },
        displays={"pattern.last_signal": display},
        findings=(display + ".",),
    )


def _run_relative_strength(ctx: ToolContext) -> ToolResult:
    """Compare the ticker against a benchmark.

    Args:
        ctx: Execution context.

    Returns:
        The measurement, or a failure when the benchmark is unavailable.
    """
    from stockcharts.indicators.beta import analyze_beta_regime

    benchmark = text(ctx.params.get("benchmark"), "SPY")
    if benchmark == ctx.state.ticker:
        return ToolResult(
            tool="relative_strength.beta_regime",
            success=False,
            error=f"{benchmark} cannot be measured against itself",
        )

    asset = ctx.ohlc()
    reference = ctx.ohlc(ticker=benchmark)
    if reference.n_bars < 60:
        return ToolResult(
            tool="relative_strength.beta_regime",
            success=False,
            error=f"no usable history for the benchmark {benchmark}",
        )

    analysis = analyze_beta_regime(asset.df, reference.df)
    regime = str(analysis.get("regime", "insufficient-data"))
    if regime == "insufficient-data":
        return ToolResult(
            tool="relative_strength.beta_regime",
            success=False,
            error="not enough overlapping history to measure relative strength",
        )

    pct = float(analysis.get("pct_from_ma") or 0.0)
    beta = analysis.get("rolling_beta")
    percentile = analysis.get("beta_percentile")

    metrics: Metrics = {
        "relative_strength.regime": regime,
        "relative_strength.pct_from_ma": round(pct, 2),
        "relative_strength.benchmark": benchmark,
    }
    displays = {
        "relative_strength.regime": (
            f"versus {benchmark}: {regime}, {pct:+.1f}% from its moving average"
        )
    }
    if beta is not None:
        metrics["relative_strength.beta"] = round(float(beta), 3)
        displays["relative_strength.beta"] = f"rolling beta {float(beta):.2f}"
    if percentile is not None:
        metrics["relative_strength.beta_percentile"] = round(float(percentile), 1)

    return ToolResult(
        tool="relative_strength.beta_regime",
        success=True,
        metrics=metrics,
        displays=displays,
        findings=(f"Relative strength versus {benchmark} is {regime}.",),
        network_calls=1 if reference.source == "live" else 0,
    )


def _run_price_regime(ctx: ToolContext) -> ToolResult:
    """Segment the price history into bull, bear and sideways stretches.

    Args:
        ctx: Execution context.

    Returns:
        The measurement, or a failure when there is too little history.
    """
    from stockcharts.indicators.segmentation import detect_regimes

    frame = ctx.ohlc()
    if frame.n_bars < 120:
        return ToolResult(
            tool="market_regime.price",
            success=False,
            error=f"only {frame.n_bars} bars; need at least 120",
        )

    found = detect_regimes(
        frame.df,
        min_segment=whole(ctx.params.get("min_segment"), 21),
        max_shuffles=whole(ctx.params.get("max_shuffles"), 250),
    )
    segments = found.get("segments") or []
    current = str(found.get("current", "insufficient-data"))
    pivots = found.get("pivots") or []

    last = segments[-1] if segments else {}
    slope = float(last.get("slope_ann") or 0.0)
    confidence = float(last.get("confidence") or 0.0)

    return ToolResult(
        tool="market_regime.price",
        success=True,
        metrics={
            "market_regime.current": current,
            "market_regime.n_segments": len(segments),
            "market_regime.slope_ann": round(slope, 3),
            "market_regime.confidence": round(confidence, 2),
            "market_regime.n_pivots": len(pivots),
        },
        displays={
            "market_regime.current": (
                f"current price regime {current} "
                f"(slope {slope:+.2f}/yr, confidence {confidence:.2f}), "
                f"{len(pivots)} regime changes over the window"
            )
        },
        findings=(f"The most recent price regime is {current}.",),
        caveat="fitted in hindsight; the current label can change as bars arrive",
    )


def _run_insider(ctx: ToolContext) -> ToolResult:
    """Measure insider trading intensity from SEC filings.

    Args:
        ctx: Execution context.

    Returns:
        The measurement, or a failure when filings cannot be retrieved.
    """
    from stockcharts.screener.sec_insider import screen_insider_ticker

    frame = ctx.ohlc()
    try:
        # Thresholds are disabled deliberately. Left at their defaults the
        # function returns None whenever activity is unremarkable, which the
        # state would record as "no data" -- a false absence the decision
        # model has no way to detect.
        found = screen_insider_ticker(
            ctx.state.ticker,
            recent_days=whole(ctx.params.get("recent_days"), 90),
            # The default of a year, added to the recent window and twice the
            # filing lag, spans about 545 days -- and the feed fetches every
            # filing in it one at a time. Shortening it is the difference
            # between a tool that answers and one that does not return.
            holdings_lookback_days=whole(ctx.params.get("holdings_lookback_days"), 120),
            end_date=ctx.state.asof,
            min_volume_increase=None,
            min_holding_increase=None,
            ohlc=frame.df if frame.n_bars else None,
        )
    except Exception as exc:  # noqa: BLE001 - network and parsing both fail here
        return ToolResult(
            tool="events.insider",
            success=False,
            error=f"{type(exc).__name__}: {str(exc)[:120]}",
            network_calls=1,
        )

    if found is None:
        return ToolResult(
            tool="events.insider",
            success=False,
            error="no insider filings found for this ticker",
            network_calls=1,
        )

    bought = float(found.recent_bought_shares)
    sold = float(found.recent_sold_shares)
    increase = found.volume_ratio_increase

    if bought and not sold:
        direction = "buying only"
    elif sold and not bought:
        direction = "selling only"
    elif bought or sold:
        direction = "both directions"
    else:
        direction = "no open-market activity"

    return ToolResult(
        tool="events.insider",
        success=True,
        metrics={
            "events.insider_bought": bought,
            "events.insider_sold": sold,
            "events.insider_direction": direction,
            "events.volume_ratio_increase": (
                None if increase is None else round(float(increase), 3)
            ),
        },
        displays={
            "events.insider_direction": (
                f"insider open-market activity: {direction} "
                f"({bought:,.0f} bought, {sold:,.0f} sold)"
            )
        },
        findings=(f"Insider activity shows {direction}.",),
        network_calls=1,
    )


def _run_vix(ctx: ToolContext) -> ToolResult:
    """Read the market-wide volatility index.

    Args:
        ctx: Execution context.

    Returns:
        The measurement, or a failure when the index is unavailable.
    """
    frame = ctx.ohlc(ticker="^VIX", bars=60)
    close = frame.df["Close"].dropna() if frame.n_bars else None
    if close is None or close.empty:
        return ToolResult(
            tool="volatility.vix",
            success=False,
            error="no history available for ^VIX",
            network_calls=1 if frame.source == "live" else 0,
        )

    level = float(close.iloc[-1])
    status = "calm"
    for threshold, name in _VIX_BANDS:
        if level >= threshold:
            status = name
            break

    return ToolResult(
        tool="volatility.vix",
        success=True,
        metrics={"volatility.vix": round(level, 2), "volatility.vix_status": status},
        displays={"volatility.vix": f"VIX {level:.1f} ({status})"},
        findings=(f"The volatility index is at {level:.1f}.",),
        network_calls=1 if frame.source == "live" else 0,
    )


def _run_volume(ctx: ToolContext) -> ToolResult:
    """Compare recent volume against its own recent history.

    Computed here rather than wrapped: stockcharts exposes volume only as an
    average field on screener results and a private figure-mutating profile,
    neither of which returns usable numbers.

    Args:
        ctx: Execution context.

    Returns:
        The measurement, or a failure when there is too little history.
    """
    frame = ctx.ohlc()
    window = whole(ctx.params.get("window"), 5)
    baseline = whole(ctx.params.get("baseline"), 60)
    if frame.n_bars < baseline + window:
        return ToolResult(
            tool="volume.surge",
            success=False,
            error=f"only {frame.n_bars} bars; need more than {baseline + window}",
        )

    volume = frame.df["Volume"].dropna()
    recent = float(volume.tail(window).mean())
    prior = float(volume.iloc[-(baseline + window) : -window].median())
    if prior <= 0:
        return ToolResult(
            tool="volume.surge",
            success=False,
            error="no usable baseline volume",
        )

    ratio = recent / prior
    if ratio >= 3.0:
        shape = "sharp surge"
    elif ratio >= 1.5:
        shape = "elevated"
    elif ratio <= 0.4:
        shape = "dried up"
    else:
        shape = "normal"

    return ToolResult(
        tool="volume.surge",
        success=True,
        metrics={
            "volume.ratio": round(ratio, 2),
            "volume.shape": shape,
            "volume.recent_mean": round(recent, 0),
        },
        displays={
            "volume.ratio": (
                f"recent {window}-bar volume is {ratio:.1f}x its {baseline}-bar "
                f"median ({shape})"
            )
        },
        findings=(f"Volume is {shape} at {ratio:.1f}x its baseline.",),
    )


def _run_mcglone(ctx: ToolContext) -> ToolResult:
    """Combine regime, volatility and drawdown into a contrarian reading.

    Args:
        ctx: Execution context.

    Returns:
        The measurement, or a failure when an input is missing.
    """
    state = ctx.state
    regime = state.value("relative_strength.regime")
    vix = maybe_number(state.value("volatility.vix"))
    drawdown = maybe_number(state.value("volatility.max_drawdown_pct"))
    beta = number(state.value("relative_strength.beta"), 1.0)

    missing = [
        name
        for name, value in (
            ("relative strength", regime),
            ("volatility index", vix),
            ("drawdown", drawdown),
        )
        if value is None
    ]
    if missing:
        return ToolResult(
            tool="signal.mcglone",
            success=False,
            error=f"missing inputs: {', '.join(missing)}",
        )

    is_risk_off = regime == "risk-off"
    is_spike = vix is not None and vix >= 30.0
    is_correction = drawdown is not None and drawdown <= -10.0
    met = sum((is_risk_off, is_spike, is_correction))

    if met == 3:
        signal, why = "capitulation", "risk-off, volatility spike and a correction together"
    elif met == 2:
        signal, why = "watch", "two of the three contrarian conditions are met"
    elif met == 1:
        signal, why = "early", "one contrarian condition is met"
    else:
        signal, why = "none", "no contrarian conditions are met"

    return ToolResult(
        tool="signal.mcglone",
        success=True,
        metrics={
            "signal.mcglone": signal,
            "signal.conditions_met": met,
            "signal.beta_used": round(beta, 3),
        },
        displays={"signal.mcglone": f"contrarian reading: {signal} -- {why}"},
        findings=(f"Contrarian conditions met: {met} of 3.",),
    )


def _run_macro(ctx: ToolContext) -> ToolResult:
    """Read the macro watchlist and count what is flashing.

    Args:
        ctx: Execution context.

    Returns:
        The measurement, or a failure when the snapshot cannot be built.
    """
    from stockcharts.macro.snapshot import build_snapshot, evaluate_watchlist

    if ctx.state.asof is not None:
        # Belt and braces: the registry already withholds this tool in a
        # replay. Reaching here would mean a live snapshot was about to be
        # labelled with a historical date.
        return ToolResult(
            tool="macro.snapshot",
            success=False,
            error="no point-in-time macro snapshot exists; withheld from replay",
        )

    try:
        snapshot = build_snapshot(include_equities=False)
        rows = evaluate_watchlist(snapshot)
    except Exception as exc:  # noqa: BLE001 - several feeds, each able to fail
        return ToolResult(
            tool="macro.snapshot",
            success=False,
            error=f"{type(exc).__name__}: {str(exc)[:120]}",
            network_calls=1,
        )

    if not rows:
        return ToolResult(
            tool="macro.snapshot",
            success=False,
            error="the macro watchlist evaluated to nothing",
            network_calls=1,
        )

    counts = {"ok": 0, "watch": 0, "alert": 0, "unknown": 0}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1

    flashing = [r.label for r in rows if r.status == "alert"]
    if counts["alert"]:
        stance = "stressed"
    elif counts["watch"] >= 3:
        stance = "deteriorating"
    elif counts["unknown"] > counts["ok"]:
        stance = "largely unmeasured"
    else:
        stance = "benign"

    return ToolResult(
        tool="macro.snapshot",
        success=True,
        metrics={
            "macro.stance": stance,
            "macro.n_alert": counts["alert"],
            "macro.n_watch": counts["watch"],
            "macro.n_unknown": counts["unknown"],
            "macro.alerting": flashing[:4],
        },
        displays={
            "macro.stance": (
                f"macro backdrop {stance}: {counts['alert']} alerting, "
                f"{counts['watch']} on watch, {counts['unknown']} unmeasured"
                + (f" -- {', '.join(flashing[:3])}" if flashing else "")
            )
        },
        findings=(f"The macro backdrop is {stance}.",),
        caveat="whole-market context, not specific to this ticker",
        network_calls=len(rows),
    )


def analysis_specs() -> list[ToolSpec]:
    """Return the dependent, benchmark-relative and networked analyses.

    Returns:
        Tool specifications.
    """
    return [
        ToolSpec(
            name="pattern.rsi_divergence",
            category="pattern",
            title="RSI divergence",
            jev_description=(
                "checks whether price and RSI are moving in opposite "
                "directions at recent swing points, which can precede a "
                "turn. Requires momentum to have been measured first. This "
                "is most informative when price has made a fresh extreme "
                "that momentum did not confirm, and least informative when "
                "price and momentum have been moving together."
            ),
            produces=frozenset(
                {
                    "pattern.bullish_divergence",
                    "pattern.bearish_divergence",
                    "pattern.last_signal",
                    "pattern.bullish_score",
                    "pattern.bearish_score",
                }
            ),
            requires=frozenset({"momentum.rsi_available"}),
            applicable_when=(Condition("ohlc.n_bars", "gte", 80),),
            cost=ToolCost(est_seconds=0.08),
            run=_run_divergence,
        ),
        ToolSpec(
            name="relative_strength.beta_regime",
            category="relative_strength",
            title="Relative strength versus the market",
            jev_description=(
                "measures the ticker against a benchmark index, reporting "
                "whether it is leading or lagging and how volatile it is "
                "relative to the market. This is most informative when the "
                "ticker and the broad market appear to be moving apart, and "
                "least informative when it is tracking the market closely."
            ),
            produces=frozenset(
                {
                    "relative_strength.regime",
                    "relative_strength.pct_from_ma",
                    "relative_strength.beta",
                    "relative_strength.beta_percentile",
                    "relative_strength.benchmark",
                }
            ),
            requires=frozenset({"ohlc.n_bars"}),
            applicable_when=(Condition("ohlc.n_bars", "gte", 260),),
            cost=ToolCost(est_seconds=0.4, network=True, network_calls=1),
            default_params={"benchmark": "SPY"},
            run=_run_relative_strength,
        ),
        ToolSpec(
            name="market_regime.price",
            category="market_regime",
            title="Price regime segmentation",
            jev_description=(
                "splits the price history into bull, bear and sideways "
                "stretches and reports the current one. The segmentation is "
                "fitted over the whole window including the most recent "
                "bars, so the current label is hindsight and can change as "
                "new bars arrive. This is most informative when the window "
                "appears to contain more than one distinct phase, and least "
                "informative when a single trend has run throughout."
            ),
            produces=frozenset(
                {
                    "market_regime.current",
                    "market_regime.n_segments",
                    "market_regime.slope_ann",
                    "market_regime.confidence",
                    "market_regime.n_pivots",
                }
            ),
            requires=frozenset({"ohlc.n_bars"}),
            applicable_when=(Condition("ohlc.n_bars", "gte", 120),),
            # Measured, not guessed: around nine seconds on 400 daily bars.
            # The permutation test dominates, so cost tracks max_shuffles far
            # more than it tracks the number of bars.
            cost=ToolCost(est_seconds=9.0),
            retrospective=True,
            default_params={"min_segment": 21, "max_shuffles": 250},
            run=_run_price_regime,
        ),
        ToolSpec(
            name="events.insider",
            category="events",
            title="Insider trading activity",
            jev_description=(
                "reads recent SEC Form 4 filings and reports whether company "
                "insiders have been buying or selling on the open market, "
                "and how that compares with the preceding period. This is "
                "most informative when price has moved substantially and the "
                "reason is not visible in the price series itself."
            ),
            produces=frozenset(
                {
                    "events.insider_bought",
                    "events.insider_sold",
                    "events.insider_direction",
                    "events.volume_ratio_increase",
                }
            ),
            requires=frozenset({"ohlc.n_bars"}),
            # Reaches SEC directly rather than through the price provider, so
            # it is withheld on synthetic data instead of quietly going to the
            # network during an offline run.
            applicable_when=(Condition("run.data_source", "eq", "live"),),
            # A floor, not an estimate. The feed issues one request per
            # filing with no cap, and a large company has hundreds across the
            # window below, so the cost scales with how many insiders a
            # company has rather than with anything the agent controls. Not
            # measured end to end on a live run: the decision model ranked it
            # last in every round, which is itself a reasonable judgement.
            # It runs under a deadline regardless.
            cost=ToolCost(est_seconds=120.0, network=True, network_calls=200),
            asof_capable="native",
            default_params={"recent_days": 90, "holdings_lookback_days": 120},
            run=_run_insider,
        ),
        ToolSpec(
            name="volatility.vix",
            category="volatility",
            title="Market volatility index",
            jev_description=(
                "reads the market-wide volatility index, showing whether the "
                "broad market is calm or fearful. This is most informative "
                "when the whole market, rather than this ticker alone, may "
                "be under strain, and least informative when conditions are "
                "ordinary."
            ),
            produces=frozenset({"volatility.vix", "volatility.vix_status"}),
            cost=ToolCost(est_seconds=0.4, network=True, network_calls=1),
            computed_in_agent=True,
            run=_run_vix,
        ),
        ToolSpec(
            name="volume.surge",
            category="volume",
            title="Volume surge or dry-up",
            jev_description=(
                "compares the most recent few bars of trading volume against "
                "the preceding months, showing whether participation has "
                "spiked or faded. This is most informative when turnover "
                "appears to have changed sharply against its own recent "
                "norm, and least informative when participation has been "
                "ordinary."
            ),
            produces=frozenset(
                {
                    "volume.ratio",
                    "volume.shape",
                    "volume.recent_mean",
                }
            ),
            requires=frozenset({"ohlc.n_bars"}),
            applicable_when=(Condition("ohlc.n_bars", "gte", 70),),
            cost=ToolCost(est_seconds=0.02),
            computed_in_agent=True,
            default_params={"window": 5, "baseline": 60},
            run=_run_volume,
        ),
        ToolSpec(
            name="signal.mcglone",
            category="signal",
            title="Contrarian capitulation reading",
            jev_description=(
                "combines relative strength, the volatility index and "
                "drawdown into a single contrarian reading, which is most "
                "informative when the market is already under stress."
            ),
            produces=frozenset(
                {
                    "signal.mcglone",
                    "signal.conditions_met",
                    "signal.beta_used",
                }
            ),
            requires=frozenset(
                {
                    "relative_strength.regime",
                    "volatility.vix",
                    "volatility.max_drawdown_pct",
                }
            ),
            cost=ToolCost(est_seconds=0.01),
            run=_run_mcglone,
        ),
        ToolSpec(
            name="macro.snapshot",
            category="macro",
            title="Macro backdrop",
            jev_description=(
                "reads the macro watchlist -- yields, credit spreads, "
                "liquidity -- and reports how many measures are flashing. "
                "This describes the whole market, not this ticker, and is "
                "only available for a live run. It is most informative when "
                "the move being examined may be market-wide rather than "
                "specific to this ticker."
            ),
            produces=frozenset(
                {
                    "macro.stance",
                    "macro.n_alert",
                    "macro.n_watch",
                    "macro.n_unknown",
                    "macro.alerting",
                }
            ),
            applicable_when=(
                Condition("run.live", "eq", True),
                Condition("run.data_source", "eq", "live"),
            ),
            # 18s cold, 4s warm, measured after the Accept-header fix in
            # the macro client. It exceeded a 45s deadline before that, which
            # led me to record it as the tool's real cost -- it was a bug in
            # how the request was made, not what the work costs.
            cost=ToolCost(est_seconds=18.0, network=True, network_calls=15),
            # Several components are revised series with no vintage source, so
            # truncating them would silently backfill revised numbers into a
            # historical window. Missing information beats contaminated.
            asof_capable="none",
            run=_run_macro,
        ),
    ]
