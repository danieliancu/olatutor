"""The verification endpoints, through real HTTP and PostgreSQL. All data here is synthetic."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from django.db import DatabaseError, connection, transaction
from django.test import Client, override_settings
from django.utils import timezone

from apps.grading.engine.version import ENGINE_VERSION, RULES_VERSION
from apps.grading.models import ManualTranscription, Verification
from apps.notebooks.ink.encoding import CHAIN_GENESIS
from apps.notebooks.models import Notebook, NotebookPage, PageRevision

pytestmark = pytest.mark.django_db

NB = "nb-grading"
PAGE = "page-1"
URL = f"/api/grading/v1/notebooks/{NB}/pages/{PAGE}/verifications/"
INK = f"/api/ink/v1/notebooks/{NB}"
SIMPLIFY = "ks2.fraction.simplify-2-4"
ORDER = "ks2.order.add-multiply"
ROOT = Path(__file__).resolve().parents[1]
_REPLAY = json.loads((ROOT / "contracts/digital_ink/v1/fixtures/replay.json").read_text("utf-8"))
STROKE_OP = next(
    op for case in _REPLAY["cases"] for op in case["ops"] if op["type"] == "ADD_STROKE"
)


def post(client: Client, url: str, body: Any) -> Any:
    return client.post(url, data=json.dumps(body), content_type="application/json")


def _document_op() -> dict[str, Any]:
    return {
        "v": 1,
        "op_id": "doc-1",
        "type": "CREATE_PAGE",
        "page_id": PAGE,
        "writer_id": "writer-a",
        "epoch": 1,
        "client_seq": 1,
        "origin": "user",
        "client_time_ms": None,
        "payload": {
            "width": 2100,
            "height": 2970,
            "orientation": "portrait",
            "background": "blank",
        },
    }


def _stroke(client_seq: int) -> dict[str, Any]:
    op = copy.deepcopy(STROKE_OP)
    op.update(op_id=f"stroke-{client_seq}", client_seq=client_seq, page_id=PAGE)
    op["payload"]["stroke"]["id"] = f"s{client_seq}"
    return op


def write_ink(client: Client, count: int = 1, start: int = 1) -> None:
    ops = [_stroke(start + index) for index in range(count)]
    response = post(
        client,
        f"{INK}/pages/{PAGE}/ops/",
        {"writer_id": "writer-a", "epoch": 1, "base_seq": start - 1, "ops": ops},
    )
    assert response.status_code == 200, response.content


def pin(client: Client) -> dict[str, Any]:
    state = client.get(f"{INK}/pages/{PAGE}/reconstruction/").json()
    response = post(
        client,
        f"{INK}/pages/{PAGE}/revisions/",
        {
            "seq": state["seq"],
            "chain_hash": state["chain_hash"],
            "visible_hash": state["visible_hash"],
        },
    )
    assert response.status_code == 201, response.content
    return response.json()


@pytest.fixture
def client() -> Client:
    created = Client()
    response = post(
        created,
        f"{INK}/document/ops/",
        {"writer_id": "writer-a", "epoch": 1, "base_seq": 0, "ops": [_document_op()]},
    )
    assert response.status_code == 200, response.content
    return created


@pytest.fixture
def revision(client: Client) -> dict[str, Any]:
    write_ink(client)
    return pin(client)


def body(revision: dict[str, Any], **changes: Any) -> dict[str, Any]:
    return {
        "idempotency_key": "key-0000000000000001",
        "exercise_id": SIMPLIFY,
        "exercise_version": 1,
        "revision": revision["revision"],
        "visible_hash": revision["visible_hash"],
        "steps": ["2/4"],
        "corrects": None,
    } | changes


def test_exercise_list_never_reveals_the_answer(client: Client) -> None:
    response = client.get("/api/grading/v1/exercises/")
    assert response.status_code == 200
    items = response.json()["exercises"]
    assert {item["exercise_id"] for item in items} >= {SIMPLIFY, ORDER}
    for item in items:
        assert set(item) == {
            "exercise_id",
            "exercise_version",
            "title",
            "statement",
            "steps_required",
            "max_score",
        }
    assert "expected" not in response.content.decode()


def test_simplify_flow_through_http(client: Client, revision: dict[str, Any]) -> None:
    response = post(client, URL, body(revision))
    assert response.status_code == 201, response.content
    result = response.json()
    assert result["mathematical_status"] == "CORRECT"
    assert result["task_compliance"] == "NON_COMPLIANT"
    assert result["error_class"] == "FORMAT_REQUIREMENT"
    assert result["score"] == 1
    assert result["max_score"] == 2
    assert result["revision"] == revision["revision"]
    assert result["visible_hash"] == revision["visible_hash"]
    assert result["is_current_page_state"] is True
    assert result["provenance"] == "manual_entry"
    assert result["versions"] == {"semantic": 2, "engine": ENGINE_VERSION, "rules": RULES_VERSION}
    assert result["feedback"]["code"] == "VALUE_RIGHT_NOT_SIMPLIFIED"


def test_everything_is_linked_and_stays_in_separate_layers(
    client: Client, revision: dict[str, Any]
) -> None:
    post(client, URL, body(revision, steps=["2/4 = 1/2"]))
    record = Verification.objects.get()
    assert record.page.notebook_id == NB
    assert record.revision.visible_hash == revision["visible_hash"]
    assert record.exercise_id == SIMPLIFY
    assert record.exercise_version == 1

    transcription = record.transcription
    assert transcription.steps == ["2/4 = 1/2"]
    assert transcription.provenance == "manual_entry"
    assert transcription.semantic_version == 2
    graph = transcription.graph
    assert graph["source"]["visible_hash"] == revision["visible_hash"]
    assert graph["source"]["notebook_id"] == NB
    assert graph["producer"]["kind"] == "manual_transcription"
    assert all(node["stroke_ids"] == [] and node["bbox"] is None for node in graph["nodes"])
    assert "points" not in json.dumps(graph), "no ink in the transcription layer"
    assert record.solution_result["kind"] == "result"
    assert record.solution_result["uncertainty"] == {"recognition": None, "mathematical": None}
    assert record.solution_result["page_revision"]["revision"] == revision["revision"]


def test_response_holds_no_computed_value_that_could_reveal_an_answer(
    client: Client, revision: dict[str, Any]
) -> None:
    response = post(client, URL, body(revision, exercise_id=ORDER, steps=["3 + 4 × 2", "3 + 8"]))
    text = response.content.decode()
    assert response.json()["mathematical_status"] == "INCOMPLETE"
    assert '"11"' not in text
    assert "11/1" not in text, "values are stored as fractions, so look for that form too"
    assert response.json()["steps"][1]["normalized"] == ["3 + 8"], "only what was written"
    assert '"value"' not in text
    assert "expected" not in text


def test_explanation_only_on_request_and_never_the_solution(
    client: Client, revision: dict[str, Any]
) -> None:
    created = post(client, URL, body(revision)).json()
    assert "explanation" not in created["feedback"]
    response = client.get(f"{URL}{created['id']}/explanation/")
    assert response.status_code == 200
    assert response.json()["code"] == "VALUE_RIGHT_NOT_SIMPLIFIED"
    assert "1/2" not in response.json()["explanation"]


@pytest.mark.parametrize(
    ("steps", "status", "compliance"),
    [
        (["half"], "UNSUPPORTED", "NOT_EVALUATED"),
        (["1/2/3"], "UNDETERMINED", "NOT_EVALUATED"),
        (["1" * 600], "UNDETERMINED", "NOT_EVALUATED"),
        (["1"] * 31, "UNDETERMINED", "NOT_EVALUATED"),
    ],
)
def test_no_verdict_cases_are_stored_with_no_score_and_a_review_flag(
    client: Client, revision: dict[str, Any], steps: list[str], status: str, compliance: str
) -> None:
    response = post(client, URL, body(revision, steps=steps))
    assert response.status_code == 201
    result = response.json()
    assert result["mathematical_status"] == status
    assert result["task_compliance"] == compliance
    assert result["score"] is None
    assert result["requires_review"] is True


def test_over_budget_result_is_controlled_and_the_next_request_works(
    client: Client, revision: dict[str, Any]
) -> None:
    over = post(client, URL, body(revision, steps=["1"] * 31)).json()
    assert over["feedback"]["code"] == "RESOURCE_LIMIT_EXCEEDED"
    assert Verification.objects.get(pk=over["id"]).limit_exceeded == "max_steps"
    next_one = post(client, URL, body(revision, idempotency_key="key-0000000000000002"))
    assert next_one.status_code == 201
    assert next_one.json()["score"] == 1


# Idempotency and concurrency.


def test_same_key_and_payload_returns_the_existing_record(
    client: Client, revision: dict[str, Any]
) -> None:
    first = post(client, URL, body(revision))
    second = post(client, URL, body(revision))
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["created_at"] == first.json()["created_at"]
    assert Verification.objects.count() == 1
    assert ManualTranscription.objects.count() == 1


def test_same_key_with_another_payload_is_refused(client: Client, revision: dict[str, Any]) -> None:
    post(client, URL, body(revision))
    response = post(client, URL, body(revision, steps=["1/2"]))
    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_MISMATCH"
    assert Verification.objects.get().transcription.steps == ["2/4"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicates_make_one_record() -> None:
    setup = Client()
    post(
        setup,
        f"{INK}/document/ops/",
        {"writer_id": "writer-a", "epoch": 1, "base_seq": 0, "ops": [_document_op()]},
    )
    write_ink(setup)
    pinned = pin(setup)

    def send(_: int) -> tuple[int, int]:
        try:
            response = post(Client(), URL, body(pinned))
            return response.status_code, response.json()["id"]
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=6) as pool:
        replies = list(pool.map(send, range(6)))
    assert {status for status, _ in replies} <= {200, 201}
    assert [status for status, _ in replies].count(201) == 1
    assert len({record for _, record in replies}) == 1
    assert Verification.objects.count() == 1
    assert ManualTranscription.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_corrections_keep_the_history_a_line() -> None:
    setup = Client()
    post(
        setup,
        f"{INK}/document/ops/",
        {"writer_id": "writer-a", "epoch": 1, "base_seq": 0, "ops": [_document_op()]},
    )
    write_ink(setup)
    pinned = pin(setup)
    original = post(setup, URL, body(pinned)).json()

    def send(index: int) -> tuple[int, str | None]:
        try:
            response = post(
                Client(),
                URL,
                body(
                    pinned,
                    idempotency_key=f"key-correction-000{index}",
                    steps=["1/2"],
                    corrects=original["id"],
                ),
            )
            return response.status_code, response.json().get("code")
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        replies = list(pool.map(send, range(4)))
    assert [status for status, _ in replies].count(201) == 1
    assert {code for status, code in replies if status != 201} == {"ALREADY_CORRECTED"}


# Corrections and history.


def test_a_correction_is_a_new_record_and_keeps_the_original(
    client: Client, revision: dict[str, Any]
) -> None:
    first = post(client, URL, body(revision)).json()
    second = post(
        client,
        URL,
        body(revision, idempotency_key="key-0000000000000002", steps=["1/2"], corrects=first["id"]),
    ).json()
    assert second["corrects"] == first["id"]
    assert second["score"] == 2
    original = Verification.objects.get(pk=first["id"])
    assert original.transcription.steps == ["2/4"]
    assert original.score == 1
    rows = client.get(URL).json()["verifications"]
    assert [row["id"] for row in rows] == [second["id"], first["id"]]
    assert rows[1]["corrected_by"] == second["id"]


@pytest.mark.parametrize(
    ("changes", "status", "code"),
    [
        ({"corrects": 999999}, 404, "UNKNOWN_CORRECTION_TARGET"),
        ({"corrects": "same", "exercise_id": ORDER}, 409, "CORRECTION_CONTEXT_MISMATCH"),
        ({"corrects": "same", "steps": ["2/4"]}, 409, "CORRECTION_UNCHANGED"),
    ],
)
def test_bad_corrections_are_refused(
    client: Client, revision: dict[str, Any], changes: dict[str, Any], status: int, code: str
) -> None:
    first = post(client, URL, body(revision)).json()
    if changes.get("corrects") == "same":
        changes = changes | {"corrects": first["id"]}
    response = post(client, URL, body(revision, idempotency_key="key-0000000000000002") | changes)
    assert response.status_code == status
    assert response.json()["code"] == code


def test_records_are_append_only_in_the_database(client: Client, revision: dict[str, Any]) -> None:
    post(client, URL, body(revision))
    for model in (Verification, ManualTranscription):
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
            model.objects.all().update(created_at="2020-01-01T00:00:00Z")
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
            model.objects.all()._raw_delete(using="default")


def test_old_revision_results_stay_as_history_and_not_as_the_current_verdict(
    client: Client, revision: dict[str, Any]
) -> None:
    created = post(client, URL, body(revision)).json()
    assert created["is_current_page_state"] is True
    write_ink(client, start=2)
    rows = client.get(URL).json()["verifications"]
    assert rows[0]["id"] == created["id"]
    assert rows[0]["is_current_page_state"] is False
    assert rows[0]["revision"] == revision["revision"]


def test_editing_after_the_pin_keeps_the_result_on_the_pinned_revision(
    client: Client, revision: dict[str, Any]
) -> None:
    write_ink(client, start=2)
    response = post(client, URL, body(revision))
    assert response.status_code == 201
    result = response.json()
    assert result["seq"] == revision["seq"]
    assert result["is_current_page_state"] is False


# Validation, references and gates.


def test_the_client_cannot_supply_expected_answers_or_scores(
    client: Client, revision: dict[str, Any]
) -> None:
    for extra in ({"score": 2}, {"expected": "2/4"}, {"max_score": 1}):
        response = post(client, URL, body(revision) | extra)
        assert response.status_code == 400
        assert response.json()["code"] == "INVALID_REQUEST"
    assert Verification.objects.count() == 0


@pytest.mark.parametrize(
    ("changes", "status", "code"),
    [
        ({"idempotency_key": "short"}, 400, "INVALID_REQUEST"),
        ({"idempotency_key": 5}, 400, "INVALID_REQUEST"),
        ({"idempotency_key": "x" * 65}, 400, "INVALID_REQUEST"),
        ({"exercise_id": "../etc"}, 400, "INVALID_REQUEST"),
        ({"exercise_version": True}, 400, "INVALID_REQUEST"),
        ({"exercise_version": 0}, 400, "INVALID_REQUEST"),
        ({"revision": "1"}, 400, "INVALID_REQUEST"),
        ({"revision": 2**40}, 400, "INVALID_REQUEST"),
        ({"visible_hash": "abc"}, 400, "INVALID_REQUEST"),
        ({"corrects": -1}, 400, "INVALID_REQUEST"),
        ({"steps": []}, 400, "INVALID_TRANSCRIPTION"),
        ({"steps": "2/4"}, 400, "INVALID_TRANSCRIPTION"),
        ({"steps": [1]}, 400, "INVALID_TRANSCRIPTION"),
        ({"steps": ["2/4\u0000"]}, 400, "INVALID_TRANSCRIPTION"),
        ({"steps": ["\ud800"]}, 400, "INVALID_TRANSCRIPTION"),
        ({"exercise_id": "no.such.exercise"}, 404, "UNKNOWN_EXERCISE"),
        ({"exercise_version": 2}, 409, "EXERCISE_VERSION_MISMATCH"),
        ({"revision": 99}, 404, "UNKNOWN_REVISION"),
        ({"visible_hash": "0" * 64}, 409, "REVISION_HASH_MISMATCH"),
    ],
)
def test_bad_requests_get_a_controlled_error(
    client: Client, revision: dict[str, Any], changes: dict[str, Any], status: int, code: str
) -> None:
    response = post(client, URL, body(revision) | changes)
    assert response.status_code == status, response.content
    assert response.json()["code"] == code
    assert "Traceback" not in response.content.decode()
    assert Verification.objects.count() == 0


@pytest.mark.parametrize("raw", [b"", b"{", b"[1]", b'{"a":1,"a":2}', b"NaN", b"\xff"])
def test_malformed_bodies_are_refused(client: Client, revision: dict[str, Any], raw: bytes) -> None:
    response = client.post(URL, data=raw, content_type="application/json")
    assert response.status_code == 400
    assert response.json()["code"] in {"INVALID_JSON", "INVALID_REQUEST"}


def test_an_oversized_body_is_refused_and_not_stored(
    client: Client, revision: dict[str, Any]
) -> None:
    response = post(client, URL, body(revision, steps=["1" * 70_000]))
    assert response.status_code == 413
    assert response.json()["code"] == "BODY_TOO_LARGE"
    assert Verification.objects.count() == 0


def test_unknown_page_is_a_json_404(client: Client) -> None:
    other = f"/api/grading/v1/notebooks/{NB}/pages/ghost/verifications/"
    response = post(client, other, {})
    assert response.status_code == 404
    assert response.json()["code"] == "UNKNOWN_PAGE"
    assert client.get(other).json()["code"] == "UNKNOWN_PAGE"


def test_a_revision_of_another_page_is_refused(client: Client, revision: dict[str, Any]) -> None:
    notebook = Notebook.objects.get(pk=NB)
    other = NotebookPage.objects.create(
        notebook=notebook,
        page_id="page-2",
        width=2100,
        height=2970,
        orientation="portrait",
        chain_hash=CHAIN_GENESIS,
    )
    url = f"/api/grading/v1/notebooks/{NB}/pages/{other.page_id}/verifications/"
    response = post(client, url, body(revision))
    assert response.status_code == 404
    assert response.json()["code"] == "UNKNOWN_REVISION"


def test_a_check_on_another_page_is_not_reachable(client: Client, revision: dict[str, Any]) -> None:
    created = post(client, URL, body(revision)).json()
    notebook = Notebook.objects.get(pk=NB)
    NotebookPage.objects.create(
        notebook=notebook,
        page_id="page-2",
        width=2100,
        height=2970,
        orientation="portrait",
        chain_hash=CHAIN_GENESIS,
    )
    base = f"/api/grading/v1/notebooks/{NB}/pages/page-2/verifications/"
    assert client.get(f"{base}{created['id']}/explanation/").status_code == 404
    assert client.get(base).json()["verifications"] == []


def test_a_deleted_page_cannot_be_verified(client: Client, revision: dict[str, Any]) -> None:
    NotebookPage.objects.filter(page_id=PAGE).update(deleted_at=timezone.now())
    response = post(client, URL, body(revision))
    assert response.status_code == 409
    assert response.json()["code"] == "PAGE_DELETED"


def test_an_empty_revision_cannot_be_verified(client: Client) -> None:
    page = NotebookPage.objects.get(notebook_id=NB, page_id=PAGE)
    empty = PageRevision.objects.create(
        page=page,
        revision=1,
        seq=0,
        visible_hash="a" * 64,
        full_hash="b" * 64,
        chain_hash="c" * 64,
    )
    response = post(client, URL, body({"revision": empty.revision, "visible_hash": "a" * 64}))
    assert response.status_code == 409
    assert response.json()["code"] == "EMPTY_REVISION"


def test_csrf_is_enforced(client: Client, revision: dict[str, Any]) -> None:
    strict = Client(enforce_csrf_checks=True)
    response = post(strict, URL, body(revision))
    assert response.status_code == 403
    assert Verification.objects.count() == 0


@pytest.mark.parametrize(
    "gates",
    [
        {"MATH_DEMO_ENABLED": False},
        {"INK_PROTOTYPE_ENABLED": False},
    ],
)
def test_gates_turn_off_every_endpoint(
    client: Client, revision: dict[str, Any], gates: dict[str, bool]
) -> None:
    with override_settings(**gates):
        assert client.get("/api/grading/v1/exercises/").status_code == 404
        assert client.get(URL).status_code == 404
        assert post(client, URL, body(revision)).status_code == 404
        assert client.get(f"{URL}1/explanation/").status_code == 404


def test_the_demo_is_off_in_base_settings() -> None:
    base = ROOT / "config" / "settings" / "base.py"
    assert "MATH_DEMO_ENABLED = False" in base.read_text("utf-8")


def test_notebook_page_labels_the_demo_and_only_when_enabled(client: Client) -> None:
    response = client.get(f"/notebook/{NB}/")
    assert b"manual transcription, not handwriting recognition" in response.content
    assert b"js/grading/verify.js" in response.content
    with override_settings(MATH_DEMO_ENABLED=False):
        response = client.get(f"/notebook/{NB}/")
    assert b"math-demo" not in response.content
    assert b"js/grading/verify.js" not in response.content


def test_method_not_allowed(client: Client) -> None:
    assert client.delete(URL).status_code == 405
    assert client.post("/api/grading/v1/exercises/").status_code == 405
