"""Journal persistence, sync rules and server-side reconstruction, through the real HTTP layer."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from django.db import DatabaseError, connection, transaction
from django.test import Client, override_settings

from apps.notebooks import services
from apps.notebooks.ink.replay import replay_page
from apps.notebooks.models import (
    InkOperation,
    InkSnapshot,
    NotebookPage,
    PageRevision,
    QuarantinedBatch,
)

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).resolve().parents[1] / "contracts" / "digital_ink" / "v1" / "fixtures"
REPLAY = json.loads((FIXTURES / "replay.json").read_text("utf-8"))
RANDOM = json.loads((FIXTURES / "random.json").read_text("utf-8"))
NB = "nb-1"
API = f"/api/ink/v1/notebooks/{NB}"
PAGE_API = f"{API}/pages/page-1"


def scenario(name: str) -> dict[str, Any]:
    return next(case for case in REPLAY["cases"] if case["name"] == name)


def post(client: Client, url: str, body: Any) -> Any:
    return client.post(url, data=json.dumps(body), content_type="application/json")


def batch(ops: list[dict[str, Any]], base_seq: int = 0, writer: str = "writer-a", epoch: int = 1):
    return {"writer_id": writer, "epoch": epoch, "base_seq": base_seq, "ops": ops}


def create_page(client: Client) -> None:
    op = {
        "v": 1,
        "op_id": "doc-1",
        "type": "CREATE_PAGE",
        "page_id": "page-1",
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
    response = post(client, f"{API}/document/ops/", batch([op]))
    assert response.status_code == 200, response.content


@pytest.fixture
def client() -> Client:
    created = Client()
    create_page(created)
    return created


def test_document_journal_creates_a_page_and_is_idempotent(client: Client) -> None:
    page = NotebookPage.objects.get(notebook_id=NB, page_id="page-1")
    assert (page.width, page.height, page.orientation) == (2100, 2970, "portrait")
    document = client.get(f"{API}/").json()["document"]
    assert document["head_seq"] == 1
    assert document["ops"][0]["op_id"] == "doc-1"


@pytest.mark.parametrize(
    "case", REPLAY["cases"] + RANDOM["cases"][:2], ids=lambda case: case["name"]
)
def test_upload_then_reconstruction_matches_the_shared_fixture(
    client: Client, case: dict[str, Any]
) -> None:
    if case["pin_index"] or not case["ops"]:
        pytest.skip("pins are covered by the revision tests; empty pages have nothing to upload")
    ops, seq = case["ops"], 0
    for start in range(0, len(ops), 50):
        part = ops[start : start + 50]
        response = post(client, f"{PAGE_API}/ops/", batch(part, base_seq=seq))
        assert response.status_code == 200, response.content
        seq = response.json()["head_seq"]

    result = client.get(f"{PAGE_API}/reconstruction/").json()
    expect = case["expect"]
    assert [{"id": s["id"], "points": s["points"]} for s in result["strokes"]] == expect["visible"]
    assert result["visible_hash"] == expect["visible_hash"]
    assert result["full_hash"] == expect["full_hash"]
    assert result["chain_hash"] == expect["chain_hash"]


def test_retry_after_a_lost_ack_returns_original_sequence(client: Client) -> None:
    ops = scenario("draw_order_is_journal_order")["ops"]
    first = post(client, f"{PAGE_API}/ops/", batch(ops)).json()
    second = post(client, f"{PAGE_API}/ops/", batch(ops)).json()
    assert first == second
    assert InkOperation.objects.filter(journal="page-1").count() == 2


def test_partial_retry_with_a_new_operation_appends_only_the_new_one(client: Client) -> None:
    ops = scenario("draw_order_is_journal_order")["ops"]
    post(client, f"{PAGE_API}/ops/", batch(ops[:1]))
    response = post(client, f"{PAGE_API}/ops/", batch(ops, base_seq=0))
    assert response.status_code == 200, response.content
    assert [ack["seq"] for ack in response.json()["acks"]] == [1, 2]
    assert InkOperation.objects.filter(journal="page-1").count() == 2


def test_same_key_with_different_payload_is_rejected_and_quarantined(client: Client) -> None:
    ops = scenario("single_stroke")["ops"]
    post(client, f"{PAGE_API}/ops/", batch(ops))
    forged = copy.deepcopy(ops)
    forged[0]["payload"]["stroke"]["points"][0][0] = 999
    response = post(client, f"{PAGE_API}/ops/", batch(forged, base_seq=1))
    assert response.status_code == 409
    assert response.json()["code"] == "IDEMPOTENCY_MISMATCH"
    assert QuarantinedBatch.objects.filter(code="IDEMPOTENCY_MISMATCH").count() == 1
    assert InkOperation.objects.filter(journal="page-1").count() == 1


def test_second_writer_conflict_keeps_its_work_without_merging(client: Client) -> None:
    ops = scenario("draw_order_is_journal_order")["ops"]
    post(client, f"{PAGE_API}/ops/", batch(ops[:1]))
    other = copy.deepcopy(ops[1])
    other.update(writer_id="writer-b", client_seq=1, op_id="other-op")
    response = post(client, f"{PAGE_API}/ops/", batch([other], base_seq=0, writer="writer-b"))
    assert response.status_code == 409
    assert response.json()["code"] == "BASE_CONFLICT"
    assert response.json()["head_seq"] == 1
    saved = QuarantinedBatch.objects.get(code="BASE_CONFLICT")
    assert saved.body["ops"][0]["op_id"] == "other-op"
    assert InkOperation.objects.filter(journal="page-1").count() == 1


def test_gap_in_client_sequence_is_refused_with_the_expected_position(client: Client) -> None:
    ops = copy.deepcopy(scenario("single_stroke")["ops"])
    ops[0]["client_seq"] = 5
    response = post(client, f"{PAGE_API}/ops/", batch(ops))
    assert response.status_code == 409
    assert response.json()["code"] == "SEQUENCE_GAP"
    assert response.json()["expected_client_seq"] == 1


def test_a_batch_is_all_or_nothing(client: Client) -> None:
    ops = scenario("draw_order_is_journal_order")["ops"]
    bad = copy.deepcopy(ops)
    bad[1]["payload"]["stroke"]["id"] = bad[0]["payload"]["stroke"]["id"]
    response = post(client, f"{PAGE_API}/ops/", batch(bad))
    assert response.status_code == 422
    assert response.json()["code"] == "DUPLICATE_STROKE"
    assert InkOperation.objects.filter(journal="page-1").count() == 0
    assert NotebookPage.objects.get(page_id="page-1").head_seq == 0


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b"not json", "INVALID_JSON"),
        (b'{"a": NaN}', "INVALID_JSON"),
        (b'{"writer_id": "a", "writer_id": "b"}', "INVALID_JSON"),
        (b"[" * 100000, "INVALID_JSON"),
        (b'{"writer_id": "w", "epoch": 1, "base_seq": 0, "ops": []}', "INVALID_BATCH"),
        (b'{"writer_id": "w", "epoch": 1, "base_seq": -1, "ops": [{}]}', "INVALID_BATCH"),
    ],
)
def test_malformed_requests_fail_safely(client: Client, raw: bytes, code: str) -> None:
    response = client.post(f"{PAGE_API}/ops/", data=raw, content_type="application/json")
    assert response.status_code == 400
    assert response.json()["code"] == code


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda op: op["payload"]["stroke"]["points"][0].__setitem__(0, 1.5), "FLOAT_NOT_ALLOWED"),
        (lambda op: op["payload"]["stroke"]["points"][0].__setitem__(0, 2**60), "INT_OUT_OF_RANGE"),
        (
            lambda op: op["payload"]["stroke"]["source"].__setitem__("device", "x\ud800"),
            "INVALID_STRING",
        ),
        (lambda op: op.__setitem__("v", 2), "UNKNOWN_VERSION"),
        (lambda op: op.__setitem__("extra", True), "INVALID_SHAPE"),
    ],
)
def test_contract_violations_are_refused_and_stored_safely(
    client: Client, mutate: Any, code: str
) -> None:
    ops = copy.deepcopy(scenario("single_stroke")["ops"])
    mutate(ops[0])
    response = post(client, f"{PAGE_API}/ops/", batch(ops))
    assert response.status_code == 422
    assert response.json()["code"] == code
    assert QuarantinedBatch.objects.filter(code=code).exists()


def test_unknown_page_returns_404(client: Client) -> None:
    ops = scenario("single_stroke")["ops"]
    response = post(client, f"{API}/pages/nope/ops/", batch(ops))
    assert response.status_code == 404


def test_csrf_is_enforced() -> None:
    strict = Client(enforce_csrf_checks=True)
    response = post(strict, f"{API}/document/ops/", batch([]))
    assert response.status_code == 403


def test_prototype_is_unreachable_when_disabled(client: Client) -> None:
    with override_settings(INK_PROTOTYPE_ENABLED=False):
        assert client.get("/notebook/").status_code == 404
        assert client.get(f"{PAGE_API}/reconstruction/").status_code == 404
        assert post(client, f"{PAGE_API}/ops/", batch([])).status_code == 404


def test_journal_rows_cannot_be_updated(client: Client) -> None:
    post(client, f"{PAGE_API}/ops/", batch(scenario("single_stroke")["ops"]))
    row = InkOperation.objects.get(journal="page-1")
    row.payload_hash = "tampered"
    with pytest.raises(DatabaseError), transaction.atomic():
        row.save()


def test_journal_rows_can_still_be_deleted_for_erasure(client: Client) -> None:
    post(client, f"{PAGE_API}/ops/", batch(scenario("single_stroke")["ops"]))
    assert InkOperation.objects.filter(journal="page-1").delete()[0] == 1


def upload(client: Client, ops: list[dict[str, Any]], base_seq: int = 0) -> Any:
    response = post(client, f"{PAGE_API}/ops/", batch(ops, base_seq=base_seq))
    assert response.status_code == 200, response.content
    return response.json()


def test_revision_pins_verified_hashes_and_blocks_undo_below_it(client: Client) -> None:
    ops = scenario("draw_order_is_journal_order")["ops"]
    upload(client, ops)
    state = replay_page("page-1", 2100, 2970, ops)
    pin = {"seq": 2, "chain_hash": state.chain_hash, "visible_hash": state.visible_hash()}

    created = post(client, f"{PAGE_API}/revisions/", pin)
    assert created.status_code == 201, created.content
    assert created.json()["revision"] == 1
    assert post(client, f"{PAGE_API}/revisions/", pin).json()["revision"] == 1

    undo = {
        **ops[1],
        "op_id": "undo-1",
        "type": "UNDO",
        "client_seq": 3,
        "payload": {"target_op_id": ops[1]["op_id"]},
    }
    response = post(client, f"{PAGE_API}/ops/", batch([undo], base_seq=2))
    assert response.status_code == 422
    assert response.json()["code"] == "PINNED"


def test_new_ink_after_a_revision_leaves_the_pinned_evidence_unchanged(client: Client) -> None:
    ops = scenario("draw_order_is_journal_order")["ops"]
    upload(client, ops[:1])
    state = replay_page("page-1", 2100, 2970, ops[:1])
    pinned = state.visible_hash()
    post(
        client,
        f"{PAGE_API}/revisions/",
        {"seq": 1, "chain_hash": state.chain_hash, "visible_hash": pinned},
    )

    upload(client, ops[1:], base_seq=1)

    at_pin = client.get(f"{PAGE_API}/reconstruction/?seq=1").json()
    assert at_pin["visible_hash"] == pinned
    assert client.get(f"{PAGE_API}/reconstruction/").json()["visible_hash"] != pinned


@pytest.mark.parametrize("wrong", ["chain_hash", "visible_hash"])
def test_revision_with_mismatched_hash_is_refused(client: Client, wrong: str) -> None:
    ops = scenario("single_stroke")["ops"]
    upload(client, ops)
    state = replay_page("page-1", 2100, 2970, ops)
    pin = {"seq": 1, "chain_hash": state.chain_hash, "visible_hash": state.visible_hash()}
    pin[wrong] = "0" * 64
    response = post(client, f"{PAGE_API}/revisions/", pin)
    assert response.status_code == 409
    assert response.json()["code"] == "HASH_MISMATCH"
    assert not PageRevision.objects.exists()


def test_revision_ahead_of_the_server_is_refused(client: Client) -> None:
    response = post(
        client, f"{PAGE_API}/revisions/", {"seq": 9, "chain_hash": "a", "visible_hash": "b"}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "REVISION_NOT_SYNCED"


def test_snapshots_are_written_and_equal_replay_from_zero(client: Client) -> None:
    ops = RANDOM["cases"][1]["ops"]
    seq = 0
    for start in range(0, len(ops), 30):
        seq = upload(client, ops[start : start + 30], base_seq=seq)["head_seq"]
    page = NotebookPage.objects.get(page_id="page-1")
    assert InkSnapshot.objects.filter(page=page).exists()
    assert services.load_page_state(page).full_hash() == services.replay_at(page).full_hash()


def test_a_corrupt_snapshot_is_detected_and_ignored(client: Client) -> None:
    ops = RANDOM["cases"][1]["ops"]
    seq = 0
    for start in range(0, len(ops), 60):
        seq = upload(client, ops[start : start + 60], base_seq=seq)["head_seq"]
    page = NotebookPage.objects.get(page_id="page-1")
    snapshot = page.snapshots.order_by("-seq").first()
    assert snapshot is not None
    snapshot.state["chain_hash"] = "0" * 64
    snapshot.save()
    state = services.load_page_state(page)
    assert state.chain_hash == page.chain_hash
    assert state.full_hash() == services.replay_at(page).full_hash()


def test_render_returns_a_png_with_ink(client: Client) -> None:
    upload(client, scenario("single_stroke")["ops"])
    response = client.get(f"{PAGE_API}/render.png")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    import io

    from PIL import Image

    image = Image.open(io.BytesIO(response.content)).convert("L")
    assert image.size == (840, 1188)
    assert min(image.tobytes()) < 128


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_batches_create_one_copy() -> None:
    create_page(Client())
    ops = scenario("draw_order_is_journal_order")["ops"]

    def send(_: int) -> int:
        try:
            return post(Client(), f"{PAGE_API}/ops/", batch(ops)).status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(send, range(6)))
    assert set(statuses) == {200}
    assert InkOperation.objects.filter(journal="page-1").count() == 2
    assert NotebookPage.objects.get(page_id="page-1").head_seq == 2


def doc_op(
    seq: int, kind: str, page: str, payload: dict[str, Any], writer: str = "writer-a"
) -> Any:
    return {
        "v": 1,
        "op_id": f"{writer}-doc-{seq}",
        "type": kind,
        "page_id": page,
        "writer_id": writer,
        "epoch": 1,
        "client_seq": seq,
        "origin": "user",
        "client_time_ms": None,
        "payload": payload,
    }


A4 = {"width": 2100, "height": 2970, "orientation": "portrait", "background": "blank"}


def test_two_writers_can_add_pages_without_a_conflict(client: Client) -> None:
    first = post(
        client,
        f"{API}/document/ops/",
        batch([doc_op(1, "CREATE_PAGE", "b1", A4, "writer-b")], writer="writer-b"),
    )
    second = post(
        client,
        f"{API}/document/ops/",
        batch([doc_op(1, "CREATE_PAGE", "c1", A4, "writer-c")], writer="writer-c"),
    )
    assert (first.status_code, second.status_code) == (200, 200), second.content
    assert NotebookPage.objects.filter(notebook_id=NB).count() == 3


def test_notebook_state_returns_all_journals_at_once(client: Client) -> None:
    upload(client, scenario("single_stroke")["ops"])
    state = client.get(f"{API}/").json()
    assert state["document"]["head_seq"] == 1
    assert [page["page_id"] for page in state["pages"]] == ["page-1"]
    assert state["pages"][0]["head_seq"] == 1
    assert state["pages"][0]["pin_seq"] == 0
    assert state["pages"][0]["deleted"] is False


def test_unknown_notebook_is_empty_not_an_error(db: Any) -> None:
    state = Client().get("/api/ink/v1/notebooks/never-seen/").json()
    assert state == {"document": {"head_seq": 0, "ops": []}, "pages": []}


def test_a_deleted_page_refuses_ink_but_keeps_its_evidence(client: Client) -> None:
    ops = scenario("draw_order_is_journal_order")["ops"]
    upload(client, ops[:1])
    deleted = post(
        client, f"{API}/document/ops/", batch([doc_op(2, "DELETE_PAGE", "page-1", {})], base_seq=1)
    )
    assert deleted.status_code == 200, deleted.content

    response = post(client, f"{PAGE_API}/ops/", batch(ops[1:], base_seq=1))
    assert response.status_code == 409
    assert response.json()["code"] == "PAGE_DELETED"
    assert QuarantinedBatch.objects.filter(code="PAGE_DELETED").exists()

    assert len(client.get(f"{PAGE_API}/reconstruction/").json()["strokes"]) == 1
    assert client.get(f"{API}/").json()["pages"][0]["deleted"] is True


def test_deleting_a_page_twice_is_refused(client: Client) -> None:
    post(client, f"{API}/document/ops/", batch([doc_op(2, "DELETE_PAGE", "page-1", {})]))
    response = post(client, f"{API}/document/ops/", batch([doc_op(3, "DELETE_PAGE", "page-1", {})]))
    assert response.status_code == 422
    assert response.json()["code"] == "PAGE_DELETED"


def test_service_worker_is_served_from_the_root(db: Any) -> None:
    response = Client().get("/sw.js")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/javascript"
    assert response["Cache-Control"] == "no-cache"
    with override_settings(INK_PROTOTYPE_ENABLED=False):
        assert Client().get("/sw.js").status_code == 404
