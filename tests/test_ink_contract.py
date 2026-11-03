"""The Python core against the shared fixtures that the JS core also has to pass."""

import json
from pathlib import Path
from typing import Any

import pytest

from apps.notebooks.ink.encoding import CHAIN_GENESIS, InkError, encode, op_hash, sha256_hex
from apps.notebooks.ink.replay import DocumentState, PageState, replay_page
from apps.notebooks.ink.schema import validate_op
from apps.notebooks.ink.transform import build_matrix, matrix_micro, to_logical

FIXTURES = Path(__file__).resolve().parents[1] / "contracts" / "digital_ink" / "v1" / "fixtures"


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text("utf-8"))


VECTORS = load("encoding_vectors.json")
REPLAY = load("replay.json")
REJECT = load("reject.json")
RANDOM = load("random.json")
TRANSFORMS = load("transforms.json")
DOCUMENT = load("document.json")
PAGE = REPLAY["page"]


def replay(case: dict[str, Any]) -> PageState:
    return replay_page(
        PAGE["page_id"], PAGE["width"], PAGE["height"], case["ops"], case["pin_index"]
    )


@pytest.mark.parametrize("vector", VECTORS["cases"], ids=lambda v: v["name"])
def test_encoding_vectors(vector: dict[str, Any]) -> None:
    assert encode(vector["value"]).hex() == vector["hex"]


def test_chain_genesis_is_derived_from_the_documented_label() -> None:
    assert sha256_hex(VECTORS["chain_genesis_ascii"].encode("ascii")) == CHAIN_GENESIS


@pytest.mark.parametrize("case", REPLAY["cases"] + RANDOM["cases"], ids=lambda case: case["name"])
def test_replay_cases(case: dict[str, Any]) -> None:
    state = replay(case)
    expect = case["expect"]
    assert [{"id": s["id"], "points": s["points"]} for s in state.visible()] == expect["visible"]
    assert state.undo == expect["undo"]
    assert state.redo == expect["redo"]
    assert [op_hash(op) for op in case["ops"]] == expect["op_hashes"]
    assert state.chain_hash == expect["chain_hash"]
    assert state.visible_hash() == expect["visible_hash"]
    assert state.full_hash() == expect["full_hash"]


@pytest.mark.parametrize("case", REJECT["cases"], ids=lambda case: case["name"])
def test_rejection_cases(case: dict[str, Any]) -> None:
    state = replay_page(PAGE["page_id"], PAGE["width"], PAGE["height"], [], case["pin_index"])
    for index, op in enumerate(case["ops"]):
        if index < case["at"]:
            state.apply(op)
        else:
            with pytest.raises(InkError) as caught:
                state.apply(op)
            assert caught.value.code == case["code"]
            return
    pytest.fail("the expected rejection was never reached")


@pytest.mark.parametrize("case", TRANSFORMS["cases"], ids=lambda case: case["name"])
def test_transform_cases(case: dict[str, Any]) -> None:
    params = case["params"]
    matrix = build_matrix(
        viewport=tuple(params["viewport"]),
        dpr=params["dpr"],
        rotation_deg=params["rotation_deg"],
        page_width=params["page_width"],
        scroll=tuple(params["scroll"]),
        zoom=params["zoom"],
    )
    for point in case["points"]:
        x, y = to_logical(matrix, *point["in"])
        assert abs(x - point["out"][0]) <= TRANSFORMS["tolerance"]
        assert abs(y - point["out"][1]) <= TRANSFORMS["tolerance"]
    assert all(isinstance(value, int) for value in matrix_micro(matrix))


def test_rejected_op_leaves_state_unchanged() -> None:
    ops = RANDOM["cases"][1]["ops"]
    state = replay_page(PAGE["page_id"], PAGE["width"], PAGE["height"], ops)
    before = state.full_hash(), state.chain_hash
    bad = {
        **ops[0],
        "op_id": "fresh",
        "client_seq": 9999,
        "type": "UNDO",
        "payload": {"target_op_id": "not-on-the-stack"},
    }
    with pytest.raises(InkError):
        state.apply(bad)
    assert (state.full_hash(), state.chain_hash) == before


def test_partially_invalid_erase_leaves_state_unchanged() -> None:
    case = next(c for c in REPLAY["cases"] if c["name"] == "single_stroke")
    state = replay(case)
    before = state.full_hash()
    bad = {
        **case["ops"][0],
        "op_id": "fresh",
        "type": "ERASE_SEGMENT",
        "payload": {
            "items": [
                {
                    "parent_id": "s1",
                    "children": [
                        {"id": "c1", "start": 0, "end": 1},
                        {"id": "c2", "start": 1, "end": 2},
                    ],
                }
            ],
            "eraser": {"radius": 1, "path": []},
        },
    }
    with pytest.raises(InkError):
        state.apply(bad)
    assert state.full_hash() == before


def test_document_journal_creates_pages_and_rejects_duplicates() -> None:
    create: dict[str, Any] = {
        "v": 1,
        "op_id": "d1",
        "type": "CREATE_PAGE",
        "page_id": "p1",
        "writer_id": "w",
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
    document = DocumentState()
    document.apply(create)
    assert document.pages["p1"]["height"] == 2970
    with pytest.raises(InkError) as duplicate:
        document.apply({**create, "op_id": "d2"})
    assert duplicate.value.code == "DUPLICATE_PAGE"
    with pytest.raises(InkError) as wrong:
        document.apply(
            {
                **create,
                "op_id": "d3",
                "page_id": "p2",
                "payload": {**create["payload"], "orientation": "landscape"},
            }
        )
    assert wrong.value.code == "INVALID_PAGE"


def test_every_valid_fixture_op_satisfies_the_schema() -> None:
    for case in REPLAY["cases"]:
        for op in case["ops"]:
            validate_op(op)


@pytest.mark.parametrize("case", DOCUMENT["cases"], ids=lambda case: case["name"])
def test_document_journal_cases(case: dict[str, Any]) -> None:
    document = DocumentState()
    for index, op in enumerate(case["ops"]):
        if "at" in case and index == case["at"]:
            with pytest.raises(InkError) as caught:
                document.apply(op)
            assert caught.value.code == case["code"]
            return
        document.apply(op)
    assert "at" not in case, "the expected rejection was never reached"
    assert [page for page in document.pages if page not in document.deleted] == case["live"]
