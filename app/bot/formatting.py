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


_MEDALS = ["\U0001f947", "\U0001f948", "\U0001f949"]  # 🥇🥈🥉


def render_leaderboard(
    test: Test,
    attempts: list[Attempt],
    owner_name: str,
    users: dict[int, str] | None = None,
) -> str:
    """Leaderboard message sent when a test is closed."""
    if not attempts:
        return texts.NO_PARTICIPANTS

    users = users or {}
    # Rank by raw_correct descending, then by submission time ascending
    ranked = sorted(attempts, key=lambda a: (-a.raw_correct, a.submitted_at))

    lines = [
        texts.LEADERBOARD_HEADER.format(
            owner=owner_name,
            code=test.code,
            questions=test.question_count,
        )
    ]

    for i, attempt in enumerate(ranked):
        medal = _MEDALS[i] if i < len(_MEDALS) else ""
        name = users.get(attempt.user_id) or f"ID:{attempt.user_id}"
        lines.append(
            texts.LEADERBOARD_ROW.format(
                rank=i + 1,
                name=name,
                correct=attempt.raw_correct,
                medal=medal,
            )
        )

    # Show answer key
    answer_parts = []
    for q in sorted(test.questions or [], key=lambda x: int(x.get("number", 0))):
        num = q.get("number", "?")
        if q.get("type") == "mc":
            answer_parts.append(f"{num}.{q.get('answer', '?').lower()}")
        else:
            parts = q.get("parts", {})
            for part_key in sorted(parts.keys()):
                vals = parts[part_key]
                if vals:
                    answer_parts.append(f"{num}{part_key}={vals[0]}")

    if answer_parts:
        lines.append(texts.LEADERBOARD_ANSWERS.format(answers=" ".join(answer_parts)))

    lines.append(texts.LEADERBOARD_FOOTER)
    return "\n".join(lines)
