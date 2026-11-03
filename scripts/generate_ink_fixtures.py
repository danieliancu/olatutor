"""Generate the shared Digital Ink conformance fixtures.

Geometry and error codes below are written by hand from the spec. Only the hashes are computed, by
the Python core; the separately written JS core must reproduce them. Byte-level encoding vectors in
`encoding_vectors.json` are entirely hand-written and are not produced here.
"""

import json
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.notebooks.ink.encoding import InkError, op_hash
from apps.notebooks.ink.replay import replay_page

OUT = Path(__file__).resolve().parents[1] / "contracts" / "digital_ink" / "v1" / "fixtures"
PAGE: dict[str, Any] = {"page_id": "page-1", "width": 2100, "height": 2970}


class Ops:
    def __init__(self) -> None:
        self.seq = 0

    def base(self, kind: str, payload: dict[str, Any], origin: str = "user") -> dict[str, Any]:
        self.seq += 1
        return {
            "v": 1,
            "op_id": f"op-{self.seq}",
            "type": kind,
            "page_id": "page-1",
            "writer_id": "writer-a",
            "epoch": 1,
            "client_seq": self.seq,
            "origin": origin,
            "client_time_ms": None,
            "payload": payload,
        }

    def add(self, stroke_id: str, xs: list[int], pressure: int | None = None) -> dict[str, Any]:
        return self.base(
            "ADD_STROKE",
            {
                "stroke": {
                    "id": stroke_id,
                    "layer": "student",
                    "style": {"width": 8, "color": "#112233"},
                    "source": {"input": "simulated", "device": None},
                    "capture": {
                        "matrix_micro": [2000000, 0, 0, 2000000, 0, 0],
                        "viewport": [1050, 1485],
                        "dpr_milli": 1000,
                        "rotation_deg": 0,
                    },
                    "points": [[x, 100, 10 * i, pressure] for i, x in enumerate(xs)],
                    "raw_points": None,
                }
            },
        )

    def remove(self, *stroke_ids: str, origin: str = "user", reason: str = "user") -> dict:
        return self.base(
            "REMOVE_STROKE", {"stroke_ids": list(stroke_ids), "reason": reason}, origin
        )

    def erase(self, parent: str, *children: tuple[str, int, int]) -> dict[str, Any]:
        return self.base(
            "ERASE_SEGMENT",
            {
                "items": [
                    {
                        "parent_id": parent,
                        "children": [{"id": c, "start": s, "end": e} for c, s, e in children],
                    }
                ],
                "eraser": {"radius": 20, "path": [[100, 100]]},
            },
        )

    def restore(self, stroke_id: str) -> dict[str, Any]:
        return self.base("RESTORE_STROKE", {"stroke_id": stroke_id})

    def undo(self, target: str) -> dict[str, Any]:
        return self.base("UNDO", {"target_op_id": target})

    def redo(self, target: str) -> dict[str, Any]:
        return self.base("REDO", {"target_op_id": target})


def xs(*values: int) -> list[list[int | None]]:
    return [[x, 100, 10 * i, None] for i, x in enumerate(values)]


def seg(values: list[int], start: int, end: int) -> list[list[int | None]]:
    return [[values[i], 100, 10 * i, None] for i in range(start, end + 1)]


