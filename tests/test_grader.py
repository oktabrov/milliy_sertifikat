"""Answer normalisation and grading."""

from __future__ import annotations

import pytest

from app.scoring.grader import (
    answers_match,
    build_items,
    grade_answers,
    normalize,
    score_attempt,
    tables_for_test,
    to_number,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12 ta", "12"),
        ("12ta", "12"),
        ("5 nafar", "5"),
        ("3 litr", "3"),
        ("1500 so'm", "1500"),
        ("90 gradus", "90"),
        ("7 jami", "7"),
        ("a=4", "4"),
        ("h = 9", "9"),
        ("12m", "12"),
        ("  8  ", "8"),
        ("3,5", "3.5"),
        ("3.50", "3.5"),
        ("3.0", "3"),
    ],
)
def test_normalize_strips_units_and_noise(raw, expected):
    assert normalize(raw) == expected


def test_normalize_handles_none_and_empty():
    assert normalize(None) == ""
    assert normalize("") == ""
    assert normalize("   ") == ""


@pytest.mark.parametrize(
    ("latex", "expected"),
    [
        (r"\frac{50}{3}", "((50)/(3))"),
        (r"\dfrac{50}{3}", "((50)/(3))"),
        (r"2\sqrt{2}", "2sqrt(2)"),
        (r"1.6\cdot10^{-26}", "1.6*10**(-26)"),
        (r"2\cdot10^{5}", "2*10**(5)"),
        (r"\pi", "pi"),
    ],
)
def test_normalize_canonicalises_latex(latex, expected):
    assert normalize(latex) == expected


def test_to_number_evaluates_arithmetic():
    assert to_number("((50)/(3))") == pytest.approx(50 / 3)
    assert to_number("2sqrt(2)") is None  # implicit multiplication is not arithmetic
    assert to_number("2*sqrt(2)") == pytest.approx(2 * 2**0.5)
    assert to_number("1.6*10**(-26)") == pytest.approx(1.6e-26)


def test_to_number_refuses_anything_dangerous():
    assert to_number("__import__('os')") is None
    assert to_number("open('/etc/passwd')") is None
    assert to_number("1/0") is None
    assert to_number("x" * 500) is None


def test_matching_is_numeric_where_it_can_be():
    assert answers_match("50/3", r"\frac{50}{3}")
    assert answers_match("0.5", "1/2")
    assert answers_match("2 ta", "2")
    # A decimal written out to enough places counts as the fraction.
    assert answers_match("16.666666666", "50/3")


def test_matching_rejects_a_rounded_decimal():
    assert answers_match("16.7", "50/3") is False
    assert answers_match("3.1", "3.2") is False


def test_matching_falls_back_to_canonical_text():
    assert answers_match(r"2\sqrt{2}", "2sqrt(2)")
    assert answers_match("3 marta ortadi", "3martaortadi")
    assert answers_match("kamayadi", "ortadi") is False


def test_matching_rejects_a_blank_expected_answer():
    assert answers_match("5", "") is False
    assert answers_match("5", None) is False


def test_build_items_flattens_open_parts():
    questions = [
        {"number": 1, "type": "mc", "options": 4, "answer": "A"},
        {"number": 2, "type": "open", "parts": {"a": "1", "b": "2"}},
        {"number": 3, "type": "open", "parts": {"a": "7"}},
    ]
    items = build_items(questions)
    assert [item.key for item in items] == ["1", "2a", "2b", "3a"]
    assert [item.kind for item in items] == ["mc", "open", "open", "open"]


def test_build_items_skips_blank_parts():
    items = build_items([{"number": 9, "type": "open", "parts": {"a": "1", "b": ""}}])
    assert [item.key for item in items] == ["9a"]


def test_grade_answers_scores_each_item():
    items = build_items(
        [
            {"number": 1, "type": "mc", "options": 4, "answer": "B"},
            {"number": 2, "type": "open", "parts": {"a": "50/3"}},
        ]
    )
    raw, per_item = grade_answers(items, {"1": "b", "2a": r"\frac{50}{3}"})
    assert raw == 2
    assert per_item == {"1": True, "2a": True}


def test_grade_answers_marks_missing_answers_wrong():
    items = build_items([{"number": 1, "type": "mc", "options": 4, "answer": "B"}])
    raw, per_item = grade_answers(items, {})
    assert raw == 0
    assert per_item == {"1": False}


