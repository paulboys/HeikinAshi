"""The questions the agent asks about what to do next.

Design follows three measured properties of the model, not guesswork:

1. **A Choice leans toward whichever option is listed first.** So routing is
   decided by one independent ``noul`` per candidate tool, which has no option
   list and therefore no order to be biased by. A Choice is still asked, in
   both option orders and averaged, but only as a shadow: recorded, compared,
   never acted on.
2. **Latency barely grows with the number of questions**, and each is
   evaluated in isolation against the same state. So asking one question per
   tool in a single request costs about what one question costs -- the
   unbiased design is also the cheap one.
3. **Probabilities are miscalibrated in a set-dependent way.** So the policy
   acts on rankings and fixed bands, never on a probability as a belief, and
   the harness measures calibration rather than assuming it.

Every judgement is split into its own single-condition question, following
the model vendor's own guidance that a judgement depending on several things
is best asked as one question per thing.

Routing moved off the usefulness question in benchmark 4. It asks whether an
analysis *would add information*, which is true for nearly every candidate at
nearly every round, so the answers were flat by construction rather than by
inattention. :func:`best_next_question` asks instead whether a candidate is
the best of the field -- a proposition at most one of them can satisfy. Both
are asked in every request; only the comparative one routes.

Public API:
    usefulness_qid(tool: str) -> str
    tool_for_qid(qid: str) -> str
    usefulness_question(spec, objective) -> dict
    best_next_qid(tool: str) -> str
    tool_for_best_next_qid(qid: str) -> str
    best_next_question(spec, objective) -> dict
    build_question_set(specs, objective, shadow_choice=True) -> dict
    STOP_ENOUGH_QID, STOP_CONFLICT_QID, CONVICTION_QID
    SELECT_FWD_QID, SELECT_REV_QID
    average_choice_probabilities(forward, reverse) -> dict[str, float]
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from stock_agent.registry import ToolSpec

__all__ = [
    "CONVICTION_QID",
    "SELECT_FWD_QID",
    "SELECT_REV_QID",
    "STOP_CONFLICT_QID",
    "STOP_ENOUGH_QID",
    "average_choice_probabilities",
    "best_next_qid",
    "best_next_question",
    "build_question_set",
    "tool_for_best_next_qid",
    "tool_for_qid",
    "usefulness_qid",
    "usefulness_question",
]

STOP_ENOUGH_QID = "stop_enough"
STOP_CONFLICT_QID = "stop_conflict"
CONVICTION_QID = "conviction"
SELECT_FWD_QID = "select_fwd"
SELECT_REV_QID = "select_rev"

_USEFUL_PREFIX = "useful__"

# Deliberately not a prefix of _USEFUL_PREFIX, nor it of this: the mock arms
# and the baselines select their questions by ``startswith``, so an
# overlapping prefix would silently make one question answer the other.
_BEST_PREFIX = "best__"

_CTX = (
    "The state describes one stock and the financial analyses already run on it. "
    "Analyses listed under MEASURED SO FAR have already been computed. Analyses "
    "listed under NOT YET MEASURED could still be run. Analyses listed under "
    "UNAVAILABLE cannot be run at all."
)


def usefulness_qid(tool: str) -> str:
    """Build the question identifier for a tool's usefulness question.

    Dots are replaced because identifier character restrictions upstream are
    unverified; the mapping stays reversible.

    Args:
        tool: Dotted tool name.

    Returns:
        The question identifier.
    """
    return f"{_USEFUL_PREFIX}{tool.replace('.', '__')}"


def tool_for_qid(qid: str) -> str:
    """Recover a tool name from its usefulness question identifier.

    Args:
        qid: Question identifier.

    Returns:
        The dotted tool name.

    Raises:
        ValueError: If the identifier is not a usefulness question.
    """
    if not qid.startswith(_USEFUL_PREFIX):
        raise ValueError(f"{qid!r} is not a usefulness question identifier")
    return qid[len(_USEFUL_PREFIX) :].replace("__", ".")


def usefulness_question(spec: ToolSpec, objective: str) -> dict[str, Any]:
    """Ask whether one analysis would add anything.

    The question is about *marginal* information given what has already been
    measured, not about whether the analysis is good in the abstract --
    otherwise a useful tool scores highly even once its answer is known.

    Args:
        spec: The analysis under consideration.
        objective: What the overall analysis is for.

    Returns:
        A noul question definition.
    """
    return {
        "type": "noul",
        "instructions": (
            f'{_CTX} The analysis under consideration is "{spec.title}": '
            f"{spec.jev_description} Return the probability that running this "
            f"analysis next would change or sharpen the conclusion about "
            f"{objective}, given what has already been measured."
        ),
        "criteria": {
            "true": (
                f'Running "{spec.title}" would add information that is not already '
                f"implied by the measurements under MEASURED SO FAR, and that bears "
                f"on the objective."
            ),
            "false": (
                f'Running "{spec.title}" would be redundant, irrelevant to the '
                f"objective, or would restate something the existing measurements "
                f"already settle."
            ),
        },
    }


def best_next_qid(tool: str) -> str:
    """Build the question identifier for a tool's best-next question.

    Args:
        tool: Dotted tool name.

    Returns:
        The question identifier.
    """
    return f"{_BEST_PREFIX}{tool.replace('.', '__')}"


def tool_for_best_next_qid(qid: str) -> str:
    """Recover a tool name from its best-next question identifier.

    Args:
        qid: Question identifier.

    Returns:
        The dotted tool name.

    Raises:
        ValueError: If the identifier is not a best-next question.
    """
    if not qid.startswith(_BEST_PREFIX):
        raise ValueError(f"{qid!r} is not a best-next question identifier")
    return qid[len(_BEST_PREFIX) :].replace("__", ".")


def best_next_question(spec: ToolSpec, objective: str) -> dict[str, Any]:
    """Ask whether one analysis is the best of the field, not merely useful.

    This exists because :func:`usefulness_question` asks something whose
    answer is *yes* for nearly every candidate. At the first decision round
    only the bootstrap has run, so every remaining analysis genuinely would
    add information not already implied -- and across two live benchmarks the
    model said so, returning near-identical probabilities that no amount of
    state detail or description text moved. Fifty-seven rounds produced a
    median top-two margin of 0.030 against a 0.10 requirement, so the policy
    never once reached ``act_clear``.

    The proposition here is true for at most one candidate. A flat answer
    across the field is therefore incoherent rather than correct, which is the
    whole point: the question can only be answered by comparing.

    Like the usefulness question it carries no option list, so it keeps the
    independent-noul design's immunity to option-order bias.

    Args:
        spec: The analysis under consideration.
        objective: What the overall analysis is for.

    Returns:
        A noul question definition.
    """
    return {
        "type": "noul",
        "instructions": (
            f'{_CTX} The analysis under consideration is "{spec.title}": '
            f"{spec.jev_description} Exactly one analysis under NOT YET "
            f"MEASURED is the best use of the next step. Return the "
            f"probability that it is this one."
        ),
        "criteria": {
            "true": (
                f"No other analysis under NOT YET MEASURED would sharpen the "
                f'conclusion about {objective} more than "{spec.title}" would.'
            ),
            "false": (
                f"At least one other analysis under NOT YET MEASURED would "
                f"sharpen the conclusion about {objective} more than "
                f'"{spec.title}" would.'
            ),
        },
    }


def stop_enough_question(objective: str) -> dict[str, Any]:
    """Ask whether the evidence already supports a conclusion.

    Args:
        objective: What the overall analysis is for.

    Returns:
        A noul question definition.
    """
    return {
        "type": "noul",
        "instructions": (
            f"{_CTX} Return the probability that the measurements under MEASURED "
            f"SO FAR are by themselves sufficient to state a conclusion about "
            f"{objective}, so that no further analysis is needed."
        ),
        "criteria": {
            "true": (
                "A conclusion about the objective can be stated from the "
                "measurements already listed."
            ),
            "false": (
                "At least one analysis under NOT YET MEASURED is needed before a "
                "conclusion about the objective can be stated."
            ),
        },
    }


def stop_conflict_question(objective: str) -> dict[str, Any]:
    """Ask whether the evidence so far disagrees with itself.

    This is not redundant with sufficiency. High sufficiency *and* high
    conflict is precisely the state where stopping would be wrong, and it is
    the one case where more analysis reliably helps.

    Args:
        objective: What the overall analysis is for.

    Returns:
        A noul question definition.
    """
    return {
        "type": "noul",
        "instructions": (
            f"{_CTX} Return the probability that the measurements under MEASURED "
            f"SO FAR disagree with each other about {objective}."
        ),
        "criteria": {
            "true": (
                "Two or more of the listed measurements point to opposite "
                "conclusions about the objective."
            ),
            "false": (
                "The listed measurements agree with each other, or do not bear on " "each other."
            ),
        },
    }


def conviction_question(objective: str) -> dict[str, Any]:
    """Ask how strongly the evidence supports acting.

    Reported only; this never routes.

    Args:
        objective: What the overall analysis is for.

    Returns:
        A score question definition.
    """
    return {
        "type": "score",
        "instructions": (
            f"{_CTX} Rate how strongly the measurements under MEASURED SO FAR "
            f"support acting on {objective} now."
        ),
        "criteria": [
            "no support",
            "weak support",
            "mixed",
            "moderate support",
            "strong support",
        ],
    }


def selector_choice_pair(
    specs: Sequence[ToolSpec],
    objective: str,
) -> dict[str, dict[str, Any]]:
    """Ask the same selection question in both option orders.

    Asking twice and averaging is the known mitigation for the model's
    tendency to favour whichever option comes first. The pair is shadow
    instrumentation: it measures that bias on this task at no extra latency,
    and the policy does not act on it.

    Args:
        specs: Candidate analyses.
        objective: What the overall analysis is for.

    Returns:
        The forward and reverse question definitions.
    """
    criteria = {spec.name: spec.jev_description for spec in specs}
    prompt = (
        f"{_CTX} Which single analysis under NOT YET MEASURED should be run next "
        f"to best sharpen the conclusion about {objective}?"
    )
    return {
        SELECT_FWD_QID: {
            "type": "choice",
            "instructions": prompt,
            "criteria": dict(criteria),
        },
        SELECT_REV_QID: {
            "type": "choice",
            "instructions": prompt,
            "criteria": dict(reversed(list(criteria.items()))),
        },
    }


def average_choice_probabilities(
    forward: Mapping[str, float] | None,
    reverse: Mapping[str, float] | None,
) -> dict[str, float]:
    """Average two option-order probability maps.

    Args:
        forward: Probabilities from the forward-order question.
        reverse: Probabilities from the reverse-order question.

    Returns:
        The averaged map, empty when either side is unavailable.
    """
    if not forward or not reverse:
        return {}
    keys = set(forward) | set(reverse)
    return {k: (forward.get(k, 0.0) + reverse.get(k, 0.0)) / 2.0 for k in sorted(keys)}


def build_question_set(
    specs: Sequence[ToolSpec],
    objective: str,
    shadow_choice: bool = True,
) -> dict[str, dict[str, Any]]:
    """Assemble every question for one iteration into a single request.

    Args:
        specs: Candidate analyses.
        objective: What the overall analysis is for.
        shadow_choice: Include the order-balanced Choice pair. It is free in
            latency terms and is the only way to measure option-order bias on
            this task.

    Returns:
        Question identifier to question definition.
    """
    questions: dict[str, dict[str, Any]] = {
        usefulness_qid(spec.name): usefulness_question(spec, objective) for spec in specs
    }
    # Both framings go in one request. Latency barely grows with the number of
    # questions, so keeping the absolute noul alongside the comparative one is
    # nearly free and buys a paired comparison of the two on byte-identical
    # state -- which matters, because run-to-run drift is not negligible: an
    # untouched question's score range moved 0.15 to 0.17 between benchmarks
    # 2 and 3. Only the comparative map routes.
    questions.update(
        {best_next_qid(spec.name): best_next_question(spec, objective) for spec in specs}
    )
    questions[STOP_ENOUGH_QID] = stop_enough_question(objective)
    questions[STOP_CONFLICT_QID] = stop_conflict_question(objective)
    questions[CONVICTION_QID] = conviction_question(objective)
    if shadow_choice and len(specs) > 1:
        questions.update(selector_choice_pair(specs, objective))
    return questions