def replay_scenarios() -> list[dict[str, Any]]:
    line = [10, 20, 30, 40, 50, 60]
    scenarios = []

    def scenario(
        name: str,
        build: Any,
        visible: list[tuple[str, list[list[int | None]]]],
        undo: list[str],
        redo: list[str],
        pin_index: int = 0,
    ) -> None:
        scenarios.append(
            {
                "name": name,
                "ops": build(Ops()),
                "pin_index": pin_index,
                "expect": {
                    "visible": [{"id": i, "points": p} for i, p in visible],
                    "undo": undo,
                    "redo": redo,
                },
            }
        )

    scenario("empty_page", lambda o: [], [], [], [])
    scenario("single_stroke", lambda o: [o.add("s1", line)], [("s1", xs(*line))], ["op-1"], [])
    scenario("single_point_stroke", lambda o: [o.add("s1", [5])], [("s1", xs(5))], ["op-1"], [])
    scenario(
        "draw_order_is_journal_order",
        lambda o: [o.add("zz", [1, 2]), o.add("aa", [3, 4])],
        [("zz", xs(1, 2)), ("aa", xs(3, 4))],
        ["op-1", "op-2"],
        [],
    )
    scenario(
        "pressure_preserved",
        lambda o: [o.add("s1", [1, 2], pressure=512)],
        [("s1", [[1, 100, 0, 512], [2, 100, 10, 512]])],
        ["op-1"],
        [],
    )
    scenario(
        "remove_then_undo_restores",
        lambda o: [o.add("s1", [1, 2]), o.remove("s1"), o.undo("op-2")],
        [("s1", xs(1, 2))],
        ["op-1"],
        ["op-2"],
    )
    scenario(
        "erase_middle_splits_in_two",
        lambda o: [o.add("s1", line), o.erase("s1", ("c1", 0, 1), ("c2", 4, 5))],
        [("c1", seg(line, 0, 1)), ("c2", seg(line, 4, 5))],
        ["op-1", "op-2"],
        [],
    )
    scenario(
        "erase_start",
        lambda o: [o.add("s1", line), o.erase("s1", ("c1", 2, 5))],
        [("c1", seg(line, 2, 5))],
        ["op-1", "op-2"],
        [],
    )
    scenario(
        "erase_end",
        lambda o: [o.add("s1", line), o.erase("s1", ("c1", 0, 3))],
        [("c1", seg(line, 0, 3))],
        ["op-1", "op-2"],
        [],
    )
    scenario(
        "erase_everything",
        lambda o: [o.add("s1", line), o.erase("s1")],
        [],
        ["op-1", "op-2"],
        [],
    )
    scenario(
        "erase_segment_only_no_vertex_removed",
        lambda o: [o.add("s1", line), o.erase("s1", ("c1", 0, 2), ("c2", 3, 5))],
        [("c1", seg(line, 0, 2)), ("c2", seg(line, 3, 5))],
        ["op-1", "op-2"],
        [],
    )
    scenario(
        "erase_leaves_single_point_child",
        lambda o: [o.add("s1", line), o.erase("s1", ("c1", 0, 0), ("c2", 2, 5))],
        [("c1", seg(line, 0, 0)), ("c2", seg(line, 2, 5))],
        ["op-1", "op-2"],
        [],
    )
    scenario(
        "re_erase_a_child_indexes_the_root",
        lambda o: [
            o.add("s1", line),
            o.erase("s1", ("c1", 0, 3)),
            o.erase("c1", ("g1", 0, 0), ("g2", 2, 3)),
        ],
        [("g1", seg(line, 0, 0)), ("g2", seg(line, 2, 3))],
        ["op-1", "op-2", "op-3"],
        [],
    )
    scenario(
        "undo_erase_restores_parent_and_hides_children",
        lambda o: [o.add("s1", line), o.erase("s1", ("c1", 0, 1)), o.undo("op-2")],
        [("s1", xs(*line))],
        ["op-1"],
        ["op-2"],
    )
    scenario(
        "redo_erase_reuses_child_ids",
        lambda o: [o.add("s1", line), o.erase("s1", ("c1", 0, 1)), o.undo("op-2"), o.redo("op-2")],
        [("c1", seg(line, 0, 1))],
        ["op-1", "op-2"],
        [],
    )
    scenario(
        "children_keep_the_parents_z_position",
        lambda o: [
            o.add("s1", line),
            o.add("s2", [1, 2]),
            o.erase("s1", ("c1", 0, 1), ("c2", 4, 5)),
        ],
        [("c1", seg(line, 0, 1)), ("c2", seg(line, 4, 5)), ("s2", xs(1, 2))],
        ["op-1", "op-2", "op-3"],
        [],
    )
    scenario(
        "new_content_clears_redo",
        lambda o: [o.add("s1", [1, 2]), o.undo("op-1"), o.add("s2", [3, 4])],
        [("s2", xs(3, 4))],
        ["op-3"],
        [],
    )
    scenario(
        "palm_removal_leaves_history",
        lambda o: [
            o.add("s1", [1, 2]),
            o.add("palm", [3, 4]),
            o.remove("palm", origin="system", reason="palm"),
        ],
        [("s1", xs(1, 2))],
        ["op-1"],
        [],
    )
    scenario(
        "undo_skips_a_palm_removed_stroke",
        lambda o: [
            o.add("palm", [3, 4]),
            o.add("s1", [1, 2]),
            o.remove("palm", origin="system", reason="palm"),
            o.undo("op-2"),
        ],
        [],
        [],
        ["op-2"],
    )
    scenario(
        "restore_a_removed_stroke_after_history_moved_on",
        lambda o: [
            o.add("s1", [1, 2]),
            o.remove("s1"),
            o.undo("op-2"),
            o.remove("s1"),
            o.restore("s1"),
        ],
        [("s1", xs(1, 2))],
        ["op-1", "op-4", "op-5"],
        [],
    )
    scenario(
        "undo_a_restore_hides_the_stroke_again",
        lambda o: [o.add("s1", [1, 2]), o.remove("s1"), o.restore("s1"), o.undo("op-3")],
        [],
        ["op-1", "op-2"],
        ["op-3"],
    )
    scenario(
        "restore_a_parent_after_its_children_were_removed",
        lambda o: [
            o.add("s1", line),
            o.erase("s1", ("c1", 0, 1)),
            o.remove("c1"),
            o.restore("s1"),
        ],
        [("s1", xs(*line))],
        ["op-1", "op-2", "op-3", "op-4"],
        [],
    )
    scenario(
        "undo_above_the_pin_is_allowed",
        lambda o: [o.add("s1", [1, 2]), o.add("s2", [3, 4]), o.undo("op-2")],
        [("s1", xs(1, 2))],
        ["op-1"],
        ["op-2"],
        pin_index=1,
    )
    return scenarios


