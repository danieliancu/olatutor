"""Validate every contract fixture, independently of the application code.

Exits non-zero on the first category of failure. Run with no arguments from the repository root.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
HANDWRITING_LAYERS = {"student", "student_revision"}
HANDWRITING_TYPES = {"Expression", "Symbol", "TextBlock", "Diagram", "SolutionStep", "Correction"}
UNDETERMINED_STATUSES = {"UNSUPPORTED", "UNDETERMINED"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def validator(path: Path) -> Draft202012Validator:
    schema = load_json(path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def graph_rule_violation(graph: dict[str, Any]) -> str | None:
    """Cross-reference rules that JSON Schema cannot express. Returns the first broken rule."""
    node_ids = [node["id"] for node in graph["nodes"]]
    if len(set(node_ids)) != len(node_ids):
        return "DUPLICATE_ID"
    known = set(node_ids)
    groups = {group["id"]: group for group in graph["hypothesis_groups"]}
    masses: dict[str, float] = defaultdict(float)
    successors: dict[str, list[str]] = defaultdict(list)

    for node in graph["nodes"]:
        if node["layer"] == "exercise" and node["stroke_ids"]:
            return "LAYER_SEPARATION"
        if (
            node["layer"] in HANDWRITING_LAYERS
            and node["type"] in HANDWRITING_TYPES
            and not node["stroke_ids"]
        ):
            return "PROVENANCE"

    for edge in graph["edges"]:
        if edge["from"] not in known or edge["to"] not in known:
            return "EDGE_ENDPOINT"
        group = edge["hypothesis_group"]
        if group is not None:
            if group not in groups:
                return "HYPOTHESIS_GROUP"
            masses[group] += edge["confidence"]["value"]
        if edge["type"] == "NEXT_IN_READING_ORDER":
            successors[edge["from"]].append(edge["to"])

    for group_id, group in groups.items():
        if masses[group_id] + group["unresolved_mass"] > 1.000001:
            return "HYPOTHESIS_MASS"

    visiting: set[str] = set()
    done: set[str] = set()

    def has_cycle(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in done:
            return False
        visiting.add(node_id)
        found = any(has_cycle(next_id) for next_id in successors[node_id])
        visiting.discard(node_id)
        done.add(node_id)
        return found

    if any(has_cycle(node_id) for node_id in list(successors)):
        return "READING_ORDER_CYCLE"
    return None


def result_rule_violation(result: dict[str, Any]) -> str | None:
    if result["error_class"] == "UNREADABLE" and result["mathematical_status"] == "INCORRECT":
        return "UNCERTAINTY_IS_NOT_WRONG"
    if result["mathematical_status"] in UNDETERMINED_STATUSES:
        if result["score"] is not None:
            return "UNDETERMINED_HAS_NO_SCORE"
        if not result["requires_review"]:
            return "REVIEW_REQUIRED"
    return None


def check_contract_examples(contract: dict[str, Any]) -> str | None:
    max_score = contract["partial_credit"]["max_score"]
    for example in contract["examples"]:
        score = example["score"]
        if example["mathematical_status"] in UNDETERMINED_STATUSES and score is not None:
            return f"{example['answer']}: undetermined work has no score"
        if score is not None and score > max_score:
            return f"{example['answer']}: score above max_score"
        if (
            example["task_compliance"] == "COMPLIANT"
            and example["mathematical_status"] != "CORRECT"
        ):
            return f"{example['answer']}: only correct work can be judged compliant"
    return None


def main() -> int:
    failures: list[str] = []
    checked = 0

    def fail(message: str) -> None:
        failures.append(message)

    semantic = validator(CONTRACTS / "page_semantics/v1/schema.json")
    semantic_dir = CONTRACTS / "page_semantics/v1/fixtures"
    for path in sorted(semantic_dir.glob("valid_*.json")):
        checked += 1
        graph = load_json(path)
        for error in semantic.iter_errors(graph):
            fail(f"{path.name}: {error.json_path}: {error.message}")
        rule = graph_rule_violation(graph)
        if rule:
            fail(f"{path.name}: valid fixture broke {rule}")

    base_graph = load_json(semantic_dir / "valid_ambiguous_crossed_out.json")
    for case in load_json(semantic_dir / "invalid_cases.json")["cases"]:
        checked += 1
        graph = {**base_graph, **case["patch"]}
        schema_broken = next(semantic.iter_errors(graph), None) is not None
        got = "SCHEMA" if schema_broken else graph_rule_violation(graph)
        if got != case["rule"]:
            fail(f"semantics {case['name']}: expected {case['rule']}, got {got}")

    grading = validator(CONTRACTS / "grading/v1/schema.json")
    grading_dir = CONTRACTS / "grading/v1/fixtures"
    for path in sorted(grading_dir.glob("contract_*.json")):
        checked += 1
        contract = load_json(path)
        for error in grading.iter_errors(contract):
            fail(f"{path.name}: {error.json_path}: {error.message}")
        problem = check_contract_examples(contract)
        if problem:
            fail(f"{path.name}: {problem}")

    base_result = load_json(grading_dir / "result_review_required.json")
    checked += 1
    for error in grading.iter_errors(base_result):
        fail(f"result_review_required.json: {error.json_path}: {error.message}")
    if result_rule_violation(base_result):
        fail("result_review_required.json: valid fixture broke a rule")
    for case in load_json(grading_dir / "invalid_results.json")["cases"]:
        checked += 1
        result = {**base_result, **case["patch"]}
        schema_broken = next(grading.iter_errors(result), None) is not None
        got = "SCHEMA" if schema_broken else result_rule_violation(result)
        if got != case["rule"]:
            fail(f"grading {case['name']}: expected {case['rule']}, got {got}")

    ink = validator(CONTRACTS / "digital_ink/v1/schema.json")
    ink_dir = CONTRACTS / "digital_ink/v1/fixtures"
    for name in ("replay.json", "random.json"):
        for case in load_json(ink_dir / name)["cases"]:
            checked += 1
            for op in case["ops"]:
                for error in ink.iter_errors(op):
                    fail(f"{name} {case['name']}: {error.json_path}: {error.message}")

    device = yaml.safe_load((CONTRACTS / "device_api/v1/openapi.draft.yaml").read_text("utf-8"))
    checked += 1
    if (
        "draft" not in device["info"]["version"]
        or "NOT IMPLEMENTED" not in device["info"]["description"]
    ):
        fail("device API must stay clearly marked as an unimplemented draft")

    profile_path = ROOT / "firmware/elecrow_esp32p4/hardware-profile.yaml"
    profile = yaml.safe_load(profile_path.read_text("utf-8"))
    for name, field in profile["fields"].items():
        checked += 1
        if field.get("status") not in {"documented", "measured", "unknown"}:
            fail(f"hardware profile {name}: invalid status")
        if field.get("status") != "unknown" and not field.get("source"):
            fail(f"hardware profile {name}: a known value needs a source")
    measured = any(field["status"] == "measured" for field in profile["fields"].values())
    if measured and not profile.get("measurements_log"):
        fail("hardware profile: measured values need a measurements log")

    for failure in failures:
        print(f"FAIL {failure}")
    print(f"{checked} contract checks, {len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
