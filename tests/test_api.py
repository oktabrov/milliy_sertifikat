"""End-to-end API: author a test, answer it, get three results back."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.conftest import TEST_BOT_TOKEN
from tests.test_auth import make_init_data


def auth_headers(user_id: int = 42, first_name: str = "Sardor") -> dict[str, str]:
    init_data = make_init_data({"id": user_id, "first_name": first_name}, token=TEST_BOT_TOKEN)
    return {"Authorization": f"tma {init_data}"}


def sample_payload(code: str | None = None) -> dict:
    questions = [
        {"number": number, "type": "mc", "options": 4, "answer": "A"} for number in range(1, 9)
    ]
    questions.append({"number": 9, "type": "open", "parts": {"a": "50/3", "b": "2"}})
    return {
        "title": "Test №1",
        "subjects": ["Matematika", "Fizika"],
        "questions": questions,
        "code": code,
    }


@pytest_asyncio.fixture
async def client(tmp_path):
    """A fresh store per test, so tests cannot see each other's data."""
    from app.main import app
    from app.store.json_store import init_store, reset_store

    await init_store(tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    reset_store()


@pytest.mark.asyncio
async def test_health_reports_a_bot_that_cannot_receive_updates(client):
    """Neither polling nor a webhook base is configured in tests.

    That is a bot which cannot receive anything, and the endpoint must say so
    rather than answering a cheerful 200 — the exact failure that hid a dead
    bot behind a healthy-looking site in production.
    """
    response = await client.get("/healthz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["bot_ready"] is False
    assert body["mode"] == "webhook"
    assert body["webhook_error"] == "WEBHOOK_BASE is not set"


@pytest.mark.asyncio
async def test_health_is_ok_once_the_webhook_registers(client):
    from app.main import app

    app.state.webhook_ok = True
    app.state.webhook_error = None
    try:
        response = await client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["bot_ready"] is True
    finally:
        app.state.webhook_ok = False


@pytest.mark.asyncio
async def test_health_never_leaks_the_webhook_secret(client):
    """The path contains WEBHOOK_SECRET and this endpoint is public."""
    from app.config import get_settings

    from app.main import app

    app.state.webhook_ok = True
    try:
        body = (await client.get("/healthz")).text
    finally:
        app.state.webhook_ok = False
    assert get_settings().webhook_secret not in body
    assert "/webhook/" not in body


@pytest.mark.asyncio
async def test_api_requires_valid_init_data(client):
    response = await client.get("/api/test/1234")
    assert response.status_code == 401

    response = await client.get("/api/test/1234", headers={"Authorization": "tma forged=1&hash=00"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_then_answer_a_test(client):
    created = await client.post("/api/test", json=sample_payload("777"), headers=auth_headers())
    assert created.status_code == 201, created.text
    assert created.json()["code"] == "777"
    assert created.json()["question_count"] == 9

    # The sheet must describe the questions without leaking the answer key.
    fetched = await client.get("/api/test/777", headers=auth_headers())
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["title"] == "Test №1"
    assert body["subjects"] == ["Matematika", "Fizika"]
    assert body["already_submitted"] is False
    assert "answer" not in str(body)
    assert body["questions"][-1] == {"number": 9, "type": "open", "options": 4, "parts": ["a", "b"]}

    answers = {str(number): "A" for number in range(1, 7)}
    answers["9a"] = r"\frac{50}{3}"
    answers["9b"] = "2 ta"

    submitted = await client.post(
        "/api/attempt",
        json={"code": "777", "subject": "Matematika", "answers": answers},
        headers=auth_headers(),
    )
    assert submitted.status_code == 200, submitted.text
    result = submitted.json()

    # 6 of 8 multiple choice, plus both open parts.
    assert result["raw_correct"] == 8
    assert result["total_items"] == 10

    scenarios = result["scenarios"]
    assert [row["key"] for row in scenarios] == ["weak", "normal", "strong"]
    assert [row["label_uz"] for row in scenarios] == ["Zaif guruh", "O'rtacha guruh", "Kuchli guruh"]
    balls = [row["ball"] for row in scenarios]
    assert balls == sorted(balls, reverse=True)


@pytest.mark.asyncio
async def test_second_submission_is_refused(client):
    await client.post("/api/test", json=sample_payload("778"), headers=auth_headers())
    payload = {"code": "778", "answers": {"1": "A"}}

    first = await client.post("/api/attempt", json=payload, headers=auth_headers())
    assert first.status_code == 200

    second = await client.post("/api/attempt", json=payload, headers=auth_headers())
    assert second.status_code == 409

    fetched = await client.get("/api/test/778", headers=auth_headers())
    assert fetched.json()["already_submitted"] is True


@pytest.mark.asyncio
async def test_unknown_code_is_a_404(client):
    response = await client.get("/api/test/000999", headers=auth_headers())
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_code_is_refused(client):
    first = await client.post("/api/test", json=sample_payload("779"), headers=auth_headers())
    assert first.status_code == 201
    second = await client.post("/api/test", json=sample_payload("779"), headers=auth_headers())
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_code_is_generated_when_omitted(client):
    response = await client.post("/api/test", json=sample_payload(None), headers=auth_headers())
    assert response.status_code == 201
    assert response.json()["code"].isdigit()


@pytest.mark.asyncio
async def test_a_test_without_an_answer_key_is_refused(client):
    payload = sample_payload("781")
    payload["questions"][0]["answer"] = ""
    response = await client.post("/api/test", json=payload, headers=auth_headers())
    assert response.status_code == 400
    assert "1-savol" in response.json()["error"]


@pytest.mark.asyncio
async def test_multi_letter_answer_key_is_refused(client):
    """"AB" is a substring of "ABCD"; membership must be per-letter."""
    payload = sample_payload("784")
    payload["questions"][0]["answer"] = "AB"
    response = await client.post("/api/test", json=payload, headers=auth_headers())
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_answer_outside_the_option_range_is_refused(client):
    payload = sample_payload("785")
    payload["questions"][0]["answer"] = "F"  # only 4 options exist
    response = await client.post("/api/test", json=payload, headers=auth_headers())
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_open_question_without_an_answer_is_refused(client):
    payload = sample_payload("782")
    payload["questions"][-1]["parts"] = {"a": "", "b": ""}
    response = await client.post("/api/test", json=payload, headers=auth_headers())
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_two_students_can_answer_the_same_test(client):
    await client.post("/api/test", json=sample_payload("783"), headers=auth_headers(user_id=1))

    strong = await client.post(
        "/api/attempt",
        json={"code": "783", "answers": {str(n): "A" for n in range(1, 9)}},
        headers=auth_headers(user_id=2, first_name="Aziz"),
    )
    weak = await client.post(
        "/api/attempt",
        json={"code": "783", "answers": {"1": "A"}},
        headers=auth_headers(user_id=3, first_name="Bek"),
    )

    assert strong.status_code == 200
    assert weak.status_code == 200
    assert strong.json()["raw_correct"] == 8
    assert weak.json()["raw_correct"] == 1
    # Within one cohort, the better performance must score higher.
    assert strong.json()["scenarios"][1]["ball"] > weak.json()["scenarios"][1]["ball"]


# --- Several accepted answers per open part ----------------------------------


def payload_with_accepted(code: str, accepted) -> dict:
    return {
        "title": "Test №2",
        "subjects": ["Matematika"],
        "code": code,
        "questions": [
            {"number": 1, "type": "mc", "options": 4, "answer": "A"},
            {"number": 2, "type": "open", "parts": {"a": accepted}},
        ],
    }


@pytest.mark.asyncio
async def test_any_accepted_form_is_marked_correct(client):
    await client.post(
        "/api/test",
        json=payload_with_accepted("900", ["3/4", "0.75", "\\frac{3}{4}"]),
        headers=auth_headers(user_id=1),
    )

    # Three students, three ways of writing the same answer, all correct.
    for index, written in enumerate(["0.75", "3/4", "\\frac{3}{4}"], start=10):
        response = await client.post(
            "/api/attempt",
            json={"code": "900", "answers": {"1": "A", "2a": written}},
            headers=auth_headers(user_id=index),
        )
        assert response.status_code == 200, response.text
        assert response.json()["raw_correct"] == 2, f"{written!r} should have been accepted"


@pytest.mark.asyncio
async def test_a_form_the_author_did_not_list_is_wrong(client):
    await client.post(
        "/api/test",
        json=payload_with_accepted("901", ["ortadi", "oshadi"]),
        headers=auth_headers(user_id=1),
    )
    response = await client.post(
        "/api/attempt",
        json={"code": "901", "answers": {"1": "A", "2a": "kamayadi"}},
        headers=auth_headers(user_id=20),
    )
    assert response.json()["raw_correct"] == 1


@pytest.mark.asyncio
async def test_a_single_string_is_still_accepted_by_the_api(client):
    """A client sending one value rather than a list must still work."""
    response = await client.post(
        "/api/test", json=payload_with_accepted("902", "50/3"), headers=auth_headers(user_id=1)
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_an_open_part_needs_at_least_one_answer(client):
    response = await client.post(
        "/api/test", json=payload_with_accepted("903", []), headers=auth_headers(user_id=1)
    )
    assert response.status_code == 400
    assert "2-savol" in response.json()["error"]

    response = await client.post(
        "/api/test", json=payload_with_accepted("904", ["  ", ""]), headers=auth_headers(user_id=1)
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_blanks_and_duplicates_are_dropped_from_the_key(client):
    await client.post(
        "/api/test",
        json=payload_with_accepted("905", ["3/4", "  ", "3/4", "0.75"]),
        headers=auth_headers(user_id=1),
    )
    from app.store.json_store import get_store

    stored = get_store().get_test_by_code("905")
    assert stored.questions[1]["parts"]["a"] == ["3/4", "0.75"]


@pytest.mark.asyncio
async def test_too_many_accepted_answers_is_refused(client):
    response = await client.post(
        "/api/test",
        json=payload_with_accepted("906", [str(n) for n in range(30)]),
        headers=auth_headers(user_id=1),
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_the_answer_key_never_reaches_the_student(client):
    """Several accepted answers must not leak any more than one did."""
    await client.post(
        "/api/test",
        json=payload_with_accepted("907", ["3/4", "0.75"]),
        headers=auth_headers(user_id=1),
    )
    body = (await client.get("/api/test/907", headers=auth_headers(user_id=30))).json()
    assert "0.75" not in str(body)
    assert "3/4" not in str(body)
    assert body["questions"][1] == {"number": 2, "type": "open", "options": 4, "parts": ["a"]}


# --- Questions 33-35 carry six options (A-F) ----------------------------------


@pytest.mark.asyncio
async def test_questions_33_to_35_get_six_options_even_when_stored_as_four(client):
    """Tests authored before the builder forced six still render A-F.

    In the Milliy sertifikat format 33-35 always have six options; the answer
    sheet upgrades them whatever the stored count says, and leaves every other
    question alone.
    """
    questions = [
        {"number": number, "type": "mc", "options": 4, "answer": "A"}
        for number in (1, 32, 33, 34, 35)
    ]
    await client.post(
        "/api/test",
        json={"title": "Eski test", "subjects": [], "code": "908", "questions": questions},
        headers=auth_headers(user_id=1),
    )

    body = (await client.get("/api/test/908", headers=auth_headers(user_id=40))).json()
    options = {question["number"]: question["options"] for question in body["questions"]}
    assert options == {1: 4, 32: 4, 33: 6, 34: 6, 35: 6}


@pytest.mark.asyncio
async def test_e_and_f_answers_are_accepted_and_graded_on_33_to_35(client):
    """Teacher keys 33-35 on E/F; tapping E/F scores, other letters do not."""
    questions = [
        {"number": number, "type": "mc", "options": 6, "answer": letter}
        for number, letter in ((33, "E"), (34, "F"), (35, "E"))
    ]
    created = await client.post(
        "/api/test",
        json={"title": "EF testi", "subjects": [], "code": "909", "questions": questions},
        headers=auth_headers(user_id=1),
    )
    assert created.status_code == 201, created.text

    # Lower-case input too: grading compares case-insensitively.
    right = await client.post(
        "/api/attempt",
        json={"code": "909", "answers": {"33": "E", "34": "f", "35": "E"}},
        headers=auth_headers(user_id=50),
    )
    assert right.status_code == 200, right.text
    assert right.json()["raw_correct"] == 3

    wrong = await client.post(
        "/api/attempt",
        json={"code": "909", "answers": {"33": "D", "34": "A"}},
        headers=auth_headers(user_id=51),
    )
    assert wrong.json()["raw_correct"] == 0