def rejection_cases() -> list[dict[str, Any]]:
    line = [10, 20, 30, 40]
    cases = []

    def case(name: str, build: Any, at: int, code: str, pin_index: int = 0) -> None:
        cases.append(
            {"name": name, "ops": build(Ops()), "pin_index": pin_index, "at": at, "code": code}
        )

    def mutated(op: dict[str, Any], mutate: Any) -> dict[str, Any]:
        mutate(op)
        return op

    case(
        "float_coordinate",
        lambda o: [mutated(o.add("s1", line), _set_point(0, 0, 1.5))],
        0,
        "FLOAT_NOT_ALLOWED",
    )
    case(
        "integer_above_safe_range",
        lambda o: [mutated(o.add("s1", line), _set_point(0, 0, 2**53))],
        0,
        "INT_OUT_OF_RANGE",
    )
    case(
        "lone_surrogate_in_text",
        lambda o: [mutated(o.add("s1", line), _set_device("bad\ud800"))],
        0,
        "INVALID_STRING",
    )
    case(
        "nul_character_in_text",
        lambda o: [mutated(o.add("s1", line), _set_device("bad\x00"))],
        0,
        "INVALID_STRING",
    )
    case(
        "unknown_version",
        lambda o: [mutated(o.add("s1", line), lambda op: op.update(v=2))],
        0,
        "UNKNOWN_VERSION",
    )
    case(
        "navigation_is_never_journaled",
        lambda o: [mutated(o.undo("x"), lambda op: op.update(type="CHANGE_PAGE"))],
        0,
        "UNSUPPORTED_OP",
    )
    case(
        "missing_pressure_is_not_null",
        lambda o: [mutated(o.add("s1", line), _truncate_point)],
        0,
        "INVALID_SHAPE",
    )
    case(
        "extra_field",
        lambda o: [mutated(o.add("s1", line), lambda op: op.update(extra=1))],
        0,
        "INVALID_SHAPE",
    )
    case(
        "non_ascii_id",
        lambda o: [mutated(o.add("s1", line), lambda op: op.update(op_id="op-é"))],
        0,
        "INVALID_SHAPE",
    )
    case("no_points", lambda o: [o.add("s1", [])], 0, "INVALID_SHAPE")
    case(
        "first_timestamp_not_zero",
        lambda o: [mutated(o.add("s1", line), _set_point(0, 2, 5))],
        0,
        "INVALID_TIMING",
    )
    case(
        "time_goes_backwards",
        lambda o: [mutated(o.add("s1", line), _set_point(2, 2, 5))],
        0,
        "INVALID_TIMING",
    )
    case("point_outside_page", lambda o: [o.add("s1", [3000])], 0, "POINT_OUT_OF_PAGE")
    case(
        "wrong_page",
        lambda o: [mutated(o.add("s1", line), lambda op: op.update(page_id="page-2"))],
        0,
        "WRONG_PAGE",
    )
    case(
        "create_page_in_page_journal",
        lambda o: [
            o.base(
                "CREATE_PAGE",
                {"width": 2100, "height": 2970, "orientation": "portrait", "background": "blank"},
            )
        ],
        0,
        "WRONG_JOURNAL",
    )
    case(
        "duplicate_stroke_id",
        lambda o: [o.add("s1", line), o.add("s1", line)],
        1,
        "DUPLICATE_STROKE",
    )
    case(
        "duplicate_op_id",
        lambda o: [
            o.add("s1", line),
            mutated(o.add("s2", line), lambda op: op.update(op_id="op-1")),
        ],
        1,
        "DUPLICATE_OP",
    )
    case("remove_unknown_stroke", lambda o: [o.remove("nope")], 0, "UNKNOWN_STROKE")
    case(
        "remove_twice",
        lambda o: [o.add("s1", line), o.remove("s1"), o.remove("s1")],
        2,
        "STROKE_NOT_ACTIVE",
    )
    case(
        "overlapping_ranges",
        lambda o: [o.add("s1", line), o.erase("s1", ("c1", 0, 2), ("c2", 2, 3))],
        1,
        "INVALID_RANGE",
    )
    case(
        "descending_ranges",
        lambda o: [o.add("s1", line), o.erase("s1", ("c1", 2, 3), ("c2", 0, 1))],
        1,
        "INVALID_RANGE",
    )
    case(
        "range_beyond_parent",
        lambda o: [o.add("s1", line), o.erase("s1", ("c1", 0, 9))],
        1,
        "INVALID_RANGE",
    )
    case(
        "child_range_outside_a_split_parent",
        lambda o: [o.add("s1", line), o.erase("s1", ("c1", 0, 1)), o.erase("c1", ("g1", 2, 3))],
        2,
        "INVALID_RANGE",
    )
    case(
        "erase_changing_nothing",
        lambda o: [o.add("s1", line), o.erase("s1", ("c1", 0, 3))],
        1,
        "ERASE_NOOP",
    )
    case(
        "child_id_collision",
        lambda o: [o.add("s1", line), o.erase("s1", ("s1", 0, 1))],
        1,
        "DUPLICATE_STROKE",
    )
    case("undo_on_empty_stack", lambda o: [o.undo("op-1")], 0, "NOT_STACK_TOP")
    case(
        "undo_not_stack_top",
        lambda o: [o.add("s1", line), o.add("s2", line), o.undo("op-1")],
        2,
        "NOT_STACK_TOP",
    )
    case("redo_without_undo", lambda o: [o.add("s1", line), o.redo("op-1")], 1, "NOT_STACK_TOP")
    case(
        "undo_at_or_below_the_pin",
        lambda o: [o.add("s1", line), o.undo("op-1")],
        1,
        "PINNED",
        pin_index=1,
    )
    case(
        "palm_removal_below_the_pin",
        lambda o: [o.add("s1", line), o.remove("s1", origin="system", reason="palm")],
        1,
        "PINNED",
        pin_index=1,
    )
    case(
        "palm_removal_of_a_split_stroke",
        lambda o: [
            o.add("s1", line),
            o.erase("s1", ("c1", 0, 1)),
            o.remove("c1", origin="system", reason="palm"),
        ],
        2,
        "SYSTEM_REMOVE_INVALID",
    )
    case(
        "palm_removal_with_a_later_op_on_history",
        lambda o: [
            o.add("s1", line),
            o.remove("s1"),
            o.undo("op-2"),
            o.remove("s1", origin="system", reason="palm"),
        ],
        3,
        "SYSTEM_REMOVE_INVALID",
    )
    case("restore_unknown_stroke", lambda o: [o.restore("nope")], 0, "UNKNOWN_STROKE")
    case(
        "restore_an_active_stroke",
        lambda o: [o.add("s1", line), o.restore("s1")],
        1,
        "STROKE_ALREADY_ACTIVE",
    )
    case(
        "restore_a_parent_with_live_children",
        lambda o: [o.add("s1", line), o.erase("s1", ("c1", 0, 1)), o.restore("s1")],
        2,
        "ACTIVE_DESCENDANTS",
    )
    case(
        "restore_a_palm_contact",
        lambda o: [o.add("p", line), o.remove("p", origin="system", reason="palm"), o.restore("p")],
        2,
        "RESTORE_BLOCKED",
    )
    case(
        "delete_page_in_page_journal",
        lambda o: [o.base("DELETE_PAGE", {})],
        0,
        "WRONG_JOURNAL",
    )
    case(
        "system_cannot_draw",
        lambda o: [mutated(o.add("s1", line), lambda op: op.update(origin="system"))],
        0,
        "INVALID_ORIGIN",
    )
    return cases


