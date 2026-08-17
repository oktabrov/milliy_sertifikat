"""The three-cohort machinery — the part the whole design turns on."""

from __future__ import annotations

import pytest

from app.scoring.scenarios import (
    SCENARIOS,
    BallScale,
    ScenarioTable,
    build_all_tables,
    build_scenario_table,
    default_difficulties,
)

# Small cohorts keep the suite quick; the properties under test are the same.
SMALL = 1500


@pytest.fixture(scope="module")
def difficulties():
    return default_difficulties(mc_items=20, open_items=6)


@pytest.fixture(scope="module")
def tables(difficulties):
    return build_all_tables(difficulties, size=SMALL)


def test_default_profile_is_centred_and_ramps_up():
    profile = default_difficulties(mc_items=35, open_items=10)
    assert len(profile) == 45
    assert sum(profile) / len(profile) == pytest.approx(0.0, abs=1e-9)
    # Multiple choice ramps up, and the open block starts harder than it ends low.
    assert profile[0] < profile[34]
    assert profile[-1] == max(profile)


def test_weak_cohort_makes_items_look_harder(tables):
    """The requirement in one assertion.

    Identical items, three cohorts: mean difficulty must rise as the cohort
    weakens, because difficulty is only identified relative to the people who
    sat the test.
    """
    means = {
        key: sum(table.difficulties) / len(table.difficulties) for key, table in tables.items()
    }
    assert means["weak"] > means["normal"] > means["strong"]
    # And the shift tracks the cohort's own ability offset, within sampling noise.
    assert means["weak"] == pytest.approx(1.2, abs=0.35)
    assert means["normal"] == pytest.approx(0.0, abs=0.35)
    assert means["strong"] == pytest.approx(-1.2, abs=0.35)


def test_same_raw_score_scores_highest_against_the_weak_cohort(tables):
    raw = 15
    weak = tables["weak"].row_for(raw)
    normal = tables["normal"].row_for(raw)
    strong = tables["strong"].row_for(raw)

    assert weak.ball > normal.ball > strong.ball
    assert weak.percentile > normal.percentile > strong.percentile


def test_every_scenario_has_a_row_per_possible_raw_score(tables, difficulties):
    for table in tables.values():
        assert len(table.rows) == len(difficulties) + 1
        assert [row.raw for row in table.rows] == list(range(len(difficulties) + 1))


def test_ball_and_percentile_rise_with_raw_score(tables):
    for table in tables.values():
        balls = [row.ball for row in table.rows]
        percentiles = [row.percentile for row in table.rows]
        assert balls == sorted(balls)
        assert percentiles == sorted(percentiles)


def test_percentiles_stay_inside_zero_to_one_hundred(tables):
    for table in tables.values():
        for row in table.rows:
            assert 0.0 <= row.percentile <= 100.0
            assert 0 <= row.ball <= 100


def test_median_of_a_cohort_sits_near_the_scale_midpoint(tables):
    """A student at their cohort's median should score about 50 ball."""
    for table in tables.values():
        median = min(table.rows, key=lambda row: abs(row.percentile - 50.0))
        assert median.ball == pytest.approx(50, abs=6)


def test_tables_are_deterministic(difficulties):
    first = build_scenario_table(difficulties, SCENARIOS[0], size=SMALL)
    second = build_scenario_table(difficulties, SCENARIOS[0], size=SMALL)
    assert [row.ball for row in first.rows] == [row.ball for row in second.rows]
    assert first.difficulties == second.difficulties


def test_table_survives_a_json_round_trip(tables):
    original = tables["normal"]
    restored = ScenarioTable.from_dict(original.to_dict())
    assert restored.key == original.key
    assert restored.label_uz == original.label_uz
    assert [row.ball for row in restored.rows] == [row.ball for row in original.rows]


def test_row_for_clamps_out_of_range_scores(tables):
    table = tables["normal"]
    assert table.row_for(-5) is table.rows[0]
    assert table.row_for(10_000) is table.rows[-1]


def test_ball_scale_bands():
    scale = BallScale()
    assert scale.grade(95) == "A+"
    assert scale.grade(70) == "A+"
    assert scale.grade(69) == "A"
    assert scale.grade(46) == "C"
    assert scale.grade(45) == "—"


def test_ball_scale_clamps():
    scale = BallScale()
    assert scale.ball(50.0) == 100
    assert scale.ball(-50.0) == 0
    assert scale.ball(0.0) == 50


def test_empty_test_produces_an_empty_table():
    table = build_scenario_table([], SCENARIOS[0], size=SMALL)
    assert table.rows == []
    assert table.difficulties == []
