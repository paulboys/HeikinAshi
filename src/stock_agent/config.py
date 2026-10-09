"""Tunable policy for the routing agent.

Every threshold the agent acts on lives here so experiments change
configuration rather than code.  Defaults are starting hypotheses, not
settled constants: JEV's probabilities are known to be miscalibrated in a
set-dependent way, so these numbers are policy knobs and the evaluation
harness measures how sensitive the agent is to them.

Public API:
    PolicyConfig, BudgetConfig, JevConfig, AgentConfig
    load_config(path: Path | None = None, overrides: Sequence[str] = ()) -> AgentConfig
"""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Literal

# Every tunable setting is one of these; naming the union keeps the override
# parser honest without falling back to Any.
SettingValue = bool | int | float | str | Path

__all__ = [
    "AgentConfig",
    "BudgetConfig",
    "JevConfig",
    "PolicyConfig",
    "SettingValue",
    "load_config",
]

OFFICIAL_ENDPOINT = "https://api.typesafe.ai/v1/systemone"

# Pinned rather than "jev-latest": every behaviour this agent is designed
# around -- Choice option-order bias, latency being flat in question count,
# set-dependent miscalibration -- was measured on this model. Routing on a
# moving alias would make the benchmark unreproducible.
#
# The patch segment is required: "jev-1.13" is rejected with HTTP 400,
# "jev-1.13.0" is accepted. Verified against the live endpoint.
DEFAULT_MODEL = "jev-1.13.0"


