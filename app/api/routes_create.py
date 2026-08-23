"""Mini App API: authoring a test."""

from __future__ import annotations

import logging
import random
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from app.api.auth import WebAppUser, require_web_app_user
from app.api.gate import require_membership
from app.bot import texts
from app.store.json_store import Store, get_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["create"])

MAX_QUESTIONS = 120
# Per part. Generous, but stops an author pasting a novel into the answer key.
MAX_ACCEPTED_ANSWERS = 20


class QuestionIn(BaseModel):
    number: int
    type: str = "mc"
    options: int = 4
    answer: str | None = None
    # Each part maps to every answer the author accepts: {"a": ["3/4", "0.75"]}.
    parts: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def known_type(cls, value: str) -> str:
        if value not in ("mc", "open"):
            raise ValueError("type must be 'mc' or 'open'")
        return value

    @field_validator("parts", mode="before")
    @classmethod
    def coerce_parts(cls, value: Any) -> Any:
        """Accept a bare string per part as well as a list.

        Keeps answer keys authored before multiple accepted answers existed
        working, and tolerates a client that sends a single value.
        """
        if not isinstance(value, dict):
            return value
        coerced: dict[str, list[str]] = {}
        for key, entry in value.items():
            if isinstance(entry, str):
                coerced[key] = [entry]
            elif isinstance(entry, (list, tuple)):
                coerced[key] = [str(item) for item in entry]
            elif entry is None:
                coerced[key] = []
            else:
                coerced[key] = [str(entry)]
        return coerced

    @field_validator("options")
    @classmethod
    def sane_options(cls, value: int) -> int:
        if not 2 <= value <= 6:
            raise ValueError("options must be between 2 and 6")
        return value


class CreateTestIn(BaseModel):
    title: str
    subjects: list[str] = Field(default_factory=list)
    questions: list[QuestionIn]
    code: str | None = None

    @field_validator("title")
    @classmethod
    def non_empty_title(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("title too short")
        return value[:160]

    @field_validator("questions")
    @classmethod
    def sane_questions(cls, value: list[QuestionIn]) -> list[QuestionIn]:
        if not value:
            raise ValueError("a test needs at least one question")
        if len(value) > MAX_QUESTIONS:
            raise ValueError(f"at most {MAX_QUESTIONS} questions")
        return value


class CreateTestOut(BaseModel):
    code: str
    title: str
    question_count: int


def _pick_code(store: Store, preferred: str | None) -> str:
    """Short numeric code, like the ones teachers share.

    Only a candidate — `Store.create_test` re-checks uniqueness under its lock,
    which is what actually prevents two teachers claiming the same code.
    """
    if preferred:
        candidate = preferred.strip()
        if not candidate.isdigit() or not 1 <= len(candidate) <= 8:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Test kodi 1-8 xonali son bo'lishi kerak"
            )
        if store.get_test_by_code(candidate) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Bu kod band. Boshqa kod tanlang")
        return candidate

    for _ in range(40):
        candidate = str(random.randint(1000, 9999))
        if store.get_test_by_code(candidate) is None:
            return candidate
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Kod yaratib bo'lmadi, qayta urining")


def _validate_answer_key(questions: list[QuestionIn]) -> None:
    """Every question must carry an answer, or the test cannot be scored."""
    for question in questions:
        if question.type == "mc":
            letter = (question.answer or "").strip().upper()
            # Membership must be tested against the individual letters: every
            # string is a substring of "ABCD", including "" and "AB".
            allowed = set("ABCDEF"[: question.options])
            if letter not in allowed:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"{question.number}-savol uchun to'g'ri javob tanlanmagan",
                )
        else:
            filled = _clean_parts(question.parts)
            if not filled:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"{question.number}-savol uchun kamida bitta javob yozing",
                )
            for part, options in filled.items():
                if len(options) > MAX_ACCEPTED_ANSWERS:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        f"{question.number}-savol {part}) uchun javoblar soni "
                        f"{MAX_ACCEPTED_ANSWERS} tadan oshmasligi kerak",
                    )


def _clean_parts(parts: dict[str, list[str]]) -> dict[str, list[str]]:
    """Drop blank answers and duplicates, keeping the author's order."""
    cleaned: dict[str, list[str]] = {}
    for part, options in parts.items():
        seen: set[str] = set()
        kept: list[str] = []
        for option in options:
            text = str(option).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            kept.append(text)
        if kept:
            cleaned[part] = kept
    return cleaned

MAX_TESTS_PER_USER = 5


@router.post("/test", response_model=CreateTestOut, status_code=status.HTTP_201_CREATED)
async def create_test(
    payload: CreateTestIn,
    request: Request,
    background: BackgroundTasks,
    web_app_user: WebAppUser = Depends(require_web_app_user),
) -> CreateTestOut:
    await require_membership(request, web_app_user.id)
    _validate_answer_key(payload.questions)

    store = get_store()
    user = await store.ensure_user(web_app_user.id, username=web_app_user.username)
    if not user.full_name and web_app_user.full_name:
        user.full_name = web_app_user.full_name
        await store.save_user(user)

    # Enforce 5-test limit: delete the oldest if at capacity
    existing = store.tests_by_owner(user.id)  # sorted newest-first
    deleted_test = None
    if len(existing) >= MAX_TESTS_PER_USER:
        oldest = existing[-1]  # last = oldest
        deleted_test = oldest
        await store.delete_test(oldest.id)

    code = _pick_code(store, payload.code)

    questions = []
    for question in sorted(payload.questions, key=lambda item: item.number):
        if question.type == "mc":
            questions.append(
                {
                    "number": question.number,
                    "type": "mc",
                    "options": question.options,
                    "answer": (question.answer or "").strip().upper(),
                }
            )
        else:
            questions.append(
                {"number": question.number, "type": "open", "parts": _clean_parts(question.parts)}
            )

    try:
        test = await store.create_test(
            code=code,
            title=payload.title,
            owner_id=user.id,
            subjects=[subject.strip() for subject in payload.subjects if subject.strip()],
            questions=questions,
        )
    except ValueError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Bu kod band. Boshqa kod tanlang"
        ) from None

    bot = getattr(request.app.state, "bot", None)
    if bot is not None:
        if deleted_test:
            background.add_task(
                _notify_test_deleted, bot, user.id, deleted_test.title, deleted_test.code
            )
        background.add_task(_notify_created, bot, user.id, test.title, test.code, len(questions))

    return CreateTestOut(code=test.code, title=test.title, question_count=len(questions))


async def _notify_test_deleted(bot, chat_id: int, title: str, code: str) -> None:
    try:
        await bot.send_message(
            chat_id,
            texts.TEST_LIMIT_REACHED.format(title=title, code=code),
        )
    except Exception:
        logger.exception("Could not notify %s about deleted test %s", chat_id, code)


async def _notify_created(bot, chat_id: int, title: str, code: str, questions: int) -> None:
    try:
        await bot.send_message(
            chat_id,
            texts.TEST_CREATED.format(title=title, code=code, questions=questions),
        )
    except Exception:
        logger.exception("Could not notify %s about created test %s", chat_id, code)
