"""The arms that are not the decision model.

All four arms answer the same question set through the same interface, and
their answers go through the same policy, the same guards and the same
registry. The comparison therefore isolates exactly one thing: how usefulness
is scored. Nothing else differs, so a difference in outcome cannot come from
one arm getting a different loop.

The arms:

``rules`` (A)
    A decision tree assembled from the domain logic already in this
    repository. **It is deliberately given more than the decision model
    gets**: it reads the numeric state directly, while the model sees only
    the rendered text. Handicapping the baseline would make the hypothesis
    easy to confirm and the result worthless, so the asymmetry runs the other
    way on purpose.

``cheapest`` (A-prime)
    Cheapest applicable analysis first, always, and never stops early. A
    floor: routing that cannot beat this is adding nothing.

``random`` (R)
    Seeded uniform scores. The other floor: routing that cannot beat this is
    not routing.

``oracle``
    Not a competitor. It is told each scenario's expectations, so it shows
    what a near-perfect score looks like. Its purpose is to prove the metrics
    can detect good routing before they are pointed at anything real.

Public API:
    CheapestFirstClient, OracleClient, RandomClient, RuleBasedClient
    build_arm(name, scenario=None, seed=0) -> DecisionModel
    ARM_NAMES
"""

from __future__ import annotations

import random
import zlib
from collections.abc import Iterable, Mapping
from typing import Any

from stock_agent.eval.scenarios import Scenario
from stock_agent.jev.answers import JevResponse, parse_answers
from stock_agent.jev.questions import (
    CONVICTION_QID,
    STOP_CONFLICT_QID,
    STOP_ENOUGH_QID,
    tool_for_qid,
)
from stock_agent.state import AnalysisState

__all__ = [
    "ARM_NAMES",
    "Arm",
    "CheapestFirstClient",
    "OracleClient",
    "RandomClient",
    "RuleBasedClient",
    "build_arm",
]

ARM_NAMES = ("rules", "cheapest", "random", "oracle", "jev")

_USEFUL_PREFIX = "useful__"

# Probabilities are chosen to land in the policy's bands rather than to look
# like beliefs: above act (0.65) means run it, between consider (0.40) and act
# means run it when nothing better is offered, below means leave it.
_ACT = 0.88
_LIKELY = 0.72
_CONSIDER = 0.50
_LEAVE = 0.12


