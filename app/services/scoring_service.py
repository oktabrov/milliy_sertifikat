"""Where the database meets the Rasch model.

`app.scoring.*` is deliberately ignorant of SQLAlchemy and Telegram; this module
is the only place that knows about all three.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Attempt, Test
from app.scoring.grader import Item, build_items, score_attempt, tables_for_test
from app.scoring.rasch import calibrate
from app.scoring.scenarios import ScenarioTable

logger = logging.getLogger(__name__)


def items_for(test: Test) -> list[Item]:
    return build_items(test.questions or [])


def _serialize(tables: dict[str, ScenarioTable]) -> dict[str, Any]:
    return {key: table.to_dict() for key, table in tables.items()}


def _deserialize(raw: dict[str, Any]) -> dict[str, ScenarioTable]:
    return {key: ScenarioTable.from_dict(value) for key, value in raw.items()}


async def ensure_tables(session: AsyncSession, test: Test) -> dict[str, ScenarioTable]:
    """Scenario tables for a test, building and caching them on first use.

    Building all three costs a fraction of a second for a 55-item test, but it
    is pure CPU and runs on every submission otherwise, so it is cached on the
    row as JSON.
    """
    if test.score_tables:
        try:
            return _deserialize(test.score_tables)
        except (KeyError, TypeError, ValueError):
            logger.warning("Cached score tables for test %s are unreadable; rebuilding", test.code)

    settings = get_settings()
    tables = tables_for_test(
        items_for(test), scale=settings.ball_scale, size=settings.cohort_size
    )
    test.score_tables = _serialize(tables)
    await session.commit()
    return tables


async def observed_difficulties(session: AsyncSession, test: Test) -> list[float] | None:
    """Calibrate item difficulty from the students who actually sat the test.

    Returns None until there are enough submissions for the estimate to mean
    anything.
    """
    settings = get_settings()
    items = items_for(test)
    if not items:
        return None

    rows = (
        (await session.execute(select(Attempt.per_item).where(Attempt.test_id == test.id)))
        .scalars()
        .all()
    )
    if len(rows) < settings.min_real_submissions:
        return None

    n_items = len(items)
    raw_score_counts = [0] * (n_items + 1)
    item_scores = [0] * n_items

    for per_item in rows:
        per_item = per_item or {}
        responses = [1 if per_item.get(item.key) else 0 for item in items]
        raw = sum(responses)
        raw_score_counts[raw] += 1
        if 0 < raw < n_items:
            for index, correct in enumerate(responses):
                item_scores[index] += correct

    calibration = calibrate(raw_score_counts, item_scores)
    return calibration.difficulties if calibration.converged else None


async def recalibrate(session: AsyncSession, test: Test) -> bool:
    """Rebuild the scenario tables from real responses. Returns True if it ran.

    The synthetic cohorts stay — they are what makes percentiles stable at
    n=50 — but their item difficulties are now seeded from real data instead of
    the default profile.
    """
    settings = get_settings()
    difficulties = await observed_difficulties(session, test)
    if difficulties is None:
        return False

    total = len(
        (await session.execute(select(Attempt.id).where(Attempt.test_id == test.id)))
        .scalars()
        .all()
    )
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
    await session.commit()

    await rescore_attempts(session, test, tables)
    logger.info("Recalibrated test %s from %d real submissions", test.code, total)
    return True


async def rescore_attempts(
    session: AsyncSession, test: Test, tables: dict[str, ScenarioTable]
) -> None:
    """Re-apply the new tables to everyone who already submitted."""
    attempts = (
        (await session.execute(select(Attempt).where(Attempt.test_id == test.id))).scalars().all()
    )
    for attempt in attempts:
        results = []
        for key, table in tables.items():
            row = table.row_for(attempt.raw_correct)
            results.append(
                {
                    "key": key,
                    "label_uz": table.label_uz,
                    "ball": row.ball,
                    "percentile": row.percentile,
                    "grade": row.grade,
                    "theta": row.theta,
                }
            )
        attempt.results = results
    await session.commit()


async def record_attempt(
    session: AsyncSession,
    test: Test,
    user_id: int,
    subject: str | None,
    answers: dict[str, Any],
) -> Attempt:
    """Grade a submission, score it against all three cohorts, and store it."""
    items = items_for(test)
    tables = await ensure_tables(session, test)
    result = score_attempt(items, answers, tables)

    attempt = Attempt(
        test_id=test.id,
        user_id=user_id,
        subject=subject,
        answers=answers,
        per_item=result.per_item,
        raw_correct=result.raw_correct,
        total_items=result.total_items,
        results=[asdict(scenario) for scenario in result.scenarios],
    )
    session.add(attempt)
    await session.commit()
    await session.refresh(attempt)
    return attempt
