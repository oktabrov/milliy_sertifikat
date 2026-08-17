"""The JSON store — durability and the concurrency guarantees it claims."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.store.json_store import Store, _write_atomic
from app.store.models import Attempt, Test, User


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path)


def sample_questions() -> list[dict]:
    return [{"number": 1, "type": "mc", "options": 4, "answer": "A"}]


@pytest.mark.asyncio
async def test_load_on_an_empty_directory(store: Store):
    await store.load()
    assert store.stats() == (0, 0, 0)


@pytest.mark.asyncio
async def test_users_survive_a_reload(store: Store, tmp_path: Path):
    await store.load()
    user = await store.ensure_user(42, username="sardor")
    user.full_name = "Torayev Sardor"
    await store.save_user(user)

    reopened = Store(tmp_path)
    await reopened.load()
    restored = reopened.get_user(42)
    assert restored is not None
    assert restored.full_name == "Torayev Sardor"
    assert restored.username == "sardor"


@pytest.mark.asyncio
async def test_tests_and_attempts_survive_a_reload(store: Store, tmp_path: Path):
    await store.load()
    await store.ensure_user(1)
    test = await store.create_test("777", "Test №1", 1, ["Matematika"], sample_questions())
    await store.create_attempt(test.id, 1, "Matematika", {"1": "A"}, {"1": True}, 1, 1, [])

    reopened = Store(tmp_path)
    await reopened.load()
    restored = reopened.get_test_by_code("777")
    assert restored is not None
    assert restored.questions == sample_questions()
    assert reopened.get_attempt(restored.id, 1) is not None
    assert reopened.stats() == (1, 1, 1)


@pytest.mark.asyncio
async def test_ids_continue_after_a_reload(store: Store, tmp_path: Path):
    """A restart must not reuse an id and overwrite an existing record."""
    await store.load()
    await store.ensure_user(1)
    first = await store.create_test("100", "A", 1, [], sample_questions())

    reopened = Store(tmp_path)
    await reopened.load()
    second = await reopened.create_test("101", "B", 1, [], sample_questions())

    assert second.id > first.id
    assert reopened.get_test(first.id) is not None
    assert reopened.get_test(second.id) is not None


@pytest.mark.asyncio
async def test_duplicate_test_code_is_refused(store: Store):
    await store.load()
    await store.ensure_user(1)
    await store.create_test("500", "A", 1, [], sample_questions())
    with pytest.raises(ValueError):
        await store.create_test("500", "B", 1, [], sample_questions())


@pytest.mark.asyncio
async def test_duplicate_attempt_is_refused(store: Store):
    await store.load()
    test = await store.create_test("501", "A", 1, [], sample_questions())
    await store.create_attempt(test.id, 7, None, {}, {}, 0, 1, [])
    with pytest.raises(ValueError):
        await store.create_attempt(test.id, 7, None, {}, {}, 0, 1, [])


@pytest.mark.asyncio
async def test_concurrent_submissions_do_not_lose_each_other(store: Store, tmp_path: Path):
    """The failure mode that makes naive JSON storage dangerous.

    Fifty students submit at once. With an unguarded read-modify-write, some
    would append to a stale list and silently vanish. Every one must survive,
    both in memory and on disk.
    """
    await store.load()
    test = await store.create_test("600", "A", 1, [], sample_questions())

    await asyncio.gather(
        *[
            store.create_attempt(test.id, user_id, None, {"1": "A"}, {"1": True}, 1, 1, [])
            for user_id in range(1000, 1050)
        ]
    )

    assert store.count_attempts(test.id) == 50
    assert len({attempt.id for attempt in store.attempts_by_test(test.id)}) == 50

    reopened = Store(tmp_path)
    await reopened.load()
    assert reopened.count_attempts(test.id) == 50


@pytest.mark.asyncio
async def test_concurrent_duplicate_submissions_yield_exactly_one(store: Store):
    """The same student double-tapping submit must not create two attempts."""
    await store.load()
    test = await store.create_test("601", "A", 1, [], sample_questions())

    outcomes = await asyncio.gather(
        *[
            store.create_attempt(test.id, 55, None, {}, {}, 0, 1, [])
            for _ in range(8)
        ],
        return_exceptions=True,
    )

    created = [item for item in outcomes if isinstance(item, Attempt)]
    refused = [item for item in outcomes if isinstance(item, ValueError)]
    assert len(created) == 1
    assert len(refused) == 7
    assert store.count_attempts(test.id) == 1


@pytest.mark.asyncio
async def test_concurrent_test_creation_cannot_duplicate_a_code(store: Store):
    await store.load()
    outcomes = await asyncio.gather(
        *[store.create_test("900", f"T{i}", 1, [], sample_questions()) for i in range(6)],
        return_exceptions=True,
    )
    created = [item for item in outcomes if isinstance(item, Test)]
    assert len(created) == 1


def test_write_is_atomic_and_leaves_no_temp_files(tmp_path: Path):
    target = tmp_path / "users.json"
    _write_atomic(target, [{"id": 1}])
    _write_atomic(target, [{"id": 1}, {"id": 2}])

    assert json.loads(target.read_text()) == [{"id": 1}, {"id": 2}]
    leftovers = [path.name for path in tmp_path.iterdir() if path.name != "users.json"]
    assert leftovers == []


@pytest.mark.asyncio
async def test_a_corrupt_file_does_not_prevent_startup(tmp_path: Path):
    """Half a JSON file should degrade to an empty collection, not a crash."""
    (tmp_path / "users.json").write_text('[{"id": 1, "full_na')
    store = Store(tmp_path)
    await store.load()
    assert store.stats() == (0, 0, 0)

    # And the store must still be usable afterwards.
    user = await store.ensure_user(9)
    assert user.id == 9


@pytest.mark.asyncio
async def test_unicode_names_round_trip(store: Store, tmp_path: Path):
    await store.load()
    user = await store.ensure_user(3)
    user.full_name = "To‘rayev Sardor O‘g‘li"
    await store.save_user(user)

    reopened = Store(tmp_path)
    await reopened.load()
    assert reopened.get_user(3).full_name == "To‘rayev Sardor O‘g‘li"


@pytest.mark.asyncio
async def test_attempts_by_user_is_newest_first(store: Store):
    await store.load()
    first = await store.create_test("801", "A", 1, [], sample_questions())
    second = await store.create_test("802", "B", 1, [], sample_questions())
    a = await store.create_attempt(first.id, 5, None, {}, {}, 0, 1, [])
    b = await store.create_attempt(second.id, 5, None, {}, {}, 0, 1, [])
    b.submitted_at = a.submitted_at.replace(year=a.submitted_at.year + 1)
    await store.save_attempts([b])

    assert [attempt.id for attempt in store.attempts_by_user(5)] == [b.id, a.id]


@pytest.mark.asyncio
async def test_tests_by_owner_only_returns_that_owner(store: Store):
    await store.load()
    await store.create_test("810", "Mine", 1, [], sample_questions())
    await store.create_test("811", "Theirs", 2, [], sample_questions())
    assert [test.code for test in store.tests_by_owner(1)] == ["810"]


def test_models_round_trip_through_dicts():
    user = User(id=1, full_name="A B", username="ab", is_admin=True)
    assert User.from_dict(user.to_dict()).to_dict() == user.to_dict()

    test = Test(id=2, code="9", title="T", owner_id=1, questions=sample_questions())
    assert Test.from_dict(test.to_dict()).to_dict() == test.to_dict()

    attempt = Attempt(id=3, test_id=2, user_id=1, raw_correct=4, total_items=5)
    assert Attempt.from_dict(attempt.to_dict()).to_dict() == attempt.to_dict()