class Arm:
    """Shared plumbing: answer a question set in the real response shape."""

    name = "arm"

    def __init__(self, model: str | None = None) -> None:
        """Create an arm.

        Args:
            model: Name reported on each response; defaults to the arm's name.
        """
        self.model = model or self.name
        self.endpoint = f"arm://{self.name}"
        self.calls = 0
        self.dry_run = False
        self.requests: list[dict[str, Any]] = []
        self.state: AnalysisState | None = None

    def __repr__(self) -> str:
        """Render the arm.

        Returns:
            A short description.
        """
        return f"{type(self).__name__}(calls={self.calls})"

    def observe(self, state: AnalysisState) -> None:
        """Receive the numeric state before being asked.

        The decision model does not implement this, so it never sees more
        than the rendered text. The baselines do, which is what keeps them
        from being straw men.

        Args:
            state: The analysis so far.
        """
        self.state = state

    def build_body(
        self,
        state: str,
        questions: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Assemble a request body in the real shape.

        Args:
            state: The compact textual state.
            questions: Question identifier to definition.

        Returns:
            The body.
        """
        return {"state": state, "model": self.model, "questions": dict(questions)}

    def ask(
        self,
        state: str,
        questions: Mapping[str, Mapping[str, Any]],
    ) -> JevResponse:
        """Answer a question set.

        Args:
            state: The compact textual state.
            questions: Question identifier to definition.

        Returns:
            A response in the same shape the real client produces.
        """
        self.calls += 1
        self.requests.append(self.build_body(state, questions))

        # These arms answer only the absolute question. They have one scoring
        # function and no comparative judgement to make, so leaving the
        # comparative questions unanswered is the truthful thing to do -- and
        # it is what keeps them comparable: the loop then routes them on the
        # absolute map at the absolute act threshold, exactly as before the
        # comparative question existed. The unanswered identifiers are
        # recorded in the trace's "missing" list.
        tools = [q for q in questions if q.startswith(_USEFUL_PREFIX)]
        raw: dict[str, Any] = {qid: {"noul": self.score(tool_for_qid(qid))} for qid in tools}
        raw[STOP_ENOUGH_QID] = {"noul": self.enough([tool_for_qid(q) for q in tools])}
        # No arm here reasons about contradiction; saying so beats inventing a
        # number the policy would then act on.
        raw[STOP_CONFLICT_QID] = {"noul": 0.0}
        raw[CONVICTION_QID] = {"score": 2, "confidence": 0.5}

        parsed, missing, malformed = parse_answers(raw, questions)
        return JevResponse(
            answers=parsed,
            missing=missing,
            malformed=malformed,
            raw={"answers": raw},
            latency_s=0.0,
            usage=None,
            endpoint=self.endpoint,
            model=self.model,
            attempts=1,
            http_status=None,
            wrapper_key="answers",
            error=None if parsed else "every answer was missing or malformed",
            model_served=self.model,
        )

    # -- what each arm overrides -------------------------------------------

    def score(self, tool: str) -> float:
        """Score one analysis.

        Args:
            tool: Tool name.

        Returns:
            A probability that running it would add information.
        """
        raise NotImplementedError

    def enough(self, offered: Iterable[str]) -> float:
        """Judge whether the evidence already supports a conclusion.

        Args:
            offered: Tools still on the menu.

        Returns:
            A probability.
        """
        raise NotImplementedError

    # -- helpers for the subclasses ----------------------------------------

    def _value(self, key: str, default: float | None = None) -> float | None:
        """Read a numeric observation.

        Args:
            key: Observation key.
            default: Value returned when absent or non-numeric.

        Returns:
            The number, or the default.
        """
        if self.state is None:
            return default
        found = self.state.value(key)
        if isinstance(found, bool) or not isinstance(found, (int, float)):
            return default
        return float(found)

    def _label(self, key: str) -> str:
        """Read a textual observation.

        Args:
            key: Observation key.

        Returns:
            The string, or an empty one.
        """
        if self.state is None:
            return ""
        found = self.state.value(key)
        return found if isinstance(found, str) else ""

    def _measured(self) -> set[str]:
        """List the analyses that have already produced measurements.

        Returns:
            Tool names.
        """
        return set() if self.state is None else set(self.state.tools_run())


class RuleBasedClient(Arm):
    """A decision tree built from this repository's own domain logic.

    The rules are the ones the repo's scripts and screeners already encode:
    cheap context first; look for divergence once momentum is extreme; read
    the volatility index once realised volatility has risen; compare against
    the benchmark once a drawdown is deep; and leave the expensive
    segmentation alone unless nothing else has fired.
    """

    name = "rules"

    # Measured first on every path: all three are near-free and every later
    # rule is written in terms of what they produce.
    _CONTEXT = ("trend.heiken_runs", "momentum.rsi_stochastic", "volatility.realised")

    def score(self, tool: str) -> float:
        """Score one analysis against the rule set.

        Args:
            tool: Tool name.

        Returns:
            A probability.
        """
        measured = self._measured()
        if tool in self._CONTEXT:
            return _ACT

        rsi = self._value("momentum.rsi")
        vol_ratio = self._value("volatility.ratio")
        drawdown = self._value("volatility.max_drawdown_pct")
        volume_known = "volume.surge" in measured

        if tool == "volume.surge":
            # Cheap, and a surge changes how every other reading is taken.
            return _LIKELY

        if tool == "pattern.rsi_divergence":
            if rsi is None:
                # Its prerequisite has not run; the policy will pull momentum
                # in, but there is no reason to reach for it yet.
                return _CONSIDER
            if rsi >= 70.0 or rsi <= 30.0:
                return _ACT
            # Still worth running even at a middling reading. A divergence
            # whose RSI has already recovered is invisible to an
            # extremes-only rule -- the planted divergence scenario ends at
            # RSI 57 -- and the check costs under a tenth of a second. A
            # baseline that skipped it here would be a straw man.
            return _LIKELY

        if tool == "volatility.vix":
            if vol_ratio is not None and vol_ratio >= 1.4:
                return _ACT
            if drawdown is not None and drawdown <= -15.0:
                return _LIKELY
            return _LEAVE

        if tool == "relative_strength.beta_regime":
            if drawdown is not None and drawdown <= -10.0:
                return _ACT
            return _CONSIDER

        if tool == "signal.mcglone":
            # Only once its three inputs exist; otherwise it cannot resolve.
            inputs = {
                "relative_strength.beta_regime",
                "volatility.vix",
                "volatility.realised",
            }
            return _ACT if inputs <= measured else _LEAVE

        if tool == "market_regime.price":
            # The expensive one. Justified only when the cheap analyses have
            # run and none of them found anything.
            quiet = (
                rsi is not None
                and 35.0 < rsi < 65.0
                and vol_ratio is not None
                and vol_ratio < 1.4
                and volume_known
            )
            bars = self._value("ohlc.n_bars", 0.0) or 0.0
            return _CONSIDER if (quiet and bars >= 250) else _LEAVE

        if tool == "events.insider":
            return _CONSIDER

        if tool == "macro.snapshot":
            # Whole-market context; informative but not about this ticker.
            return _LEAVE

        return _CONSIDER

    def enough(self, offered: Iterable[str]) -> float:
        """Stop once nothing on the menu still clears the act band.

        Args:
            offered: Tools still available.

        Returns:
            A probability.
        """
        if not self._CONTEXT or not (set(self._CONTEXT) <= self._measured()):
            return 0.0
        return 0.0 if any(self.score(t) >= _LIKELY for t in offered) else 0.95


class CheapestFirstClient(Arm):
    """Always the cheapest applicable analysis, and never an early stop."""

    name = "cheapest"

    def __init__(self, costs: Mapping[str, float] | None = None) -> None:
        """Create the arm.

        Args:
            costs: Estimated seconds per tool. Taken from the registry when
                omitted, so the ordering reflects real cost rather than a
                guess.
        """
        super().__init__()
        if costs is None:
            from stock_agent.tools.builtin import build_registry

            costs = {s.name: s.cost.est_seconds for s in build_registry().implemented()}
        self.costs = dict(costs)

    def score(self, tool: str) -> float:
        """Score inversely to cost.

        Args:
            tool: Tool name.

        Returns:
            A probability, higher for cheaper analyses.
        """
        seconds = self.costs.get(tool, 1.0)
        # Maps roughly 0.01s -> 0.95 and 9s -> 0.45, so the ordering is by
        # cost while everything stays above the consider band: this arm
        # declines nothing, it only sequences.
        return max(_CONSIDER - 0.05, min(0.95, 0.95 - 0.11 * (seconds**0.5)))

    def enough(self, offered: Iterable[str]) -> float:
        """Never stop while anything remains.

        Args:
            offered: Tools still available.

        Returns:
            Zero while the menu is non-empty.
        """
        return 0.0 if list(offered) else 1.0


class RandomClient(Arm):
    """Seeded uniform scores, reproducible run to run."""

    name = "random"

    def __init__(self, seed: int = 0, stop_rate: float = 0.35) -> None:
        """Create the arm.

        Args:
            seed: Seed for the generator.
            stop_rate: Chance per round of declaring the evidence sufficient.
                High enough that this arm usually stops before exhausting the
                menu: an arm that always runs everything is exhaustive, not
                random, and would be no floor at all.
        """
        super().__init__()
        self.seed = seed
        self.stop_rate = stop_rate
        self._rng = random.Random(seed)

    def score(self, tool: str) -> float:
        """Draw a uniform score.

        Args:
            tool: Tool name, unused.

        Returns:
            A probability.
        """
        return self._rng.random()

    def enough(self, offered: Iterable[str]) -> float:
        """Stop at a fixed rate per round.

        Args:
            offered: Tools still available, unused.

        Returns:
            A probability drawn from the same generator.
        """
        return 0.95 if self._rng.random() < self.stop_rate else 0.0


class OracleClient(Arm):
    """Told the answer. Exists to show what a near-perfect score looks like.

    This is not an arm the hypothesis competes against. If the metrics cannot
    separate this from :class:`RandomClient`, they are not measuring routing
    and no comparison built on them means anything.
    """

    name = "oracle"

    def __init__(self, required: Iterable[str], forbidden: Iterable[str] = ()) -> None:
        """Create the arm.

        Args:
            required: Analyses the scenario expects to be run.
            forbidden: Analyses the scenario counts as wasted.
        """
        super().__init__()
        self.required = frozenset(required)
        self.forbidden = frozenset(forbidden)

    def score(self, tool: str) -> float:
        """Score the expected analyses high and everything else low.

        Args:
            tool: Tool name.

        Returns:
            A probability.
        """
        if tool in self.required:
            return 0.97
        if tool in self.forbidden:
            return 0.01
        return _LEAVE

    def enough(self, offered: Iterable[str]) -> float:
        """Stop as soon as every expected analysis has run.

        Args:
            offered: Tools still available, unused.

        Returns:
            A probability.
        """
        return 0.95 if self.required <= self._measured() else 0.0


def build_arm(
    name: str,
    scenario: Scenario | None = None,
    seed: int = 0,
) -> Arm:
    """Construct an arm by name.

    Args:
        name: One of ``rules``, ``cheapest``, ``random`` or ``oracle``.
        scenario: Required by the oracle, which needs its expectations.
        seed: Seed for the random arm.

    Returns:
        The arm.

    Raises:
        ValueError: If the name is unknown, or the oracle is asked for with no
            scenario to be an oracle about.
    """
    if name == "rules":
        return RuleBasedClient()
    if name == "cheapest":
        return CheapestFirstClient()
    if name == "random":
        # Seeded per scenario, not once for the whole benchmark. With one
        # seed the generator hands out the same draw at the same call
        # position, so both halves of a minimal pair got identical scores and
        # the arm registered "no preference" through determinism rather than
        # through chance -- a floor of exactly zero instead of the coin-flip
        # it should be. crc32 rather than hash() so it is stable across runs.
        offset = zlib.crc32(scenario.name.encode("utf-8")) if scenario else 0
        return RandomClient(seed=seed ^ offset)
    if name == "oracle":
        if scenario is None:
            raise ValueError("the oracle arm needs a scenario to read expectations from")
        return OracleClient(scenario.required, scenario.forbidden)
    raise ValueError(f"unknown arm {name!r}; have {ARM_NAMES}")