def document_cases() -> list[dict[str, Any]]:
    def op(seq: int, kind: str, page: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "v": 1,
            "op_id": f"d-{seq}",
            "type": kind,
            "page_id": page,
            "writer_id": "writer-a",
            "epoch": 1,
            "client_seq": seq,
            "origin": "user",
            "client_time_ms": None,
            "payload": payload,
        }

    a4 = {"width": 2100, "height": 2970, "orientation": "portrait", "background": "blank"}
    wide = {"width": 2970, "height": 2100, "orientation": "landscape", "background": "blank"}
    create_a, create_b = op(1, "CREATE_PAGE", "a", a4), op(2, "CREATE_PAGE", "b", wide)
    return [
        {"name": "two_pages", "ops": [create_a, create_b], "live": ["a", "b"]},
        {
            "name": "deleted_page_is_hidden_not_forgotten",
            "ops": [create_a, create_b, op(3, "DELETE_PAGE", "a", {})],
            "live": ["b"],
        },
        {
            "name": "duplicate_page",
            "ops": [create_a, op(2, "CREATE_PAGE", "a", a4)],
            "at": 1,
            "code": "DUPLICATE_PAGE",
        },
        {
            "name": "recreate_a_deleted_page",
            "ops": [create_a, op(2, "DELETE_PAGE", "a", {}), op(3, "CREATE_PAGE", "a", a4)],
            "at": 2,
            "code": "DUPLICATE_PAGE",
        },
        {
            "name": "orientation_disagrees_with_size",
            "ops": [op(1, "CREATE_PAGE", "a", {**a4, "orientation": "landscape"})],
            "at": 0,
            "code": "INVALID_PAGE",
        },
        {
            "name": "delete_unknown_page",
            "ops": [op(1, "DELETE_PAGE", "a", {})],
            "at": 0,
            "code": "UNKNOWN_PAGE",
        },
        {
            "name": "delete_twice",
            "ops": [create_a, op(2, "DELETE_PAGE", "a", {}), op(3, "DELETE_PAGE", "a", {})],
            "at": 2,
            "code": "PAGE_DELETED",
        },
        {
            "name": "ink_in_the_document_journal",
            "ops": [op(1, "UNDO", "a", {"target_op_id": "x"})],
            "at": 0,
            "code": "WRONG_JOURNAL",
        },
        {
            "name": "delete_page_with_a_payload",
            "ops": [create_a, op(2, "DELETE_PAGE", "a", {"x": 1})],
            "at": 1,
            "code": "INVALID_SHAPE",
        },
    ]


