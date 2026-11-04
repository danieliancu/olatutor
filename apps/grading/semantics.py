"""The manual adaptor for the semantic layer. Free of Django. See ADR 0006.

Confirmed text becomes a Page Semantics v2 graph, and grading reads the steps back from that graph.
It holds no stroke IDs, no geometry and no confidence, because none of them exist for typed text. It
says nothing about whether the text matches the ink. The expected answer is never put in a graph.
"""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SEMANTIC_VERSION = 2
MANUAL_LAYER = "manual_transcription"
PROVENANCE = "manual_entry"
TOOL = "olatutor-manual-demo"
TOOL_VERSION = "1"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "contracts/page_semantics/v2/schema.json"
_VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text("utf-8")))


class GraphRefused(ValueError):
    """Not a graph this stage may grade. Refused, never reinterpreted."""


def build_manual_graph(
    *,
    notebook_id: str,
    page_id: str,
    revision: int,
    seq: int,
    visible_hash: str,
    exercise_ref: str,
    steps: list[str],
    processed_at: str,
) -> dict[str, Any]:
    def edge(edge_id: str, kind: str, start: str, end: str) -> dict[str, Any]:
        return {
            "id": edge_id,
            "type": kind,
            "from": start,
            "to": end,
            "confidence": None,
            "hypothesis_group": None,
        }

    def node(node_id: str, kind: str, layer: str, content: str | None) -> dict[str, Any]:
        return {
            "id": node_id,
            "type": kind,
            "layer": layer,
            "bbox": None,
            "stroke_ids": [],
            "source_content_id": content,
            "candidates": [],
            "attributes": {},
        }

    nodes = [
        node("problem", "Problem", "exercise", exercise_ref),
        node("solution", "Solution", MANUAL_LAYER, None),
    ]
    edges = [edge("solves", "BELONGS_TO_PROBLEM", "solution", "problem")]
    for order, text in enumerate(steps, start=1):
        step = node(f"step-{order}", "SolutionStep", MANUAL_LAYER, None)
        step["candidates"] = [{"text": text, "confidence": None}]
        step["attributes"] = {"order": order}
        nodes.append(step)
        edges.append(edge(f"contains-{order}", "CONTAINS", "solution", f"step-{order}"))
        if order > 1:
            edges.append(
                edge(f"order-{order}", "FOLLOWS_STEP", f"step-{order}", f"step-{order - 1}")
            )

    return {
        "schema": "tutor.page_semantics",
        "version": SEMANTIC_VERSION,
        "source": {
            "notebook_id": notebook_id,
            "page_id": page_id,
            "revision": revision,
            "seq": seq,
            "visible_hash": visible_hash,
        },
        "producer": {
            "kind": "manual_transcription",
            "tool": TOOL,
            "tool_version": TOOL_VERSION,
            "processed_at": processed_at,
            "confirmed_by": "prototype_user",
        },
        "nodes": nodes,
        "edges": edges,
        "hypothesis_groups": [],
    }


def confirmed_steps(graph: dict[str, Any]) -> list[tuple[str, str]]:
    """Returns (node id, text) in the order given by FOLLOWS_STEP. Grading reads only this."""
    if next(_VALIDATOR.iter_errors(graph), None) is not None:
        raise GraphRefused("the graph does not match Page Semantics v2")
    if graph["producer"]["kind"] != "manual_transcription":
        raise GraphRefused("only manually confirmed graphs can be graded at this stage")

    steps = {node["id"]: node for node in graph["nodes"] if node["type"] == "SolutionStep"}
    for node in steps.values():
        if (
            node["layer"] != MANUAL_LAYER
            or node["stroke_ids"]
            or node["bbox"] is not None
            or len(node["candidates"]) != 1
            or node["candidates"][0]["confidence"] is not None
        ):
            raise GraphRefused("a step does not have manual provenance")

    successor: dict[str, str] = {}
    followers: set[str] = set()
    for edge in graph["edges"]:
        if edge["type"] == "FOLLOWS_STEP":
            if edge["from"] not in steps or edge["to"] not in steps or edge["to"] in successor:
                raise GraphRefused("the step order is not a single line")
            successor[edge["to"]] = edge["from"]
            followers.add(edge["from"])
    first = [node_id for node_id in steps if node_id not in followers]
    if len(first) != 1 and steps:
        raise GraphRefused("the step order is not a single line")

    ordered: list[str] = []
    current = first[0] if first else None
    while current is not None and len(ordered) <= len(steps):
        ordered.append(current)
        current = successor.get(current)
    if len(ordered) != len(steps):
        raise GraphRefused("the step order is not a single line")
    return [(node_id, steps[node_id]["candidates"][0]["text"]) for node_id in ordered]