@dataclass(frozen=True)
class PolicyConfig:
    """Thresholds governing how JEV's probabilities turn into actions.

    Attributes:
        act_threshold: Run the top-ranked tool outright at or above this,
            when routing on the absolute usefulness question.
        rank_act_threshold: The same band for the comparative question, whose
            answers live on a different scale: "would this help" sat near
            0.74 across benchmarks 2 and 3, while "is this the best of the
            field" sits near 0.42, so 0.65 made the act band unreachable.
            0.50 is the one privileged point on a probability-of-being-best
            scale -- more likely than not the right choice -- rather than a
            value fitted to any measurement.
        consider_threshold: Floor of the grey band; below this nothing runs.
            Read against the *gate* map, which answers whether anything is
            worth running at all. The comparative question cannot answer
            that, only which candidate wins.
        stop_threshold: Probability of sufficiency required to stop.
        conflict_veto: Probability of contradiction that inhibits stopping.
        margin_min: Minimum gap between the top two tools to count as decided.
        indecision_limit: Consecutive indecisive iterations before giving up.
        min_tools_before_stop: Tools that must have run before stopping.
        max_corun: Tools that may run in a single iteration.
        require_price_history: Fetch prices on iteration zero without asking.
        selector: Which question actuates routing; the other is shadowed.
    """

    act_threshold: float = 0.65
    rank_act_threshold: float = 0.50
    consider_threshold: float = 0.40
    stop_threshold: float = 0.70
    conflict_veto: float = 0.60
    margin_min: float = 0.10
    indecision_limit: int = 2
    min_tools_before_stop: int = 2
    max_corun: int = 2
    require_price_history: bool = True
    selector: Literal["noul", "choice_balanced"] = "noul"

    def __post_init__(self) -> None:
        """Reject incoherent threshold orderings.

        Raises:
            ValueError: If a probability is outside [0, 1], the bands are out
                of order, or a count is below its minimum.
        """
        for name in (
            "act_threshold",
            "rank_act_threshold",
            "consider_threshold",
            "stop_threshold",
            "conflict_veto",
            "margin_min",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {value}")
        if self.consider_threshold > self.act_threshold:
            raise ValueError(
                f"consider_threshold ({self.consider_threshold}) must not exceed "
                f"act_threshold ({self.act_threshold})"
            )
        if self.indecision_limit < 1:
            raise ValueError(f"indecision_limit must be >= 1, got {self.indecision_limit}")
        if self.max_corun < 1:
            raise ValueError(f"max_corun must be >= 1, got {self.max_corun}")
        if self.min_tools_before_stop < 0:
            raise ValueError(
                f"min_tools_before_stop must be >= 0, got {self.min_tools_before_stop}"
            )
        if self.selector not in ("noul", "choice_balanced"):
            raise ValueError(f"unknown selector {self.selector!r}")


@dataclass(frozen=True)
class BudgetConfig:
    """Hard caps that bound a run regardless of what JEV returns.

    Attributes:
        max_iterations: Decision rounds.
        max_tool_calls: Total tool executions, including prerequisites.
        max_same_tool_calls: Executions of any one tool.
        max_jev_calls: Requests to the decision model.
        max_wall_seconds: Total runtime, checked between rounds.
        max_network_seconds: Deadline for one networked tool. The caps above
            all count calls and are tested between rounds, so none of them can
            end a single tool that blocks -- and the first live run sat inside
            the macro snapshot for twelve minutes before being killed by hand.
            This is the only bound that applies while a tool is still running.
        max_network_calls: Outbound data fetches.
        max_consecutive_tool_errors: Failures in a row before abandoning.
    """

    max_iterations: int = 8
    max_tool_calls: int = 12
    max_same_tool_calls: int = 2
    max_jev_calls: int = 10
    max_wall_seconds: float = 120.0
    max_network_seconds: float = 45.0
    max_network_calls: int = 20
    max_consecutive_tool_errors: int = 3

    def __post_init__(self) -> None:
        """Reject non-positive budgets.

        Raises:
            ValueError: If any cap is below its minimum.
        """
        for name in fields(self):
            value = getattr(self, name.name)
            if value <= 0:
                raise ValueError(f"{name.name} must be > 0, got {value}")


@dataclass(frozen=True)
class JevConfig:
    """Connection settings for the decision model.

    The API key is never held here; it is read from the environment or the
    gitignored .env at call time and bound to its endpoint.

    Attributes:
        endpoint: Full URL of the decision endpoint.
        model: Model identifier sent with every request.
        timeout_s: Per-request timeout.
        max_retries: Attempts before giving up on a request.
        retry_backoff: Exponential backoff base between attempts.
    """

    endpoint: str = OFFICIAL_ENDPOINT
    model: str = DEFAULT_MODEL
    timeout_s: float = 30.0
    max_retries: int = 2
    retry_backoff: float = 1.5


@dataclass(frozen=True)
class AgentConfig:
    """Everything tunable about a run.

    Attributes:
        policy: Routing thresholds.
        budget: Hard caps.
        jev: Decision-model connection settings.
        trace_dir: Where decision traces are written.
        interval: Default bar aggregation.
        default_bars: Bars of history requested by default.
    """

    policy: PolicyConfig = field(default_factory=PolicyConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    jev: JevConfig = field(default_factory=JevConfig)
    trace_dir: Path = Path("runs")
    interval: str = "1d"
    default_bars: int = 504

    def to_dict(self) -> dict[str, Any]:
        """Render the configuration for the trace.

        Returns:
            A JSON-safe mapping of every setting.
        """
        return {
            "policy": {f.name: getattr(self.policy, f.name) for f in fields(self.policy)},
            "budget": {f.name: getattr(self.budget, f.name) for f in fields(self.budget)},
            "jev": {f.name: getattr(self.jev, f.name) for f in fields(self.jev)},
            "trace_dir": str(self.trace_dir),
            "interval": self.interval,
            "default_bars": self.default_bars,
        }


_SECTIONS: dict[str, type] = {
    "policy": PolicyConfig,
    "budget": BudgetConfig,
    "jev": JevConfig,
}


def _coerce(current: SettingValue, text: str) -> SettingValue:
    """Convert an override string to the type of the value it replaces.

    Args:
        current: Existing value, whose type is the target.
        text: Raw override text.

    Returns:
        The converted value.

    Raises:
        ValueError: If the text cannot be converted.
    """
    if isinstance(current, bool):
        lowered = text.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
        raise ValueError(f"cannot read {text!r} as a boolean")
    if isinstance(current, int) and not isinstance(current, bool):
        return int(text)
    if isinstance(current, float):
        return float(text)
    if isinstance(current, Path):
        # Without this, --set trace_dir=... leaves a plain string behind and
        # the first path join raises, which is how it was found.
        return Path(text)
    return text


def _apply_overrides(config: AgentConfig, overrides: Sequence[str]) -> AgentConfig:
    """Apply ``section.key=value`` strings to a configuration.

    Args:
        config: Starting configuration.
        overrides: Override expressions.

    Returns:
        The updated configuration.

    Raises:
        ValueError: If an expression is malformed or names an unknown setting.
    """
    updates: dict[str, dict[str, Any]] = {name: {} for name in _SECTIONS}
    top: dict[str, Any] = {}

    for item in overrides:
        if "=" not in item:
            raise ValueError(f"override must be section.key=value, got {item!r}")
        dotted, _, raw = item.partition("=")
        parts = dotted.strip().split(".")
        if len(parts) == 1:
            key = parts[0]
            if not hasattr(config, key):
                raise ValueError(f"unknown setting {dotted!r}")
            top[key] = _coerce(getattr(config, key), raw)
            continue
        if len(parts) != 2 or parts[0] not in _SECTIONS:
            raise ValueError(f"unknown setting {dotted!r}")
        section, key = parts
        current = getattr(config, section)
        if not hasattr(current, key):
            raise ValueError(f"unknown setting {dotted!r}")
        updates[section][key] = _coerce(getattr(current, key), raw)

    changed: dict[str, Any] = dict(top)
    for section, values in updates.items():
        if values:
            changed[section] = replace(getattr(config, section), **values)
    return replace(config, **changed) if changed else config


def load_config(
    path: Path | None = None,
    overrides: Sequence[str] = (),
) -> AgentConfig:
    """Build a configuration from defaults, an optional file and overrides.

    Args:
        path: Optional TOML file with ``[policy]`` / ``[budget]`` / ``[jev]``
            tables and optional top-level keys.
        overrides: ``section.key=value`` expressions applied last.

    Returns:
        The resolved configuration.

    Raises:
        ValueError: If the file or an override names an unknown setting.
        FileNotFoundError: If ``path`` is given but does not exist.
    """
    config = AgentConfig()

    if path is not None:
        if not path.exists():
            raise FileNotFoundError(f"config file not found: {path}")
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        changed: dict[str, Any] = {}
        for section, cls in _SECTIONS.items():
            if section in data:
                known = {f.name for f in fields(cls)}
                unknown = set(data[section]) - known
                if unknown:
                    raise ValueError(f"unknown {section} settings: {sorted(unknown)}")
                changed[section] = replace(getattr(config, section), **data[section])
        if "trace_dir" in data:
            changed["trace_dir"] = Path(data["trace_dir"])
        for key in ("interval", "default_bars"):
            if key in data:
                changed[key] = data[key]
        config = replace(config, **changed)

    return _apply_overrides(config, overrides)
