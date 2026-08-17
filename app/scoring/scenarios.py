"""Three-cohort reference scoring.

Why this exists
---------------
A real sitting of one of these tests has 50-100 students. That is far too few
to calibrate 45-55 items or to quote a percentile with a straight face.

So instead of pretending the real cohort is a norm group, we build three
*synthetic* norm groups of 10,000 virtual participants each and score every
real student against all three:

    weak    N(-1.2, 1)   most participants did poorly
    normal  N( 0.0, 1)   most participants did about average
    strong  N(+1.2, 1)   most participants did very well

Each cohort gets its own JMLE calibration, anchored so that the *cohort's* mean
ability sits at zero. That anchoring is what produces "question complexity in
three types": the identical item comes out harder in the weak cohort and easier
in the strong one, because difficulty is only ever identified relative to the
people who sat the test.

A student then receives three results, which bracket where they would land
depending on how strong the national field turns out to be.

Honest caveat
-------------
Simulation does not discover difficulty it was not given. Difficulties
recovered from a synthetic cohort equal the seeded ones plus the anchoring
shift, up to sampling noise. What the simulation buys is (a) a smooth, stable
raw-score -> ball -> percentile mapping computed at N=10,000 instead of N=50,
and (b) the cohort-strength bracketing above. It is not a substitute for real
calibration data, and once 20 real submissions exist we re-seed the true
difficulties from them (see `scoring.grader`).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, asdict
from typing import Any

from app.scoring.rasch import (
    abilities_by_raw_score,
    calibrate,
    prob_correct,
)

COHORT_SIZE = 10_000


@dataclass(frozen=True)
class Scenario:
    key: str
    label_uz: str
    mean: float
    sd: float
    seed: int


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("weak", "Zaif guruh", -1.2, 1.0, seed=101),
    Scenario("normal", "O'rtacha guruh", 0.0, 1.0, seed=202),
    Scenario("strong", "Kuchli guruh", 1.2, 1.0, seed=303),
)

SCENARIOS_BY_KEY = {scenario.key: scenario for scenario in SCENARIOS}


@dataclass(frozen=True)
class BallScale:
    """Maps ability in logits onto the 0-100 ball used by the bot.

    `midpoint + slope * theta`, so a student sitting exactly at the cohort mean
    scores `midpoint`, and each logit above that is worth `slope` ball.
    """

    midpoint: float = 50.0
    slope: float = 16.0
    minimum: int = 0
    maximum: int = 100
    # Descending, first match wins.
    bands: tuple[tuple[int, str], ...] = (
        (70, "A+"),
        (65, "A"),
        (60, "B+"),
        (55, "B"),
        (50, "C+"),
        (46, "C"),
    )

    def ball(self, theta: float) -> int:
        raw = self.midpoint + self.slope * theta
        return int(max(self.minimum, min(self.maximum, round(raw))))

    def grade(self, ball: int) -> str:
        for threshold, label in self.bands:
            if ball >= threshold:
                return label
        return "—"


@dataclass
class ScoreRow:
    raw: int
    theta: float
    ball: int
    percentile: float
    grade: str


@dataclass
class ScenarioTable:
    """Everything needed to score a student against one synthetic cohort."""

    key: str
    label_uz: str
    difficulties: list[float]
    rows: list[ScoreRow]
    converged: bool

    def row_for(self, raw: int) -> ScoreRow:
        index = max(0, min(len(self.rows) - 1, raw))
        return self.rows[index]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label_uz": self.label_uz,
            "difficulties": [round(value, 4) for value in self.difficulties],
            "rows": [asdict(row) for row in self.rows],
            "converged": self.converged,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScenarioTable":
        return cls(
            key=data["key"],
            label_uz=data["label_uz"],
            difficulties=list(data["difficulties"]),
            rows=[ScoreRow(**row) for row in data["rows"]],
            converged=data["converged"],
        )


def default_difficulties(mc_items: int, open_items: int) -> list[float]:
    """Starting difficulty profile for a test nobody has sat yet.

    Mirrors how these papers are actually built: multiple-choice questions ramp
    up gently, and the short-answer block at the end is a step harder.
    """
    difficulties: list[float] = []

    if mc_items > 0:
        low, high = -1.5, 1.2
        span = max(mc_items - 1, 1)
        difficulties += [low + (high - low) * index / span for index in range(mc_items)]

    if open_items > 0:
        low, high = 0.4, 2.2
        span = max(open_items - 1, 1)
        difficulties += [low + (high - low) * index / span for index in range(open_items)]

    if not difficulties:
        return []

    mean = sum(difficulties) / len(difficulties)
    return [value - mean for value in difficulties]


def simulate_cohort(
    true_difficulties: list[float],
    scenario: Scenario,
    size: int = COHORT_SIZE,
) -> tuple[list[int], list[int]]:
    """Draw `size` virtual participants and have them sit the test.

    Returns `(raw_score_counts, item_scores)` where `item_scores` counts only
    non-extreme participants, matching what `rasch.calibrate` expects.

    The RNG is seeded from the scenario, so a given test always produces
    identical tables — students comparing screenshots see the same numbers.
    """
    rng = random.Random(scenario.seed)
    n_items = len(true_difficulties)

    raw_score_counts = [0] * (n_items + 1)
    item_scores = [0] * n_items

    for _ in range(size):
        theta = rng.gauss(scenario.mean, scenario.sd)
        responses = [1 if rng.random() < prob_correct(theta, b) else 0 for b in true_difficulties]
        raw = sum(responses)
        raw_score_counts[raw] += 1
        if 0 < raw < n_items:
            for index, correct in enumerate(responses):
                item_scores[index] += correct

    return raw_score_counts, item_scores


def build_scenario_table(
    true_difficulties: list[float],
    scenario: Scenario,
    scale: BallScale | None = None,
    size: int = COHORT_SIZE,
) -> ScenarioTable:
    """Simulate one cohort, calibrate it, and precompute the whole score table."""
    scale = scale or BallScale()
    n_items = len(true_difficulties)
    if n_items == 0:
        return ScenarioTable(scenario.key, scenario.label_uz, [], [], converged=True)

    raw_score_counts, item_scores = simulate_cohort(true_difficulties, scenario, size)
    calibration = calibrate(raw_score_counts, item_scores, start_from=true_difficulties)

    abilities = calibration.abilities_by_raw or abilities_by_raw_score(calibration.difficulties)
    total = sum(raw_score_counts)

    # Person anchoring: shift so the cohort's mean ability is zero. The same
    # shift moves difficulties in the opposite direction, which is precisely the
    # "harder in a weak cohort" effect we are after.
    cohort_mean = (
        sum(raw_score_counts[raw] * abilities[raw] for raw in range(len(abilities))) / total
        if total
        else 0.0
    )

    rows: list[ScoreRow] = []
    cumulative = 0
    for raw, ability in enumerate(abilities):
        count = raw_score_counts[raw]
        # Mid-rank percentile: half of the people on your own score count as below you.
        percentile = ((cumulative + 0.5 * count) / total * 100.0) if total else 0.0
        cumulative += count

        theta = ability - cohort_mean
        ball = scale.ball(theta)
        rows.append(
            ScoreRow(
                raw=raw,
                theta=round(theta, 4),
                ball=ball,
                percentile=round(percentile, 1),
                grade=scale.grade(ball),
            )
        )

    return ScenarioTable(
        key=scenario.key,
        label_uz=scenario.label_uz,
        difficulties=[b - cohort_mean for b in calibration.difficulties],
        rows=rows,
        converged=calibration.converged,
    )


def build_all_tables(
    true_difficulties: list[float],
    scale: BallScale | None = None,
    size: int = COHORT_SIZE,
) -> dict[str, ScenarioTable]:
    """All three scenario tables. Roughly 2-5 s of CPU — cache the result."""
    return {
        scenario.key: build_scenario_table(true_difficulties, scenario, scale, size)
        for scenario in SCENARIOS
    }
