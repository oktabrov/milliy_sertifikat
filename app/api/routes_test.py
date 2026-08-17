"""Mini App API: fetch a test, submit answers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import WebAppUser, require_web_app_user
from app.bot import texts
from app.bot.keyboards import see_result_inline
from app.db.base import SessionLocal, get_session
from app.db.models import Attempt, Test, User
from app.services.scoring_service import record_attempt, recalibrate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["test"])


class QuestionOut(BaseModel):
    number: int
    type: str
    options: int = 4
    parts: list[str] = Field(default_factory=list)


class TestOut(BaseModel):
    code: str
    title: str
    subjects: list[str]
    question_count: int
    status: str
    already_submitted: bool
    questions: list[QuestionOut]


class SubmitIn(BaseModel):
    code: str
    subject: str | None = None
    # Keys are item keys: "12" for multiple choice, "36a"/"36b" for open parts.
    answers: dict[str, str] = Field(default_factory=dict)


class ScenarioOut(BaseModel):
    key: str
    label_uz: str
    ball: int
    percentile: float
    grade: str


class SubmitOut(BaseModel):
    raw_correct: int
    total_items: int
    scenarios: list[ScenarioOut]


async def _load_test(session: AsyncSession, code: str) -> Test:
    test = (
        await session.execute(select(Test).where(Test.code == code.strip()))
    ).scalar_one_or_none()
    if test is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bunday kodli test topilmadi")
    return test


@router.get("/test/{code}", response_model=TestOut)
async def get_test(
    code: str,
    web_app_user: WebAppUser = Depends(require_web_app_user),
    session: AsyncSession = Depends(get_session),
) -> TestOut:
    """Test metadata and the shape of the answer sheet.

    Correct answers are never included — the sheet only needs to know how many
    options each question has.
    """
    test = await _load_test(session, code)

    existing = (
        await session.execute(
            select(Attempt.id).where(
                Attempt.test_id == test.id, Attempt.user_id == web_app_user.id
            )
        )
    ).scalar_one_or_none()

    questions = []
    for question in test.questions or []:
        if question.get("type") == "open":
            parts = sorted((question.get("parts") or {}).keys())
            questions.append(
                QuestionOut(number=int(question["number"]), type="open", parts=parts)
            )
        else:
            questions.append(
                QuestionOut(
                    number=int(question["number"]),
                    type="mc",
                    options=int(question.get("options", 4)),
                )
            )

    return TestOut(
        code=test.code,
        title=test.title,
        subjects=test.subjects or [],
        question_count=len(questions),
        status=test.status,
        already_submitted=existing is not None,
        questions=questions,
    )


@router.post("/attempt", response_model=SubmitOut)
async def submit_attempt(
    payload: SubmitIn,
    request: Request,
    background: BackgroundTasks,
    web_app_user: WebAppUser = Depends(require_web_app_user),
    session: AsyncSession = Depends(get_session),
) -> SubmitOut:
    test = await _load_test(session, payload.code)

    if test.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu test yopilgan")

    user = await session.get(User, web_app_user.id)
    if user is None:
        user = User(
            id=web_app_user.id,
            full_name=web_app_user.full_name or None,
            username=web_app_user.username,
        )
        session.add(user)
        await session.commit()

    already = (
        await session.execute(
            select(Attempt.id).where(Attempt.test_id == test.id, Attempt.user_id == user.id)
        )
    ).scalar_one_or_none()
    if already is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Siz bu testga allaqachon javob bergansiz")

    attempt = await record_attempt(session, test, user.id, payload.subject, payload.answers)

    bot = getattr(request.app.state, "bot", None)
    if bot is not None:
        background.add_task(_notify_submitted, bot, user.id, test.code)
    background.add_task(_recalibrate_later, test.id)

    return SubmitOut(
        raw_correct=attempt.raw_correct,
        total_items=attempt.total_items,
        scenarios=[ScenarioOut(**row) for row in _scenario_rows(attempt)],
    )


def _scenario_rows(attempt: Attempt) -> list[dict[str, Any]]:
    rows = []
    for row in attempt.results or []:
        rows.append(
            {
                "key": row["key"],
                "label_uz": row["label_uz"],
                "ball": row["ball"],
                "percentile": row["percentile"],
                "grade": row["grade"],
            }
        )
    return rows


async def _notify_submitted(bot, chat_id: int, code: str) -> None:
    try:
        await bot.send_message(
            chat_id,
            texts.SUBMITTED.format(code=code),
            reply_markup=see_result_inline(code),
        )
    except Exception:
        logger.exception("Could not notify %s about submission to %s", chat_id, code)


async def _recalibrate_later(test_id: int) -> None:
    """Re-derive item difficulty from real responses once enough have arrived.

    Runs in its own session because the request's session is closed by the time
    background tasks execute.
    """
    try:
        async with SessionLocal() as session:
            test = await session.get(Test, test_id)
            if test is not None:
                await recalibrate(session, test)
    except Exception:
        logger.exception("Recalibration failed for test id %s", test_id)
