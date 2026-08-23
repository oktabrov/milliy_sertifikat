"""Mini App API: fetch a test, submit answers."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.auth import WebAppUser, require_web_app_user
from app.api.gate import require_membership
from app.bot import texts
from app.bot.keyboards import see_result_inline, submission_notify_inline
from app.services.scoring_service import record_attempt, recalibrate, items_for, ensure_tables
from app.scoring.grader import score_attempt
from app.store.json_store import Store, get_store
from app.store.models import Test

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["test"])

# In the Milliy sertifikat format questions 33-35 always carry six options
# (A-F). The builder already stores six for new tests; enforcing it here as
# well upgrades answer sheets of tests created before that was the case.
SIX_OPTION_QUESTIONS = frozenset({33, 34, 35})


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
    practice: bool = False


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
    """Test metadata and the shape of the answer sheet."""
    await require_membership(request, web_app_user.id)

    store = get_store()
    test = _load_test(store, code)

    questions = []
    for question in test.questions or []:
        if question.get("type") == "open":
            parts = sorted((question.get("parts") or {}).keys())
            questions.append(QuestionOut(number=int(question["number"]), type="open", parts=parts))
        else:
            number = int(question["number"])
            options = int(question.get("options", 4))
            questions.append(
                QuestionOut(
                    number=number,
                    type="mc",
                    options=max(options, 6) if number in SIX_OPTION_QUESTIONS else options,
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

    user = await store.ensure_user(web_app_user.id, username=web_app_user.username)
    if not user.full_name and web_app_user.full_name:
        user.full_name = web_app_user.full_name
        await store.save_user(user)

    # --- PRACTICE MODE: test is closed, score but don't store ---
    if test.status != "open":
        items = items_for(test)
        tables = await ensure_tables(store, test)
        result = score_attempt(items, payload.answers, tables)
        return SubmitOut(
            raw_correct=result.raw_correct,
            total_items=result.total_items,
            scenarios=[ScenarioOut(**asdict(s)) for s in result.scenarios],
            practice=True,
        )

    # --- NORMAL MODE: test is open, store and notify ---
    if store.get_attempt(test.id, user.id) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Siz bu testga allaqachon javob bergansiz"
        )

    try:
        attempt = await record_attempt(store, test, user.id, payload.subject, payload.answers)
    except ValueError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Siz bu testga allaqachon javob bergansiz"
        ) from None

    bot = getattr(request.app.state, "bot", None)
    if bot is not None:
        # Notify the student
        background.add_task(_notify_submitted, bot, user.id, test.code)
        # Notify the test creator
        student_name = user.full_name or user.username or f"ID:{user.id}"
        background.add_task(
            _notify_creator, bot, test.owner_id, test.code,
            student_name, attempt.raw_correct, attempt.total_items,
        )
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


async def _notify_creator(
    bot, owner_id: int, code: str, student_name: str, correct: int, total: int,
) -> None:
    """Notify the test creator that someone submitted answers."""
    try:
        await bot.send_message(
            owner_id,
            texts.SUBMISSION_NOTIFY.format(
                student=student_name, code=code, correct=correct, total=total,
            ),
            reply_markup=submission_notify_inline(code),
        )
    except Exception:
        logger.exception("Could not notify creator %s about submission to %s", owner_id, code)


async def _recalibrate_later(test_id: int) -> None:
    """Re-derive item difficulty from real responses once enough have arrived."""
    try:
        store = get_store()
        test = store.get_test(test_id)
        if test is not None:
            await recalibrate(store, test)
    except Exception:
        logger.exception("Recalibration failed for test id %s", test_id)
