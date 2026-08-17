"""Mini App API: fetch a test, submit answers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.auth import WebAppUser, require_web_app_user
from app.api.gate import require_membership
from app.bot import texts
from app.bot.keyboards import see_result_inline
from app.services.scoring_service import record_attempt, recalibrate
from app.store.json_store import Store, get_store
from app.store.models import Test

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


def _load_test(store: Store, code: str) -> Test:
    test = store.get_test_by_code(code)
    if test is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bunday kodli test topilmadi")
    return test


@router.get("/test/{code}", response_model=TestOut)
async def get_test(
    code: str,
    request: Request,
    web_app_user: WebAppUser = Depends(require_web_app_user),
) -> TestOut:
    """Test metadata and the shape of the answer sheet.

    Correct answers are never included — the sheet only needs to know how many
    options each question has.
    """
    await require_membership(request, web_app_user.id)

    store = get_store()
    test = _load_test(store, code)

    questions = []
    for question in test.questions or []:
        if question.get("type") == "open":
            parts = sorted((question.get("parts") or {}).keys())
            questions.append(QuestionOut(number=int(question["number"]), type="open", parts=parts))
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
        already_submitted=store.get_attempt(test.id, web_app_user.id) is not None,
        questions=questions,
    )


@router.post("/attempt", response_model=SubmitOut)
async def submit_attempt(
    payload: SubmitIn,
    request: Request,
    background: BackgroundTasks,
    web_app_user: WebAppUser = Depends(require_web_app_user),
) -> SubmitOut:
    await require_membership(request, web_app_user.id)

    store = get_store()
    test = _load_test(store, payload.code)

    if test.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu test yopilgan")

    user = await store.ensure_user(web_app_user.id, username=web_app_user.username)
    if not user.full_name and web_app_user.full_name:
        user.full_name = web_app_user.full_name
        await store.save_user(user)

    try:
        attempt = await record_attempt(store, test, user.id, payload.subject, payload.answers)
    except ValueError:
        # The store re-checks under its lock, so a duplicate that slipped past
        # an earlier read still lands here rather than creating a second row.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Siz bu testga allaqachon javob bergansiz"
        ) from None

    bot = getattr(request.app.state, "bot", None)
    if bot is not None:
        background.add_task(_notify_submitted, bot, user.id, test.code)
    background.add_task(_recalibrate_later, test.id)

    return SubmitOut(
        raw_correct=attempt.raw_correct,
        total_items=attempt.total_items,
        scenarios=[ScenarioOut(**row) for row in _scenario_rows(attempt.results)],
    )


def _scenario_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "key": row["key"],
            "label_uz": row["label_uz"],
            "ball": row["ball"],
            "percentile": row["percentile"],
            "grade": row["grade"],
        }
        for row in results or []
    ]


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
    """Re-derive item difficulty from real responses once enough have arrived."""
    try:
        store = get_store()
        test = store.get_test(test_id)
        if test is not None:
            await recalibrate(store, test)
    except Exception:
        logger.exception("Recalibration failed for test id %s", test_id)