def test_multiple_choice_is_case_insensitive():
    items = build_items([{"number": 1, "type": "mc", "options": 4, "answer": "C"}])
    assert grade_answers(items, {"1": " c "})[0] == 1


def test_score_attempt_returns_one_result_per_scenario():
    questions = [{"number": n, "type": "mc", "options": 4, "answer": "A"} for n in range(1, 11)]
    items = build_items(questions)
    tables = tables_for_test(items, size=800)

    submitted = {str(n): "A" for n in range(1, 8)}
    result = score_attempt(items, submitted, tables)

    assert result.raw_correct == 7
    assert result.total_items == 10
    assert [scenario.key for scenario in result.scenarios] == ["weak", "normal", "strong"]
    # Same performance, three verdicts — weakest field flatters the student most.
    balls = [scenario.ball for scenario in result.scenarios]
    assert balls == sorted(balls, reverse=True)


def test_tables_for_test_accepts_observed_difficulties():
    items = build_items(
        [{"number": n, "type": "mc", "options": 4, "answer": "A"} for n in range(1, 6)]
    )
    observed = [-2.0, -1.0, 0.0, 1.0, 2.0]
    tables = tables_for_test(items, observed=observed, size=800)
    assert set(tables) == {"weak", "normal", "strong"}
    assert len(tables["normal"].rows) == 6


def test_tables_for_test_ignores_mismatched_observed_length():
    items = build_items(
        [{"number": n, "type": "mc", "options": 4, "answer": "A"} for n in range(1, 6)]
    )
    tables = tables_for_test(items, observed=[0.0, 0.1], size=800)
    assert len(tables["normal"].rows) == 6


# --- Several accepted answers per open part ----------------------------------


def test_accepted_list_normalises_every_shape():
    from app.scoring.grader import accepted_list

    assert accepted_list("3/4") == ["3/4"]
    assert accepted_list(["3/4", "0.75"]) == ["3/4", "0.75"]
    assert accepted_list(["3/4", "  ", ""]) == ["3/4"]
    assert accepted_list(None) == []
    assert accepted_list("") == []
    assert accepted_list([]) == []


def test_build_items_keeps_every_accepted_answer():
    items = build_items(
        [{"number": 36, "type": "open", "parts": {"a": ["3/4", "0.75", r"\frac{3}{4}"]}}]
    )
    assert [item.key for item in items] == ["36a"]
    assert items[0].accepted == ["3/4", "0.75", r"\frac{3}{4}"]
    assert items[0].expected == "3/4"


def test_build_items_still_accepts_a_bare_string():
    """Answer keys written before multiple answers existed must keep working."""
    items = build_items([{"number": 36, "type": "open", "parts": {"a": "50/3"}}])
    assert items[0].accepted == ["50/3"]


def test_any_accepted_answer_counts_as_correct():
    items = build_items(
        [{"number": 1, "type": "open", "parts": {"a": ["3/4", "0.75", "0,75"]}}]
    )
    for submitted in ("3/4", "0.75", "0,75", r"\frac{3}{4}"):
        raw, _ = grade_answers(items, {"1a": submitted})
        assert raw == 1, f"{submitted!r} should have been accepted"


def test_a_wrong_answer_is_still_wrong_with_several_accepted():
    items = build_items([{"number": 1, "type": "open", "parts": {"a": ["3/4", "0.75"]}}])
    assert grade_answers(items, {"1a": "4/3"})[0] == 0
    assert grade_answers(items, {"1a": ""})[0] == 0
    assert grade_answers(items, {})[0] == 0


def test_accepted_answers_cover_forms_no_canonicaliser_would_match():
    """The real reason this feature exists: text and algebraic variants."""
    items = build_items(
        [{"number": 2, "type": "open", "parts": {"a": ["ortadi", "oshadi", "kattalashadi"]}}]
    )
    assert grade_answers(items, {"2a": "oshadi"})[0] == 1
    assert grade_answers(items, {"2a": "kamayadi"})[0] == 0


def test_an_empty_accepted_list_yields_no_item():
    items = build_items([{"number": 3, "type": "open", "parts": {"a": [], "b": ["2"]}}])
    assert [item.key for item in items] == ["3b"]


def test_multiple_choice_with_no_key_is_never_correct():
    items = build_items([{"number": 1, "type": "mc", "options": 4, "answer": ""}])
    assert grade_answers(items, {"1": "A"})[0] == 0
