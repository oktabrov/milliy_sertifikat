"""Rasch engine: does it recover what we put in?"""

from __future__ import annotations

import math
import random

import pytest

from app.scoring.rasch import (
    ability_for_raw_score,
    calibrate,
    prob_correct,
    seed_difficulties,
)


def test_prob_correct_is_a_half_at_equal_ability_and_difficulty():
    assert prob_correct(0.0, 0.0) == pytest.approx(0.5)
    assert prob_correct(1.0, 1.0) == pytest.approx(0.5)


def test_prob_correct_is_monotonic_in_ability():
    values = [prob_correct(theta, 0.0) for theta in (-2, -1, 0, 1, 2)]
    assert values == sorted(values)


def test_prob_correct_survives_extreme_arguments():
    assert prob_correct(-500.0, 500.0) >= 0.0
    assert prob_correct(500.0, -500.0) <= 1.0


def test_ability_rises_with_raw_score():
    difficulties = [-1.0, -0.5, 0.0, 0.5, 1.0]
    abilities = [ability_for_raw_score(raw, difficulties) for raw in range(6)]
    assert abilities == sorted(abilities)


def test_extreme_scores_stay_finite():
    difficulties = [0.0] * 10
    assert math.isfinite(ability_for_raw_score(0, difficulties))
    assert math.isfinite(ability_for_raw_score(10, difficulties))


def test_ability_solves_the_score_equation():
    """The defining property: expected score at theta equals the raw score."""
    difficulties = [-1.5, -0.7, 0.0, 0.3, 0.9, 1.8]
    for raw in range(1, len(difficulties)):
        theta = ability_for_raw_score(raw, difficulties)
        expected = sum(prob_correct(theta, b) for b in difficulties)
        assert expected == pytest.approx(raw, abs=1e-4)


def test_seed_difficulties_are_centred():
    seeds = seed_difficulties([80, 50, 20], n_persons=100)
    assert sum(seeds) == pytest.approx(0.0, abs=1e-9)
    # Fewer correct answers means a harder item.
    assert seeds[0] < seeds[1] < seeds[2]


def _simulate(true_difficulties, n_persons, seed, ability_mean=0.0):
    rng = random.Random(seed)
    n_items = len(true_difficulties)
    raw_counts = [0] * (n_items + 1)
    item_scores = [0] * n_items
    for _ in range(n_persons):
        theta = rng.gauss(ability_mean, 1.0)
        row = [1 if rng.random() < prob_correct(theta, b) else 0 for b in true_difficulties]
        raw = sum(row)
        raw_counts[raw] += 1
        if 0 < raw < n_items:
            for index, correct in enumerate(row):
                item_scores[index] += correct
    return raw_counts, item_scores


def test_calibrate_recovers_known_difficulties():
    """The headline property. Feed in known difficulties, get them back."""
    true_difficulties = [-2.0, -1.2, -0.6, 0.0, 0.4, 0.9, 1.5, 2.1]
    centred = [b - sum(true_difficulties) / len(true_difficulties) for b in true_difficulties]

    raw_counts, item_scores = _simulate(true_difficulties, n_persons=4000, seed=7)
    calibration = calibrate(raw_counts, item_scores)

    assert calibration.converged
    for estimated, expected in zip(calibration.difficulties, centred):
        assert estimated == pytest.approx(expected, abs=0.25)


def test_calibrate_preserves_difficulty_ordering():
    true_difficulties = [-1.8, -0.9, 0.0, 0.7, 1.6]
    raw_counts, item_scores = _simulate(true_difficulties, n_persons=3000, seed=11)
    estimated = calibrate(raw_counts, item_scores).difficulties
    assert estimated == sorted(estimated)


def test_calibrate_output_is_centred():
    true_difficulties = [-1.0, 0.0, 1.0, 2.0]
    raw_counts, item_scores = _simulate(true_difficulties, n_persons=2000, seed=3)
    estimated = calibrate(raw_counts, item_scores).difficulties
    assert sum(estimated) / len(estimated) == pytest.approx(0.0, abs=1e-6)


def test_calibrate_handles_a_cohort_with_no_usable_data():
    """Everyone scored zero: nothing to calibrate, but it must not explode."""
    calibration = calibrate([5, 0, 0, 0], [0, 0, 0])
    assert len(calibration.difficulties) == 3
    assert not calibration.converged


def test_calibrate_handles_no_items():
    calibration = calibrate([1], [])
    assert calibration.difficulties == []
    assert calibration.converged