def _set_point(index: int, field: int, value: Any) -> Any:
    def mutate(op: dict[str, Any]) -> None:
        op["payload"]["stroke"]["points"][index][field] = value

    return mutate


def _set_device(value: str) -> Any:
    def mutate(op: dict[str, Any]) -> None:
        op["payload"]["stroke"]["source"]["device"] = value

    return mutate


def _truncate_point(op: dict[str, Any]) -> None:
    op["payload"]["stroke"]["points"][0] = op["payload"]["stroke"]["points"][0][:3]


def random_sequence(seed: int, length: int) -> list[dict[str, Any]]:
    """A valid random journal. Only `random()` is used, whose sequence is stable across versions."""
    rng = random.Random(seed)

    def below(limit: int) -> int:
        return int(rng.random() * limit)

    ops = Ops()
    state = replay_page("page-1", 2100, 2970, [])
    journal: list[dict[str, Any]] = []
    stroke_counter = 0
    while len(journal) < length:
        roll = rng.random()
        active = [s["id"] for s in state.visible()]
        if roll < 0.45 or not active:
            stroke_counter += 1
            op = ops.add(f"s{stroke_counter}", [below(2000) for _ in range(1 + below(12))])
        elif roll < 0.6 and state.undo:
            op = ops.undo(state.undo[-1])
        elif roll < 0.7 and state.redo:
            op = ops.redo(state.redo[-1])
        elif roll < 0.8:
            op = ops.remove(active[below(len(active))])
        else:
            parent_id = active[below(len(active))]
            parent = state.nodes[parent_id]
            size = parent.end - parent.start + 1
            if size < 2:
                op = ops.erase(parent_id)
            else:
                cut = parent.start + below(size - 1)
                stroke_counter += 1
                children = [(f"s{stroke_counter}", parent.start, cut)]
                if cut + 2 <= parent.end:
                    stroke_counter += 1
                    children.append((f"s{stroke_counter}", cut + 2, parent.end))
                op = ops.erase(parent_id, *children)
        state.apply(op)
        journal.append(op)
    return journal


