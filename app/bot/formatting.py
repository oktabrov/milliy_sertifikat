"""Rendering attempts and tests as Telegram messages."""

from __future__ import annotations

from app.bot import texts
from app.store.models import Attempt, Test


def render_result(attempt: Attempt, test: Test, student_name: str) -> str:
    """The three-scenario result block a student sees."""
    lines = [
        texts.RESULT_HEADER.format(
            title=test.title,
            name=student_name,
            correct=attempt.raw_correct,
            total=attempt.total_items,
        )
    ]
    for row in attempt.results or []:
        lines.append(
            texts.RESULT_ROW.format(
                label=row.get("label_uz", row.get("key", "")),
                ball=row.get("ball", 0),
                percentile=row.get("percentile", 0),
                grade=row.get("grade", "—"),
            )
        )
    lines.append(texts.RESULT_FOOTER)
    return "\n".join(lines)


def render_test_row(test: Test, participants: int) -> str:
    return texts.TEST_ROW.format(
        title=test.title,
        code=test.code,
        questions=test.question_count,
        participants=participants,
        status=texts.STATUS_LABELS.get(test.status, test.status),
    )
