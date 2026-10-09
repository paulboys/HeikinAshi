"""Synthetic situations with known routing expectations.

Six minimal pairs and three controls. Within a pair, the two halves share a
base series and differ in exactly one planted feature -- so the only defensible
difference in how they should be routed is the one analysis that measures that
feature. That makes a pair a controlled comparison rather than a vibe.

Two disciplines keep this honest:

**Labels are routing expectations, never market truths.** A scenario says
"an analysis that never looks at volume missed information that is present",
not "this stock will go up". No scenario asserts a price direction, and
nothing here can be read as a claim about returns.

**Every planted feature is verified against the real detector before the
scenario is used.** A base series happened to fire a bearish divergence by
chance, which would have made a labelled "no divergence" case silently wrong
and both arms identically mistaken. :func:`verify_all` is what caught that.

Public API:
    Scenario, SCENARIOS, by_name(name), pairs(), verify_all()
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from stock_agent.eval.synthetic import (
    plant_divergence,
    plant_momentum_push,
    plant_run,
    plant_volume_surge,
    synth_ohlc,
    synth_vix,
    verify_divergence,
    verify_relative_strength,
    verify_run,
    verify_volatility_ratio,
    verify_volume_surge,
)

__all__ = ["SCENARIOS", "Scenario", "by_name", "pairs", "verify_all"]

TICKER = "SYN"
BENCHMARK = "SPY"
VOL_INDEX = "^VIX"

# Every scenario needs price history, and the loop fetches it without asking,
# so it is never part of a routing expectation.
BOOTSTRAP = "price_history.ohlc"

# The segmentation fit costs around nine seconds, far more than everything
# else combined. Running it where no regime change exists is the clearest
# example of a wasteful choice, which is what makes it the one tool worth
# marking forbidden. This is a cost judgement, declared in advance, not a
# claim that the analysis would be wrong.
EXPENSIVE = "market_regime.price"

Frames = dict[str, pd.DataFrame]


@dataclass(frozen=True)
class Scenario:
    """One situation, with what a good router would look at.

    Attributes:
        name: Stable identifier.
        pair: Minimal-pair identifier; both halves share it. None for controls.
        half: Which side of the pair this is, for reporting.
        description: What was planted, in plain terms.
        build: Produces the frames, keyed by ticker.
        required: Analyses that measure a feature this scenario contains. A
            router missing one of these overlooked information that is there.
        forbidden: Analyses that would be wasted here.
        pivotal: The analysis the planted feature is meant to pull in; this is
            what differs between the halves of a pair.
        bars: Length of the generated history, for reporting.
        check: Confirms the planted feature really is present, or really is
            absent, using the production detector.
    """

    name: str
    pair: str | None
    half: str
    description: str
    build: Callable[[], Frames]
    required: frozenset[str]
    forbidden: frozenset[str] = frozenset()
    pivotal: str | None = None
    bars: int = 400
    check: Callable[[Frames], tuple[bool, str]] | None = field(default=None)

    def verify(self) -> tuple[bool, str]:
        """Confirm the scenario is what it claims to be.

        Returns:
            Whether the planted feature is as labelled, and what the detector
            reported. A scenario with no check passes trivially.
        """
        if self.check is None:
            return True, "no check declared"
        return self.check(self.build())

    @property
    def pivotal_probe(self) -> str | None:
        """Name the analysis a within-pair comparison should look at.

        The absent half of a pair declares no pivotal analysis -- there is
        nothing there to find -- but comparing the two halves means scoring
        the *same* analysis on both. So the absent half borrows its partner's.

        Returns:
            The tool name, or None for a control with no pair.
        """
        if self.pivotal is not None:
            return self.pivotal
        if self.pair is None:
            return None
        for other in SCENARIOS:
            if other.pair == self.pair and other.pivotal is not None:
                return other.pivotal
        return None

    def relevance(self, tools: list[str]) -> list[int]:
        """Score a ranking of tools for nDCG.

        Args:
            tools: Tool names, in the order a router ranked them.

        Returns:
            One relevance value per tool: two for the pivotal analysis, one
            for anything else required, zero otherwise. The pivotal analysis
            is weighted higher because it is the only thing distinguishing
            this scenario from its pair.
        """
        return [2 if t == self.pivotal else (1 if t in self.required else 0) for t in tools]


# --- shared frame construction ---------------------------------------------


def _with_market(frame: pd.DataFrame, benchmark: pd.DataFrame) -> Frames:
    """Attach a benchmark and a derived volatility index to a series.

    Args:
        frame: The ticker's history.
        benchmark: The benchmark's history.

    Returns:
        Frames keyed by ticker.
    """
    return {TICKER: frame, BENCHMARK: benchmark, VOL_INDEX: synth_vix(frame)}


def _benchmark(bars: int, seed: int = 101) -> pd.DataFrame:
    """Build a benchmark that advances gently.

    Args:
        bars: Bars to generate.
        seed: Generator seed.

    Returns:
        The benchmark history.
    """
    return synth_ohlc(bars, seed=seed, drift_ann=0.09, vol_ann=0.15, s0=400.0)


def _base(
    bars: int = 400,
    seed: int = 1,
    drift: float = 0.08,
    vol: float = 0.18,
) -> pd.DataFrame:
    """Build a plain series with no planted feature.

    Args:
        bars: Bars to generate.
        seed: Generator seed.
        drift: Annualised drift.
        vol: Annualised volatility.

    Returns:
        The history.
    """
    return synth_ohlc(bars, seed=seed, drift_ann=drift, vol_ann=vol)


def _plain(
    bars: int = 400,
    seed: int = 1,
    drift: float = 0.08,
    vol: float = 0.18,
) -> Callable[[], Frames]:
    """Build a scenario constructor for an unplanted series.

    Args:
        bars: Bars to generate.
        seed: Generator seed.
        drift: Annualised drift.
        vol: Annualised volatility.

    Returns:
        A constructor producing the frames.
    """
    return lambda: _with_market(_base(bars, seed, drift, vol), _benchmark(bars))


# --- the checks ------------------------------------------------------------


def _check_run(present: bool, minimum: int = 7) -> Callable[[Frames], tuple[bool, str]]:
    """Build a check on Heiken Ashi run length.

    Args:
        present: Whether an extended run is expected.
        minimum: Run length counted as extended.

    Returns:
        A check function.
    """

    def check(frames: Frames) -> tuple[bool, str]:
        length, colour = verify_run(frames[TICKER])
        found = length >= minimum
        return found == present, f"run of {length} {colour} candles"

    return check


def _check_divergence(present: bool) -> Callable[[Frames], tuple[bool, str]]:
    """Build a check on RSI divergence.

    Args:
        present: Whether a divergence is expected.

    Returns:
        A check function.
    """

    def check(frames: Frames) -> tuple[bool, str]:
        fired, detail = verify_divergence(frames[TICKER])
        return fired == present, detail

    return check


def _check_volume(present: bool, threshold: float = 3.0) -> Callable[[Frames], tuple[bool, str]]:
    """Build a check on the volume ratio.

    Args:
        present: Whether a surge is expected.
        threshold: Ratio counted as a surge.

    Returns:
        A check function.
    """

    def check(frames: Frames) -> tuple[bool, str]:
        ratio = verify_volume_surge(frames[TICKER])
        return (ratio >= threshold) == present, f"volume ratio {ratio:.2f}"

    return check


def _check_volatility(
    present: bool, threshold: float = 1.6
) -> Callable[[Frames], tuple[bool, str]]:
    """Build a check on the realised-volatility ratio.

    Args:
        present: Whether a volatility spike is expected.
        threshold: Ratio counted as a spike.

    Returns:
        A check function.
    """

    def check(frames: Frames) -> tuple[bool, str]:
        ratio = verify_volatility_ratio(frames[TICKER])
        return (ratio >= threshold) == present, f"volatility ratio {ratio:.2f}"

    return check


def _check_relative(expected: str) -> Callable[[Frames], tuple[bool, str]]:
    """Build a check on the relative-strength label.

    Args:
        expected: The label the scenario claims.

    Returns:
        A check function.
    """

    def check(frames: Frames) -> tuple[bool, str]:
        label = verify_relative_strength(frames[TICKER], frames[BENCHMARK])
        return label == expected, f"relative strength {label}"

    return check


def _check_momentum(
    extreme: bool,
    low: float = 30.0,
    high: float = 70.0,
    run_limit: int = 7,
) -> Callable[[Frames], tuple[bool, str]]:
    """Build a check on RSI, and on the pair staying minimal.

    The run length is asserted too. An upward push drives RSI up but also
    produces an extended Heiken Ashi run, which would plant the trend pair's
    feature here as well; this check is what guarantees it has not.

    Args:
        extreme: Whether RSI is expected outside its middle range.
        low: Oversold boundary.
        high: Overbought boundary.
        run_limit: Run length that would count as an extended trend.

    Returns:
        A check function.
    """

    def check(frames: Frames) -> tuple[bool, str]:
        from stock_agent.eval.synthetic import verify_rsi

        rsi = verify_rsi(frames[TICKER])
        length, colour = verify_run(frames[TICKER])
        found = rsi <= low or rsi >= high
        minimal = length < run_limit
        detail = f"RSI {rsi:.0f}, run of {length} {colour} candles"
        return (found == extreme and minimal), detail

    return check


def _check_segments(present: bool) -> Callable[[Frames], tuple[bool, str]]:
    """Build a check on whether the series holds more than one regime.

    The segmenter is the slowest thing in the project, so this check uses a
    reduced permutation count. It establishes that a change is or is not
    there, which is all a scenario label claims.

    Args:
        present: Whether a regime change is expected.

    Returns:
        A check function.
    """

    def check(frames: Frames) -> tuple[bool, str]:
        from stock_agent.eval.synthetic import verify_regime_change

        pivots, current = verify_regime_change(frames[TICKER])
        return (pivots >= 1) == present, f"{pivots} regime changes, now {current}"

    return check


# --- the scenarios ---------------------------------------------------------

# Base seeds are chosen because verify_all passes on them, not for appearance.
# Seed 1 is verified divergence-free, which the negative halves depend on.

_TREND_REQUIRED = frozenset({"trend.heiken_runs"})
_MOMENTUM = "momentum.rsi_stochastic"

SCENARIOS: tuple[Scenario, ...] = (
    # --- pair 1: an extended trend run -----------------------------------
    Scenario(
        name="extended_run",
        pair="trend",
        half="present",
        description="nine consecutive green Heiken Ashi candles planted",
        build=lambda: _with_market(
            plant_run(_base(400, 1, 0.30, 0.18), 9, "green"), _benchmark(400)
        ),
        required=frozenset({"trend.heiken_runs"}),
        forbidden=frozenset({EXPENSIVE}),
        pivotal="trend.heiken_runs",
        check=_check_run(True),
    ),
    Scenario(
        name="no_extended_run",
        pair="trend",
        half="absent",
        description="the same series with no run planted",
        build=_plain(400, 1, 0.30, 0.18),
        required=frozenset(),
        forbidden=frozenset({EXPENSIVE}),
        check=_check_run(False),
    ),
    # --- pair 2: RSI divergence -------------------------------------------
    Scenario(
        name="divergence_present",
        pair="divergence",
        half="present",
        description="two troughs planted so price makes a lower low and RSI a higher low",
        build=lambda: _with_market(plant_divergence(_base(400, 2, 0.08, 0.14)), _benchmark(400)),
        # The divergence detector needs an RSI column, so an arm that routes
        # to it without momentum has not actually reached the measurement.
        required=frozenset({"pattern.rsi_divergence", _MOMENTUM}),
        forbidden=frozenset({EXPENSIVE}),
        pivotal="pattern.rsi_divergence",
        check=_check_divergence(True),
    ),
    Scenario(
        name="divergence_absent",
        pair="divergence",
        half="absent",
        description="the same base series, verified to produce no divergence",
        build=_plain(400, 2, 0.08, 0.14),
        required=frozenset(),
        forbidden=frozenset({EXPENSIVE}),
        check=_check_divergence(False),
    ),
    # --- pair 3: a volume surge -------------------------------------------
    Scenario(
        name="volume_surge",
        pair="volume",
        half="present",
        description="final five bars at six times their usual volume",
        build=lambda: _with_market(plant_volume_surge(_base(400, 4)), _benchmark(400)),
        required=frozenset({"volume.surge"}),
        forbidden=frozenset({EXPENSIVE}),
        pivotal="volume.surge",
        check=_check_volume(True),
    ),
    Scenario(
        name="volume_normal",
        pair="volume",
        half="absent",
        description="the same series at ordinary volume",
        build=_plain(400, 4),
        required=frozenset(),
        forbidden=frozenset({EXPENSIVE}),
        check=_check_volume(False),
    ),
    # --- pair 4: a volatility spike ---------------------------------------
    Scenario(
        name="volatility_spike",
        pair="volatility",
        half="present",
        description="a calm series whose last fifty bars turn sharply volatile",
        build=lambda: _with_market(
            synth_ohlc(400, seed=5, segments=[(350, 0.10, 0.12), (50, -0.30, 0.55)]),
            _benchmark(400),
        ),
        required=frozenset({"volatility.realised"}),
        forbidden=frozenset({EXPENSIVE}),
        pivotal="volatility.realised",
        check=_check_volatility(True),
    ),
    Scenario(
        name="volatility_calm",
        pair="volatility",
        half="absent",
        description="the same series with no change in volatility",
        build=lambda: _with_market(
            synth_ohlc(400, seed=5, segments=[(350, 0.10, 0.12), (50, 0.10, 0.12)]),
            _benchmark(400),
        ),
        required=frozenset(),
        forbidden=frozenset({EXPENSIVE}),
        check=_check_volatility(False),
    ),
    # --- pair 5: a momentum extreme ---------------------------------------
    Scenario(
        name="momentum_oversold",
        pair="momentum",
        half="present",
        description="five bars down three percent each, driving RSI into oversold",
        build=lambda: _with_market(plant_momentum_push(_base(400, 2, 0.0, 0.14)), _benchmark(400)),
        required=frozenset({_MOMENTUM}),
        forbidden=frozenset({EXPENSIVE}),
        pivotal=_MOMENTUM,
        check=_check_momentum(True),
    ),
    Scenario(
        name="momentum_neutral",
        pair="momentum",
        half="absent",
        description="the same series with RSI in the middle of its range",
        build=_plain(400, 2, 0.0, 0.14),
        required=frozenset(),
        forbidden=frozenset({EXPENSIVE}),
        check=_check_momentum(False),
    ),
    # --- pair 6: strength against the benchmark ---------------------------
    Scenario(
        name="lagging_benchmark",
        pair="relative_strength",
        half="present",
        description="a declining series against an advancing benchmark",
        build=lambda: _with_market(
            synth_ohlc(400, seed=3, drift_ann=-0.35, vol_ann=0.30), _benchmark(400)
        ),
        required=frozenset({"relative_strength.beta_regime"}),
        forbidden=frozenset({EXPENSIVE}),
        pivotal="relative_strength.beta_regime",
        check=_check_relative("risk-off"),
    ),
    Scenario(
        name="leading_benchmark",
        pair="relative_strength",
        half="absent",
        description="a series advancing faster than its benchmark",
        build=lambda: _with_market(
            synth_ohlc(400, seed=2, drift_ann=0.45, vol_ann=0.20), _benchmark(400)
        ),
        required=frozenset(),
        forbidden=frozenset({EXPENSIVE}),
        check=_check_relative("risk-on"),
    ),
    # --- controls ----------------------------------------------------------
    Scenario(
        name="short_history",
        pair=None,
        half="control",
        description="forty bars, so most analyses are gated out before any choice",
        build=lambda: _with_market(_base(40, 6), _benchmark(40)),
        required=frozenset(),
        forbidden=frozenset(),
        bars=40,
    ),
    Scenario(
        name="featureless",
        pair=None,
        half="control",
        description="a quiet drift with nothing planted in it at all",
        build=_plain(400, 7, 0.05, 0.10),
        required=frozenset(),
        # Nothing here is the right answer, so nothing is the wrong one
        # either. What this scenario measures is how much effort an arm
        # spends when there is nothing to find.
        forbidden=frozenset(),
        check=_check_divergence(False),
    ),
    Scenario(
        name="several_features",
        pair=None,
        half="control",
        description="a divergence, a volume surge and a volatility spike together",
        build=lambda: _with_market(
            plant_volume_surge(
                plant_divergence(
                    synth_ohlc(
                        400,
                        seed=1,
                        segments=[(350, 0.10, 0.12), (50, -0.30, 0.45)],
                    )
                )
            ),
            _benchmark(400),
        ),
        required=frozenset(
            {
                "pattern.rsi_divergence",
                _MOMENTUM,
                "volume.surge",
                "volatility.realised",
            }
        ),
        pivotal="pattern.rsi_divergence",
        check=_check_divergence(True),
    ),
)


def by_name(name: str) -> Scenario:
    """Look a scenario up.

    Args:
        name: Scenario name.

    Returns:
        The scenario.

    Raises:
        KeyError: If no scenario has that name.
    """
    for scenario in SCENARIOS:
        if scenario.name == name:
            return scenario
    raise KeyError(f"unknown scenario {name!r}; have {[s.name for s in SCENARIOS]}")


def pairs() -> dict[str, tuple[Scenario, ...]]:
    """Group the minimal pairs.

    Returns:
        Scenarios by pair identifier, controls excluded.
    """
    grouped: dict[str, list[Scenario]] = {}
    for scenario in SCENARIOS:
        if scenario.pair is not None:
            grouped.setdefault(scenario.pair, []).append(scenario)
    return {k: tuple(v) for k, v in grouped.items()}


def verify_all() -> list[tuple[str, bool, str]]:
    """Check every scenario against the production detectors.

    Returns:
        One row per scenario: its name, whether it is what it claims, and what
        the detector reported.
    """
    return [(s.name, *s.verify()) for s in SCENARIOS]
