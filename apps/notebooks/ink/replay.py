"""Deterministic fold of a page journal into page state (spec sections 6-8)."""

import copy
from dataclasses import dataclass, field
from typing import Any

from .encoding import CHAIN_GENESIS, InkError, chain_next, encode, op_hash, sha256_hex
from .schema import validate_op


@dataclass
class Node:
    """One visible-or-hidden piece of ink: an inclusive point range of an immutable root stroke."""

    id: str
    root_id: str
    parent_id: str | None
    start: int
    end: int
    z: int
    active: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "root_id": self.root_id,
            "parent_id": self.parent_id,
            "start": self.start,
            "end": self.end,
            "z": self.z,
            "active": self.active,
        }


@dataclass
class PageState:
    page_id: str
    width: int
    height: int
    pin_index: int = 0
    roots: dict[str, dict[str, Any]] = field(default_factory=dict)
    nodes: dict[str, Node] = field(default_factory=dict)
    effects: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    undo: list[str] = field(default_factory=list)
    redo: list[str] = field(default_factory=list)
    op_index: dict[str, int] = field(default_factory=dict)
    next_z: int = 0
    chain_hash: str = CHAIN_GENESIS
    palm_removed: list[str] = field(default_factory=list)

    @property
    def op_count(self) -> int:
        return len(self.op_index)

    def apply(self, op: dict[str, Any]) -> None:
        validate_op(op)
        if op["type"] in ("CREATE_PAGE", "DELETE_PAGE"):
            raise InkError("WRONG_JOURNAL", "page lifecycle belongs to the document journal")
        if op["page_id"] != self.page_id:
            raise InkError("WRONG_PAGE")
        if op["op_id"] in self.op_index:
            raise InkError("DUPLICATE_OP")

        handler = {
            "ADD_STROKE": self._add_stroke,
            "REMOVE_STROKE": self._remove_stroke,
            "ERASE_SEGMENT": self._erase_segment,
            "RESTORE_STROKE": self._restore_stroke,
            "UNDO": self._undo,
            "REDO": self._redo,
        }[op["type"]]
        handler(op)
        self.op_index[op["op_id"]] = self.op_count
        self.chain_hash = chain_next(self.chain_hash, op_hash(op))

    def _require_user(self, op: dict[str, Any]) -> None:
        if op["origin"] != "user":
            raise InkError("INVALID_ORIGIN")

    def _push_content(self, op_id: str, activate: list[str], deactivate: list[str]) -> None:
        self.effects[op_id] = {"activate": activate, "deactivate": deactivate}
        self.undo.append(op_id)
        self.redo.clear()

    def _add_stroke(self, op: dict[str, Any]) -> None:
        self._require_user(op)
        stroke = op["payload"]["stroke"]
        stroke_id = stroke["id"]
        if stroke_id in self.nodes:
            raise InkError("DUPLICATE_STROKE")
        points = stroke["points"]
        previous_t = 0
        for index, (x, y, t, _pressure) in enumerate(points):
            if x > self.width or y > self.height:
                raise InkError("POINT_OUT_OF_PAGE")
            if (index == 0 and t != 0) or t < previous_t:
                raise InkError("INVALID_TIMING")
            previous_t = t
        self.roots[stroke_id] = stroke
        self.nodes[stroke_id] = Node(
            stroke_id, stroke_id, None, 0, len(points) - 1, self.next_z, True
        )
        self.next_z += 1
        self._push_content(op["op_id"], [stroke_id], [])

    def _remove_stroke(self, op: dict[str, Any]) -> None:
        payload = op["payload"]
        stroke_ids = payload["stroke_ids"]
        if len(set(stroke_ids)) != len(stroke_ids):
            raise InkError("DUPLICATE_STROKE")
        for stroke_id in stroke_ids:
            node = self.nodes.get(stroke_id)
            if node is None:
                raise InkError("UNKNOWN_STROKE")
            if not node.active:
                raise InkError("STROKE_NOT_ACTIVE")

        if op["origin"] == "system":
            self._remove_as_palm(op)
            return
        if payload["reason"] != "user":
            raise InkError("INVALID_ORIGIN")
        for stroke_id in stroke_ids:
            self.nodes[stroke_id].active = False
        self._push_content(op["op_id"], [], list(stroke_ids))

    def _remove_as_palm(self, op: dict[str, Any]) -> None:
        """A late palm reclassification stays out of history and never touches evidence."""
        stroke_ids = op["payload"]["stroke_ids"]
        if op["payload"]["reason"] != "palm" or len(stroke_ids) != 1:
            raise InkError("SYSTEM_REMOVE_INVALID")
        stroke_id = stroke_ids[0]
        if stroke_id not in self.roots:
            raise InkError("SYSTEM_REMOVE_INVALID")
        add_op_id = next(
            (op_id for op_id in self.undo if self.effects[op_id]["activate"] == [stroke_id]), None
        )
        if add_op_id is None:
            raise InkError("SYSTEM_REMOVE_INVALID")
        if self.op_index[add_op_id] < self.pin_index:
            raise InkError("PINNED")
        for other in self.undo + self.redo:
            effect = self.effects[other]
            if other != add_op_id and stroke_id in effect["activate"] + effect["deactivate"]:
                # Undoing or redoing that other operation could bring the palm stroke back.
                raise InkError("SYSTEM_REMOVE_INVALID")
        self.nodes[stroke_id].active = False
        self.undo.remove(add_op_id)
        self.palm_removed.append(stroke_id)
        self.effects[op["op_id"]] = {"activate": [], "deactivate": [stroke_id]}

    def _erase_segment(self, op: dict[str, Any]) -> None:
        self._require_user(op)
        activate: list[str] = []
        deactivate: list[str] = []
        created: list[Node] = []
        new_ids: set[str] = set()
        parents: set[str] = set()
        for item in op["payload"]["items"]:
            parent_id = item["parent_id"]
            parent = self.nodes.get(parent_id)
            if parent is None:
                raise InkError("UNKNOWN_STROKE")
            if not parent.active:
                raise InkError("STROKE_NOT_ACTIVE")
            if parent_id in parents:
                raise InkError("DUPLICATE_STROKE")
            parents.add(parent_id)

            cursor = parent.start
            children = item["children"]
            for child in children:
                if child["start"] < cursor or child["end"] < child["start"]:
                    raise InkError("INVALID_RANGE")
                if child["end"] > parent.end:
                    raise InkError("INVALID_RANGE")
                cursor = child["end"] + 1
                if child["id"] in self.nodes or child["id"] in new_ids:
                    raise InkError("DUPLICATE_STROKE")
                new_ids.add(child["id"])
                created.append(
                    Node(
                        child["id"],
                        parent.root_id,
                        parent_id,
                        child["start"],
                        child["end"],
                        parent.z,
                        True,
                    )
                )
                activate.append(child["id"])
            if len(children) == 1 and (children[0]["start"], children[0]["end"]) == (
                parent.start,
                parent.end,
            ):
                raise InkError("ERASE_NOOP")
            deactivate.append(parent_id)

        for node in created:
            self.nodes[node.id] = node
        for parent_id in deactivate:
            self.nodes[parent_id].active = False
        self._push_content(op["op_id"], activate, deactivate)

    def _restore_stroke(self, op: dict[str, Any]) -> None:
        self._require_user(op)
        stroke_id = op["payload"]["stroke_id"]
        node = self.nodes.get(stroke_id)
        if node is None:
            raise InkError("UNKNOWN_STROKE")
        if node.active:
            raise InkError("STROKE_ALREADY_ACTIVE")
        if stroke_id in self.palm_removed:
            raise InkError("RESTORE_BLOCKED", "a palm contact is not student work")
        if self._has_active_descendant(stroke_id):
            raise InkError("ACTIVE_DESCENDANTS")
        node.active = True
        self._push_content(op["op_id"], [stroke_id], [])

    def _has_active_descendant(self, stroke_id: str) -> bool:
        for node in self.nodes.values():
            ancestor = node.parent_id
            while ancestor is not None:
                if ancestor == stroke_id and node.active:
                    return True
                ancestor = self.nodes[ancestor].parent_id
        return False

    def _undo(self, op: dict[str, Any]) -> None:
        self._require_user(op)
        target = op["payload"]["target_op_id"]
        if not self.undo or self.undo[-1] != target:
            raise InkError("NOT_STACK_TOP")
        if self.op_index[target] < self.pin_index:
            raise InkError("PINNED")
        effect = self.effects[target]
        for stroke_id in effect["activate"]:
            self.nodes[stroke_id].active = False
        for stroke_id in effect["deactivate"]:
            self.nodes[stroke_id].active = True
        self.redo.append(self.undo.pop())

    def _redo(self, op: dict[str, Any]) -> None:
        self._require_user(op)
        target = op["payload"]["target_op_id"]
        if not self.redo or self.redo[-1] != target:
            raise InkError("NOT_STACK_TOP")
        effect = self.effects[target]
        for stroke_id in effect["deactivate"]:
            self.nodes[stroke_id].active = False
        for stroke_id in effect["activate"]:
            self.nodes[stroke_id].active = True
        self.undo.append(self.redo.pop())

    def visible(self) -> list[dict[str, Any]]:
        active = [node for node in self.nodes.values() if node.active]
        active.sort(key=lambda node: (node.z, node.start, node.id))
        strokes = []
        for node in active:
            root = self.roots[node.root_id]
            strokes.append(
                {
                    "id": node.id,
                    "z": node.z,
                    "width": root["style"]["width"],
                    "color": root["style"]["color"],
                    "points": root["points"][node.start : node.end + 1],
                }
            )
        return strokes

    def visible_hash(self) -> str:
        return sha256_hex(
            encode({"width": self.width, "height": self.height, "strokes": self.visible()})
        )

    def full_hash(self) -> str:
        nodes = []
        for node_id in sorted(self.nodes):
            node = self.nodes[node_id]
            digest = sha256_hex(encode(self.roots[node_id])) if node_id in self.roots else None
            nodes.append({**node.as_dict(), "root_digest": digest})
        return sha256_hex(
            encode(
                {
                    "page_id": self.page_id,
                    "width": self.width,
                    "height": self.height,
                    "nodes": nodes,
                    "undo": self.undo,
                    "redo": self.redo,
                    "palm_removed": sorted(self.palm_removed),
                }
            )
        )

    def to_snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(
            {
                "page_id": self.page_id,
                "width": self.width,
                "height": self.height,
                "roots": self.roots,
                "nodes": [self.nodes[key].as_dict() for key in sorted(self.nodes)],
                "effects": self.effects,
                "undo": self.undo,
                "redo": self.redo,
                "op_index": self.op_index,
                "next_z": self.next_z,
                "chain_hash": self.chain_hash,
                "palm_removed": self.palm_removed,
            }
        )

    @classmethod
    def from_snapshot(cls, data: dict[str, Any], pin_index: int = 0) -> "PageState":
        data = copy.deepcopy(data)
        return cls(
            page_id=data["page_id"],
            width=data["width"],
            height=data["height"],
            pin_index=pin_index,
            roots=data["roots"],
            nodes={item["id"]: Node(**item) for item in data["nodes"]},
            effects=data["effects"],
            undo=data["undo"],
            redo=data["redo"],
            op_index=data["op_index"],
            next_z=data["next_z"],
            chain_hash=data["chain_hash"],
            palm_removed=data["palm_removed"],
        )


