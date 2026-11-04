"""Turns an engine assessment into grading v1 results. Free of Django.

`uncertainty.recognition` is null because no recogniser ran, so nothing was measured. It is not a
claim of certainty about the transcription. `uncertainty.mathematical` is null because the engine
either decides exactly or says UNSUPPORTED or UNDETERMINED: it does not estimate a probability.
"""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .engine.exercise import Exercise
from .engine.grade import NOT_EVALUATED, Assessment, StepVerdict, grade_steps
from .engine.version import GRADING_VERSION
from .semantics import confirmed_steps

_SCHEMA = Path(__file__).resolve().parents[2] / "contracts/grading/v1/schema.json"
_VALIDATOR = Draft202012Validator(json.loads(_SCHEMA.read_text("utf-8")))
_NO_SCORE = {"UNSUPPORTED", "UNDETERMINED"}


def _base(graph: dict[str, Any], exercise: Exercise) -> dict[str, Any]:
    source = graph["source"]
    return {
        "kind": "result",
        "version": 1,
        "page_revision": {
            "page_id": source["page_id"],
            "revision": source["revision"],
            "visible_hash": source["visible_hash"],
        },
        "exercise_ref": exercise.ref,
        "solution_ref": "solution",
        "uncertainty": {"recognition": None, "mathematical": None},
        "grading_version": GRADING_VERSION,
    }


def _checked(result: dict[str, Any]) -> dict[str, Any]:
    error = next(_VALIDATOR.iter_errors(result), None)
    if error is not None:
        raise ValueError(f"result breaks the grading contract at {error.json_path}")
    status = result["mathematical_status"]
    if status in _NO_SCORE and (result["score"] is not None or not result["requires_review"]):
        raise ValueError("undetermined work must have no score and must require review")
    if result["task_compliance"] == "COMPLIANT" and status != "CORRECT":
        raise ValueError("only correct work can be judged compliant")
    return result


def solution_result(
    assessment: Assessment, graph: dict[str, Any], exercise: Exercise, node_ids: list[str]
) -> dict[str, Any]:
    return _checked(
        {
            **_base(graph, exercise),
            "step_ref": None,
            "mathematical_status": assessment.mathematical_status,
            "task_compliance": assessment.task_compliance,
            "error_class": assessment.error_class,
            "score": assessment.score,
            "explanation_code": assessment.code,
            "requires_review": assessment.requires_review,
            "source_node_ids": node_ids,
        }
    )


def step_result(
    verdict: StepVerdict, graph: dict[str, Any], exercise: Exercise, node_id: str
) -> dict[str, Any]:
    """A step has no score of its own. Marks belong only to the whole solution."""
    return _checked(
        {
            **_base(graph, exercise),
            "step_ref": node_id,
            "mathematical_status": verdict.mathematical_status,
            "task_compliance": NOT_EVALUATED,
            "error_class": verdict.error_class,
            "score": None,
            "explanation_code": verdict.code,
            "requires_review": verdict.requires_review,
            "source_node_ids": [node_id],
        }
    )


def grade_graph(
    graph: dict[str, Any], exercise: Exercise
) -> tuple[Assessment, dict[str, Any], list[dict[str, Any]]]:
    """The only path from confirmed text to a verdict: it goes through the semantic graph."""
    steps = confirmed_steps(graph)
    node_ids = [node_id for node_id, _ in steps]
    assessment = grade_steps([text for _, text in steps], exercise)
    step_results = [
        step_result(verdict, graph, exercise, node_ids[verdict.index])
        for verdict in assessment.step_verdicts
    ]
    return assessment, solution_result(assessment, graph, exercise, node_ids), step_results
