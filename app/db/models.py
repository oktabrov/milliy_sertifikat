"""Database schema.

Questions and score tables are stored as JSON documents rather than in child
tables. A test is authored, read and scored as one whole — nothing ever queries
"all questions with option count 6" — so a document column is the honest shape
and keeps the same code working on SQLite locally and PostgreSQL on alwaysdata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    # Telegram user id, used directly as the primary key.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    full_name: Mapped[str | None] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tests: Mapped[list["Test"]] = relationship(back_populates="owner")
    attempts: Mapped[list["Attempt"]] = relationship(back_populates="user")


class Test(Base):
    __tablename__ = "tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))

    # ["Matematika", "Fizika"] — drives the "Fanni tanlang" dropdown.
    subjects: Mapped[list[str]] = mapped_column(JSON, default=list)

    # [{number, type: mc|open, options?, answer?, parts?: {a, b}}]
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    # open | closed
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Cached output of scoring.grader.tables_for_test, keyed by scenario.
    score_tables: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # How many real submissions the cached tables were calibrated from. 0 means
    # the default difficulty profile is still in use.
    calibrated_from: Mapped[int] = mapped_column(Integer, default=0)

    owner: Mapped[User] = relationship(back_populates="tests")
    attempts: Mapped[list["Attempt"]] = relationship(
        back_populates="test", cascade="all, delete-orphan"
    )

    @property
    def question_count(self) -> int:
        return len(self.questions or [])


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (UniqueConstraint("test_id", "user_id", name="uq_attempt_once"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_id: Mapped[int] = mapped_column(Integer, ForeignKey("tests.id"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)

    subject: Mapped[str | None] = mapped_column(String(64))

    # Raw submission, keyed by item key ("12", "36a").
    answers: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Per-item correctness, same keys.
    per_item: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    raw_correct: Mapped[int] = mapped_column(Integer, default=0)
    total_items: Mapped[int] = mapped_column(Integer, default=0)

    # [{key, label_uz, ball, percentile, grade, theta}] — one per scenario.
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    test: Mapped[Test] = relationship(back_populates="attempts")
    user: Mapped[User] = relationship(back_populates="attempts")


class Setting(Base):
    """Small key/value store for things an admin flips at runtime."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