def with_hashes(ops: list[dict[str, Any]], pin_index: int = 0) -> dict[str, Any]:
    state = replay_page(PAGE["page_id"], PAGE["width"], PAGE["height"], ops, pin_index)
    return {
        "op_hashes": [op_hash(op) for op in ops],
        "chain_hash": state.chain_hash,
        "visible_hash": state.visible_hash(),
        "full_hash": state.full_hash(),
    }


def assert_geometry(scenario: dict[str, Any]) -> None:
    state = replay_page(
        PAGE["page_id"], PAGE["width"], PAGE["height"], scenario["ops"], scenario["pin_index"]
    )
    actual = [{"id": s["id"], "points": s["points"]} for s in state.visible()]
    if actual != scenario["expect"]["visible"]:
        raise SystemExit(f"{scenario['name']}: hand-written geometry disagrees with the core")
    if state.undo != scenario["expect"]["undo"] or state.redo != scenario["expect"]["redo"]:
        raise SystemExit(f"{scenario['name']}: hand-written stacks disagree with the core")


def assert_rejected(case: dict[str, Any]) -> None:
    state = replay_page(PAGE["page_id"], PAGE["width"], PAGE["height"], [], case["pin_index"])
    for index, op in enumerate(case["ops"]):
        try:
            state.apply(op)
        except InkError as exc:
            if (index, exc.code) != (case["at"], case["code"]):
                raise SystemExit(f"{case['name']}: got {index} {exc.code}") from exc
            return
    raise SystemExit(f"{case['name']}: nothing was rejected")


def main() -> None:
    scenarios = replay_scenarios()
    for scenario in scenarios:
        assert_geometry(scenario)
        scenario["expect"].update(with_hashes(scenario["ops"], scenario["pin_index"]))
    rejections = rejection_cases()
    for case in rejections:
        assert_rejected(case)
    generated = []
    for seed, length in [(1, 40), (2, 120), (3, 300)]:
        ops = random_sequence(seed, length)
        state = replay_page(PAGE["page_id"], PAGE["width"], PAGE["height"], ops)
        generated.append(
            {
                "name": f"random_seed_{seed}",
                "ops": ops,
                "pin_index": 0,
                "expect": {
                    "visible": [{"id": s["id"], "points": s["points"]} for s in state.visible()],
                    "undo": state.undo,
                    "redo": state.redo,
                    **with_hashes(ops),
                },
            }
        )

    def write(name: str, cases: list[dict[str, Any]], indent: int | None = 1) -> None:
        document = {"page": PAGE, "cases": cases}
        # ensure_ascii keeps lone surrogates representable as \ud800 in the fixture file.
        text = json.dumps(document, indent=indent, ensure_ascii=True)
        (OUT / name).write_text(text + "\n", "utf-8")

    write("replay.json", scenarios)
    write("reject.json", rejections)
    write("random.json", generated, indent=None)
    write("document.json", document_cases())
    print(f"{len(scenarios)} replay, {len(rejections)} reject, {len(generated)} random")


if __name__ == "__main__":
    main()
