"""Records held in the JSON store.

Plain dataclasses with explicit `to_dict` / `from_dict`, so the on-disk shape is
visible in one place and a hand-edited data file is easy to reason about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@dataclass
class User:
    id: int
    full_name: str | None = None
    username: str | None = None
    is_admin: bool = False
    is_blocked: bool = False
    created_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "username": self.username,
            "is_admin": self.is_admin,
            "is_blocked": self.is_blocked,
            "created_at": _iso(self.created_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "User":
        return cls(
            id=int(data["id"]),
            full_name=data.get("full_name"),
            username=data.get("username"),
            is_admin=bool(data.get("is_admin", False)),
            is_blocked=bool(data.get("is_blocked", False)),
            created_at=_parse(data.get("created_at")) or utcnow(),
        )


@dataclass
class Test:
    # Stops pytest trying to collect this as a test class on account of its name.
    __test__ = False

    id: int
    code: str
    title: str
    owner_id: int
    subjects: list[str] = field(default_factory=list)
    # [{number, type: mc|open, options?, answer?, parts?: {a, b}}]
    questions: list[dict[str, Any]] = field(default_factory=list)
    status: str = "open"
    created_at: datetime = field(default_factory=utcnow)
    closes_at: datetime | None = None
    # Cached scoring.grader.tables_for_test output, keyed by scenario.
    score_tables: dict[str, Any] | None = None
    # How many real submissions the cached tables were calibrated from; 0 means
    # the default difficulty profile is still in use.
    calibrated_from: int = 0

    @property
    def question_count(self) -> int:
        return len(self.questions or [])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "title": self.title,
            "owner_id": self.owner_id,
            "subjects": self.subjects,
            "questions": self.questions,
            "status": self.status,
            "created_at": _iso(self.created_at),
            "closes_at": _iso(self.closes_at),
            "score_tables": self.score_tables,
            "calibrated_from": self.calibrated_from,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Test":
        return cls(
            id=int(data["id"]),
            code=str(data["code"]),
            title=data.get("title", ""),
            owner_id=int(data.get("owner_id", 0)),
            subjects=list(data.get("subjects") or []),
            questions=list(data.get("questions") or []),
            status=data.get("status", "open"),
            created_at=_parse(data.get("created_at")) or utcnow(),
            closes_at=_parse(data.get("closes_at")),
            score_tables=data.get("score_tables"),
            calibrated_from=int(data.get("calibrated_from", 0)),
        )


@dataclass
class Attempt:
    id: int
    test_id: int
    user_id: int
    subject: str | None = None
    # Raw submission keyed by item key ("12", "36a").
    answers: dict[str, Any] = field(default_factory=dict)
    # Per-item correctness, same keys.
    per_item: dict[str, Any] = field(default_factory=dict)
    raw_correct: int = 0
    total_items: int = 0
    # [{key, label_uz, ball, percentile, grade, theta}] — one per scenario.
    results: list[dict[str, Any]] = field(default_factory=list)
    submitted_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "test_id": self.test_id,
            "user_id": self.user_id,
            "subject": self.subject,
            "answers": self.answers,
            "per_item": self.per_item,
            "raw_correct": self.raw_correct,
            "total_items": self.total_items,
            "results": self.results,
            "submitted_at": _iso(self.submitted_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Attempt":
        return cls(
            id=int(data["id"]),
            test_id=int(data["test_id"]),
            user_id=int(data["user_id"]),
            subject=data.get("subject"),
            answers=dict(data.get("answers") or {}),
            per_item=dict(data.get("per_item") or {}),
            raw_correct=int(data.get("raw_correct", 0)),
            total_items=int(data.get("total_items", 0)),
            results=list(data.get("results") or []),
            submitted_at=_parse(data.get("submitted_at")) or utcnow(),
        )
