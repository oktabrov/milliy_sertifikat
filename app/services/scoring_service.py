"""Where storage meets the Rasch model.

`app.scoring.*` is deliberately ignorant of storage and of Telegram; this module
is the only place that knows about both.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from app.config import get_settings
from app.scoring.grader import Item, build_items, score_attempt, tables_for_test
from app.scoring.rasch import calibrate
from app.scoring.scenarios import ScenarioTable
from app.store.json_store import Store
from app.store.models import Attempt, Test

logger = logging.getLogger(__name__)


def items_for(test: Test) -> list[Item]:
    return build_items(test.questions or [])


def _serialize(tables: dict[str, ScenarioTable]) -> dict[str, Any]:
    return {key: table.to_dict() for key, table in tables.items()}


def _deserialize(raw: dict[str, Any]) -> dict[str, ScenarioTable]:
    return {key: ScenarioTable.from_dict(value) for key, value in raw.items()}


async def ensure_tables(store: Store, test: Test) -> dict[str, ScenarioTable]:
    """Scenario tables for a test, building and caching them on first use.

    Building all three costs a fraction of a second for a 55-item test, but it
    is pure CPU and would otherwise run on every submission, so the result is
    cached on the record.
    """
    if test.score_tables:
        try:
            return _deserialize(test.score_tables)
        except (KeyError, TypeError, ValueError):
            logger.warning("Cached score tables for test %s are unreadable; rebuilding", test.code)

    settings = get_settings()
    tables = tables_for_test(items_for(test), scale=settings.ball_scale, size=settings.cohort_size)
    test.score_tables = _serialize(tables)
    await store.save_test(test)
    return tables


def observed_difficulties(store: Store, test: Test) -> list[float] | None:
    """Calibrate item difficulty from the students who actually sat the test.

    Returns None until there are enough submissions for the estimate to mean
    anything.
    """
    settings = get_settings()
    items = items_for(test)
    if not items:
        return None

    attempts = store.attempts_by_test(test.id)
    if len(attempts) < settings.min_real_submissions:
        return None

    n_items = len(items)
    raw_score_counts = [0] * (n_items + 1)
    item_scores = [0] * n_items

    for attempt in attempts:
        per_item = attempt.per_item or {}
        responses = [1 if per_item.get(item.key) else 0 for item in items]
        raw = sum(responses)
        raw_score_counts[raw] += 1
        if 0 < raw < n_items:
            for index, correct in enumerate(responses):
                item_scores[index] += correct

    calibration = calibrate(raw_score_counts, item_scores)
    return calibration.difficulties if calibration.converged else None


async def recalibrate(store: Store, test: Test) -> bool:
    """Rebuild the scenario tables from real responses. Returns True if it ran.

    The synthetic cohorts stay — they are what makes percentiles stable at
    n=50 — but their item difficulties are now seeded from real data instead of
    the default profile.
    """
    settings = get_settings()
    difficulties = observed_difficulties(store, test)
    if difficulties is None:
        return False

    total = store.count_attempts(test.id)
    if total <= test.calibrated_from:
        return False

    tables = tables_for_test(
        items_for(test),
        observed=difficulties,
        scale=settings.ball_scale,
        size=settings.cohort_size,
    )
    test.score_tables = _serialize(tables)
    test.calibrated_from = total
    await store.save_test(test)

    await rescore_attempts(store, test, tables)
    logger.info("Recalibrated test %s from %d real submissions", test.code, total)
    return True


async def rescore_attempts(
    store: Store, test: Test, tables: dict[str, ScenarioTable]
) -> None:
    """Re-apply the new tables to everyone who already submitted."""
    attempts = store.attempts_by_test(test.id)
    for attempt in attempts:
        attempt.results = _rows_for(attempt.raw_correct, tables)
    await store.save_attempts(attempts)


def _rows_for(raw_correct: int, tables: dict[str, ScenarioTable]) -> list[dict[str, Any]]:
    rows = []
    for key, table in tables.items():
        row = table.row_for(raw_correct)
        rows.append(
            {
                "key": key,
                "label_uz": table.label_uz,
                "ball": row.ball,
                "percentile": row.percentile,
                "grade": row.grade,
                "theta": row.theta,
            }
        )
    return rows


async def record_attempt(
    store: Store,
    test: Test,
    user_id: int,
    subject: str | None,
    answers: dict[str, Any],
) -> Attempt:
    """Grade a submission, score it against all three cohorts, and store it.

    Raises `ValueError` if this student already answered this test.
    """
    items = items_for(test)
    tables = await ensure_tables(store, test)
    result = score_attempt(items, answers, tables)

    return await store.create_attempt(
        test_id=test.id,
        user_id=user_id,
        subject=subject,
        answers=answers,
        per_item=result.per_item,
        raw_correct=result.raw_correct,
        total_items=result.total_items,
        results=[asdict(scenario) for scenario in result.scenarios],
    )
