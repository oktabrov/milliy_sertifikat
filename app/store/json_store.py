"""JSON-file storage.

Three files under `DATA_DIR`: `users.json`, `tests.json`, `attempts.json`.
Everything is held in memory and the relevant file is rewritten whenever it
changes, which is fine at this scale — a sitting is 50-100 students and the
whole dataset is well under a megabyte.

Two things make that safe rather than merely convenient:

**Atomic writes.** Every save goes to a temporary file in the same directory,
is flushed and fsynced, then moved into place with `os.replace`, which is
atomic on POSIX. A crash mid-write leaves the previous file intact — never a
half-written one.

**A serialising lock.** Read-modify-write is the failure mode that loses data:
two students submit in the same second, both read the attempt list, both append,
both write, and one result disappears with no error. Every mutation here holds
`self._lock` for the whole read-modify-write cycle, so that interleaving cannot
happen.

The lock is an `asyncio.Lock`, which serialises within one event loop. **Run a
single uvicorn worker.** With two worker processes each would hold its own copy
of the data in memory and clobber the other's writes; no in-process lock can fix
that. The deployment in DEPLOY-alwaysdata.md runs one worker.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from app.store.models import Attempt, Test, User

logger = logging.getLogger(__name__)


def _write_atomic(path: Path, payload: Any) -> None:
    """Serialise `payload` to `path` without ever leaving a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=1)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(handle.name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(handle.name)
        raise


def _read_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8") as stream:
            data = json.load(stream)
    except (json.JSONDecodeError, OSError):
        logger.exception("Could not read %s; starting from an empty collection", path)
        return []
    return data if isinstance(data, list) else []


class Store:
    """All persistence for the bot. One instance per process."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self._lock = asyncio.Lock()

        self._users: dict[int, User] = {}
        self._tests: dict[int, Test] = {}
        self._attempts: dict[int, Attempt] = {}
        # Runtime configuration an admin can change without a redeploy.
        self._settings: dict[str, Any] = {}

        self._next_test_id = 1
        self._next_attempt_id = 1

    # --- files ---------------------------------------------------------------

    @property
    def _users_path(self) -> Path:
        return self.data_dir / "users.json"

    @property
    def _tests_path(self) -> Path:
        return self.data_dir / "tests.json"

    @property
    def _attempts_path(self) -> Path:
        return self.data_dir / "attempts.json"

    @property
    def _settings_path(self) -> Path:
        return self.data_dir / "settings.json"

    async def load(self) -> None:
        """Read every collection into memory. Call once at startup."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._users = {
            record["id"]: User.from_dict(record)
            for record in _read_json(self._users_path)
            if "id" in record
        }
        self._tests = {
            record["id"]: Test.from_dict(record)
            for record in _read_json(self._tests_path)
            if "id" in record
        }
        self._attempts = {
            record["id"]: Attempt.from_dict(record)
            for record in _read_json(self._attempts_path)
            if "id" in record
        }

        # settings.json is a single object, not a list like the others.
        self._settings = {}
        if self._settings_path.exists():
            try:
                with self._settings_path.open(encoding="utf-8") as stream:
                    loaded = json.load(stream)
                if isinstance(loaded, dict):
                    self._settings = loaded
            except (json.JSONDecodeError, OSError):
                logger.exception("Could not read %s; using defaults", self._settings_path)

        self._next_test_id = max(self._tests, default=0) + 1
        self._next_attempt_id = max(self._attempts, default=0) + 1

        logger.info(
            "Store loaded from %s: %d users, %d tests, %d attempts",
            self.data_dir,
            len(self._users),
            len(self._tests),
            len(self._attempts),
        )

    def _flush_users(self) -> None:
        _write_atomic(self._users_path, [user.to_dict() for user in self._users.values()])

    def _flush_tests(self) -> None:
        _write_atomic(self._tests_path, [test.to_dict() for test in self._tests.values()])

    def _flush_attempts(self) -> None:
        _write_atomic(
            self._attempts_path, [attempt.to_dict() for attempt in self._attempts.values()]
        )

    # --- users ---------------------------------------------------------------

    def get_user(self, user_id: int) -> User | None:
        return self._users.get(user_id)

    async def ensure_user(
        self, user_id: int, username: str | None = None, is_admin: bool = False
    ) -> User:
        """Fetch the user, creating the row on first contact."""
        async with self._lock:
            user = self._users.get(user_id)
            if user is None:
                user = User(id=user_id, username=username, is_admin=is_admin)
                self._users[user_id] = user
                self._flush_users()
            else:
                # Refresh both: a user created before an ADMIN_IDS change would
                # otherwise keep the stale flag for ever.
                changed = False
                if username is not None and user.username != username:
                    user.username = username
                    changed = True
                if user.is_admin != is_admin:
                    user.is_admin = is_admin
                    changed = True
                if changed:
                    self._flush_users()
            return user

    async def save_user(self, user: User) -> None:
        async with self._lock:
            self._users[user.id] = user
            self._flush_users()

    def all_users(self) -> list[User]:
        return list(self._users.values())

    # --- tests ---------------------------------------------------------------

    def get_test(self, test_id: int) -> Test | None:
        return self._tests.get(test_id)

    def get_test_by_code(self, code: str) -> Test | None:
        code = (code or "").strip()
        for test in self._tests.values():
            if test.code == code:
                return test
        return None

    def tests_by_owner(self, owner_id: int) -> list[Test]:
        tests = [test for test in self._tests.values() if test.owner_id == owner_id]
        tests.sort(key=lambda test: test.created_at, reverse=True)
        return tests

    async def create_test(
        self,
        code: str,
        title: str,
        owner_id: int,
        subjects: Iterable[str],
        questions: list[dict[str, Any]],
    ) -> Test:
        async with self._lock:
            # Re-check inside the lock: two teachers can race on the same code.
            for test in self._tests.values():
                if test.code == code:
                    raise ValueError("code already taken")

            test = Test(
                id=self._next_test_id,
                code=code,
                title=title,
                owner_id=owner_id,
                subjects=list(subjects),
                questions=questions,
            )
            self._tests[test.id] = test
            self._next_test_id += 1
            self._flush_tests()
            return test

    async def save_test(self, test: Test) -> None:
        async with self._lock:
            self._tests[test.id] = test
            self._flush_tests()

    def all_tests(self) -> list[Test]:
        return list(self._tests.values())

    # --- attempts ------------------------------------------------------------

    def get_attempt(self, test_id: int, user_id: int) -> Attempt | None:
        for attempt in self._attempts.values():
            if attempt.test_id == test_id and attempt.user_id == user_id:
                return attempt
        return None

    def attempts_by_test(self, test_id: int) -> list[Attempt]:
        return [attempt for attempt in self._attempts.values() if attempt.test_id == test_id]

    def attempts_by_user(self, user_id: int, limit: int | None = None) -> list[Attempt]:
        attempts = [attempt for attempt in self._attempts.values() if attempt.user_id == user_id]
        attempts.sort(key=lambda attempt: attempt.submitted_at, reverse=True)
        return attempts[:limit] if limit else attempts

    async def create_attempt(
        self,
        test_id: int,
        user_id: int,
        subject: str | None,
        answers: dict[str, Any],
        per_item: dict[str, Any],
        raw_correct: int,
        total_items: int,
        results: list[dict[str, Any]],
    ) -> Attempt:
        """Record a submission.

        Raises `ValueError` if this student already answered this test — the
        check happens inside the lock, so two simultaneous submissions cannot
        both slip through.
        """
        async with self._lock:
            for attempt in self._attempts.values():
                if attempt.test_id == test_id and attempt.user_id == user_id:
                    raise ValueError("already submitted")

            attempt = Attempt(
                id=self._next_attempt_id,
                test_id=test_id,
                user_id=user_id,
                subject=subject,
                answers=answers,
                per_item=per_item,
                raw_correct=raw_correct,
                total_items=total_items,
                results=results,
            )
            self._attempts[attempt.id] = attempt
            self._next_attempt_id += 1
            self._flush_attempts()
            return attempt

    async def save_attempts(self, attempts: Iterable[Attempt]) -> None:
        """Persist several attempts in one write, as rescoring does."""
        async with self._lock:
            for attempt in attempts:
                self._attempts[attempt.id] = attempt
            self._flush_attempts()

    def count_attempts(self, test_id: int) -> int:
        return sum(1 for attempt in self._attempts.values() if attempt.test_id == test_id)

    # --- runtime settings ----------------------------------------------------

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def has_setting(self, key: str) -> bool:
        """Distinguishes "never configured" from "configured to nothing".

        An admin who removes every required channel must not silently fall back
        to whatever REQUIRED_CHANNELS says in .env.
        """
        return key in self._settings

    async def set_setting(self, key: str, value: Any) -> None:
        async with self._lock:
            self._settings[key] = value
            _write_atomic(self._settings_path, self._settings)

    # --- misc ----------------------------------------------------------------

    def stats(self) -> tuple[int, int, int]:
        return len(self._users), len(self._tests), len(self._attempts)


_store: Store | None = None


def get_store() -> Store:
    """The process-wide store. `init_store` must have run first."""
    if _store is None:
        raise RuntimeError("store not initialised; call init_store() during startup")
    return _store


async def init_store(data_dir: str | Path) -> Store:
    global _store
    _store = Store(data_dir)
    await _store.load()
    return _store


def reset_store() -> None:
    """Drop the process-wide store. Used by tests."""
    global _store
    _store = None
