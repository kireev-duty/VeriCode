"""Item response theory primitives (3PL) with EAP ability estimation on a fixed quadrature grid.

Ability theta is on the N(0, 1) scale of the candidate population. Each item has
  a - discrimination (how sharply the item separates weaker from stronger candidates),
  b - difficulty (theta at which a non-guessing candidate answers correctly with p = 0.5),
  c - guessing floor (1/k for k-option multiple choice, 0 for open answers).
"""

from dataclasses import dataclass

import numpy as np

GRID = np.linspace(-4.0, 4.0, 161)


@dataclass(frozen=True)
class ItemParams:
    a: float
    b: float
    c: float = 0.0


def p_correct(theta, item: ItemParams):
    return item.c + (1.0 - item.c) / (1.0 + np.exp(-item.a * (np.asarray(theta) - item.b)))


def fisher_info(theta: float, item: ItemParams) -> float:
    p = float(p_correct(theta, item))
    q = 1.0 - p
    if p <= item.c or p <= 0 or q <= 0:
        return 0.0
    return item.a**2 * ((p - item.c) ** 2 / (1.0 - item.c) ** 2) * (q / p)


def posterior(responses: list[tuple[ItemParams, bool]], prior_mean: float = 0.0, prior_sd: float = 1.0) -> np.ndarray:
    log_post = -0.5 * ((GRID - prior_mean) / prior_sd) ** 2
    for item, correct in responses:
        p = np.clip(p_correct(GRID, item), 1e-9, 1 - 1e-9)
        log_post += np.log(p) if correct else np.log(1.0 - p)
    log_post -= log_post.max()
    post = np.exp(log_post)
    return post / post.sum()


def eap(responses: list[tuple[ItemParams, bool]], prior_mean: float = 0.0, prior_sd: float = 1.0) -> tuple[float, float]:
    """Expected a posteriori estimate and posterior SD. Stable for short tests and all-correct/all-wrong patterns."""
    post = posterior(responses, prior_mean, prior_sd)
    mean = float((GRID * post).sum())
    sd = float(np.sqrt(((GRID - mean) ** 2 * post).sum()))
    return mean, sd


def prob_above(responses: list[tuple[ItemParams, bool]], threshold: float, prior_mean: float = 0.0,
               prior_sd: float = 1.0) -> float:
    """Posterior probability that the candidate's true ability is at or above a grade threshold."""
    post = posterior(responses, prior_mean, prior_sd)
    return float(post[GRID >= threshold].sum())
