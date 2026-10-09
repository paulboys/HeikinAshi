"""JEV-only adaptive stock-analysis routing agent.

An experiment: can a specialised decision model route among deterministic
financial-analysis tools better, faster or more cheaply than a hand-built
decision tree?

JEV is the only AI in the loop. It never computes an indicator -- Python does
that -- and answers only which analysis is worth running next and whether the
evidence is sufficient to stop. There is no generative-LLM fallback: if the
decision model is unavailable the agent reports what it has and stops.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