@dataclass
class DocumentState:
    """The notebook-level journal: which pages exist. Separate from any page's ink."""

    pages: dict[str, dict[str, Any]] = field(default_factory=dict)
    deleted: set[str] = field(default_factory=set)
    op_ids: set[str] = field(default_factory=set)
    chain_hash: str = CHAIN_GENESIS

    def apply(self, op: dict[str, Any]) -> None:
        validate_op(op)
        if op["type"] not in ("CREATE_PAGE", "DELETE_PAGE"):
            raise InkError("WRONG_JOURNAL", "only page lifecycle operations are allowed here")
        if op["op_id"] in self.op_ids:
            raise InkError("DUPLICATE_OP")
        if op["origin"] != "user":
            raise InkError("INVALID_ORIGIN")
        payload = op["payload"]
        if op["type"] == "CREATE_PAGE":
            if op["page_id"] in self.pages:
                raise InkError("DUPLICATE_PAGE")
            is_portrait = payload["height"] >= payload["width"]
            if is_portrait != (payload["orientation"] == "portrait"):
                raise InkError("INVALID_PAGE")
            self.pages[op["page_id"]] = payload
        else:
            if op["page_id"] not in self.pages:
                raise InkError("UNKNOWN_PAGE")
            if op["page_id"] in self.deleted:
                raise InkError("PAGE_DELETED")
            self.deleted.add(op["page_id"])
        self.op_ids.add(op["op_id"])
        self.chain_hash = chain_next(self.chain_hash, op_hash(op))


def replay_page(
    page_id: str, width: int, height: int, ops: list[dict[str, Any]], pin_index: int = 0
) -> PageState:
    state = PageState(page_id, width, height, pin_index=pin_index)
    for op in ops:
        state.apply(op)
    return state
