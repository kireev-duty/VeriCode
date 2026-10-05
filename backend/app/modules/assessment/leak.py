"""Leak detector for item slots: one-sided CUSUM on residuals against the slot's own baseline.

residual = observed correctness - P(correct | estimated ability of the respondent)

Expert item parameters are never exact, so a slot can have a constant residual offset that is *not* a leak.
The detector therefore learns the slot's baseline during a burn-in period and keeps adapting it slowly; a leak shows
up as an abrupt upward shift relative to that baseline (many respondents suddenly "know" the answer or the trick).
Pure functions: the service and the validation share them.
"""

from dataclasses import dataclass

BURN_IN = 100  # responses used to learn the baseline offset of a slot
ALPHA = 0.01  # slow adaptation of the baseline after burn-in
K = 0.10  # CUSUM allowance (about half of the shift caused by ~30% respondents knowing the answer)
H = 5.0  # decision threshold: ~5% false alarms per 600 honest responses (docs/validation)


@dataclass
class LeakState:
    n: int = 0
    baseline: float = 0.0
    cusum: float = 0.0


def step(state: LeakState, residual: float) -> bool:
    """Updates the state with one response; returns True when the slot should be flagged."""
    state.n += 1
    if state.n <= BURN_IN:
        state.baseline += (residual - state.baseline) / state.n
        return False
    state.cusum = max(0.0, state.cusum + (residual - state.baseline) - K)
    state.baseline += ALPHA * (residual - state.baseline)
    return state.cusum > H
