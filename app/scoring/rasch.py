"""Dichotomous Rasch (1-PL) model in pure Python.

No numpy/scipy on purpose: alwaysdata's free tier gives 100 MB of disk and
numpy alone eats a third of it. Everything here is stdlib `math`.

The one optimisation that makes this fast enough to be practical: under the
dichotomous Rasch model, every person with the same raw score gets the same
ability estimate. A 10,000 x 55 response matrix therefore collapses to 56
raw-score groups, and JMLE iterates over those instead of over people.

Model
-----
    P(correct | theta, b) = 1 / (1 + exp(b - theta))

`theta` is person ability, `b` is item difficulty, both in logits.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Abilities and difficulties beyond +/-6 logits are meaningless in practice and
# only serve to make the arithmetic unstable.
MAX_LOGIT = 6.0

# Persons with a perfect or zero score have no finite ML estimate. The standard
# Wright/Linacre fix is to nudge the raw score inwards by this much.
EXTREME_CORRECTION = 0.3

_NEWTON_TOL = 1e-6
_NEWTON_MAX_ITER = 60
_JMLE_TOL = 1e-4
_JMLE_MAX_ITER = 200


def prob_correct(theta: float, difficulty: float) -> float:
    """Probability that a person of ability `theta` answers an item of `difficulty`."""
    delta = difficulty - theta
    # math.exp overflows around 710; clamp long before that.
    if delta > 35.0:
        return 1e-15
    if delta < -35.0:
        return 1.0 - 1e-15
    return 1.0 / (1.0 + math.exp(delta))


def _clamp_logit(value: float) -> float:
    return max(-MAX_LOGIT, min(MAX_LOGIT, value))


def ability_for_raw_score(
    raw: int,
    difficulties: list[float],
    extreme_correction: float = EXTREME_CORRECTION,
) -> float:
    """Maximum-likelihood ability estimate for someone scoring `raw` out of len(difficulties).

    Newton-Raphson on the score equation `sum(P) = raw`, which is what makes the
    estimate depend only on the raw score and not on *which* items were correct.
    """
    n_items = len(difficulties)
    if n_items == 0:
        raise ValueError("cannot estimate ability with no items")

    target = float(raw)
    if raw <= 0:
        target = extreme_correction
    elif raw >= n_items:
        target = n_items - extreme_correction

    # Seed with the closed-form PROX-style guess; it is close enough that
    # Newton converges in a handful of steps.
    mean_difficulty = sum(difficulties) / n_items
    theta = mean_difficulty + math.log(target / (n_items - target))

    for _ in range(_NEWTON_MAX_ITER):
        expected = 0.0
        information = 0.0
        for difficulty in difficulties:
            p = prob_correct(theta, difficulty)
            expected += p
            information += p * (1.0 - p)
        if information < 1e-12:
            break
        # Damped step: undamped Newton can overshoot badly on the first
        # iteration when the seed is poor.
        step = max(-2.0, min(2.0, (target - expected) / information))
        theta = _clamp_logit(theta + step)
        if abs(step) < _NEWTON_TOL:
            break

    return _clamp_logit(theta)


def abilities_by_raw_score(difficulties: list[float]) -> list[float]:
    """Ability for every possible raw score, index 0..len(difficulties)."""
    return [ability_for_raw_score(raw, difficulties) for raw in range(len(difficulties) + 1)]


@dataclass
class Calibration:
    """Result of a JMLE run.

    `difficulties` are centred on zero — the conventional identification
    constraint. Callers that want person-anchored difficulties (see
    `scoring.scenarios`) shift them afterwards.
    """

    difficulties: list[float]
    abilities_by_raw: list[float] = field(default_factory=list)
    iterations: int = 0
    converged: bool = False


def seed_difficulties(item_scores: list[int], n_persons: int) -> list[float]:
    """Closed-form starting difficulties from proportion-correct."""
    out = []
    for score in item_scores:
        adjusted = min(max(float(score), EXTREME_CORRECTION), n_persons - EXTREME_CORRECTION)
        out.append(math.log((n_persons - adjusted) / adjusted))
    mean = sum(out) / len(out) if out else 0.0
    return [value - mean for value in out]


def calibrate(
    raw_score_counts: list[int],
    item_scores: list[int],
    start_from: list[float] | None = None,
) -> Calibration:
    """Joint Maximum Likelihood estimation of item difficulties.

    Parameters
    ----------
    raw_score_counts
        Length `n_items + 1`. `raw_score_counts[r]` is how many people scored `r`.
    item_scores
        Length `n_items`. How many people answered each item correctly, counted
        over non-extreme persons only (JMLE drops perfect and zero scorers from
        item calibration — they carry no information about relative difficulty).
    start_from
        Optional starting difficulties. Speeds up convergence when a previous
        calibration is available.
    """
    n_items = len(item_scores)
    if n_items == 0:
        return Calibration(difficulties=[], abilities_by_raw=[0.0], converged=True)

    # Only non-extreme raw scores inform item difficulty.
    groups = [(raw, raw_score_counts[raw]) for raw in range(1, n_items) if raw_score_counts[raw] > 0]
    n_effective = sum(count for _, count in groups)

    if not groups or n_effective == 0:
        difficulties = list(start_from) if start_from else [0.0] * n_items
        return Calibration(
            difficulties=difficulties,
            abilities_by_raw=abilities_by_raw_score(difficulties),
            converged=False,
        )

    difficulties = list(start_from) if start_from else seed_difficulties(item_scores, n_effective)

    iterations = 0
    converged = False
    for iterations in range(1, _JMLE_MAX_ITER + 1):
        # One ability estimate per raw-score group, not per person.
        abilities = {raw: ability_for_raw_score(raw, difficulties) for raw, _ in groups}

        largest_step = 0.0
        updated = []
        for index in range(n_items):
            expected = 0.0
            information = 0.0
            for raw, count in groups:
                p = prob_correct(abilities[raw], difficulties[index])
                expected += count * p
                information += count * p * (1.0 - p)
            if information < 1e-12:
                updated.append(difficulties[index])
                continue
            # Model predicts more correct answers than observed => item is harder.
            step = max(-1.0, min(1.0, (expected - item_scores[index]) / information))
            updated.append(difficulties[index] + step)
            largest_step = max(largest_step, abs(step))

        mean = sum(updated) / n_items
        difficulties = [_clamp_logit(value - mean) for value in updated]

        if largest_step < _JMLE_TOL:
            converged = True
            break

    difficulties = _correct_jmle_bias(difficulties)

    return Calibration(
        difficulties=difficulties,
        abilities_by_raw=abilities_by_raw_score(difficulties),
        iterations=iterations,
        converged=converged,
    )


def _correct_jmle_bias(difficulties: list[float]) -> list[float]:
    """Shrink the estimated difficulty spread by (L-1)/L.

    Joint MLE systematically over-disperses item difficulties on short tests —
    measured here as a regression slope of 1.19 on 8 items, 1.07 on 20 and 1.03
    on 45. The classic Wright/Linacre multiplier removes almost all of it
    (residual slope within 4% at 8 items, under 1% at 45).
    """
    n_items = len(difficulties)
    if n_items < 2:
        return difficulties
    factor = (n_items - 1) / n_items
    return [value * factor for value in difficulties]
