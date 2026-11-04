"""Loads the versioned exercise catalogue. Free of Django.

The server's copy is the only authority on an exercise: its expected result and marks never come
from a client. A catalogue that breaks a rule or a budget limit stops loading, loudly.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .engine.exercise import Exercise, ExerciseContractError, build_exercise
from .engine.limits import DEFAULT_LIMITS, Limits

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = Path(__file__).resolve().parent / "exercises" / "catalog_v1.json"
_CATALOG_SCHEMA = ROOT / "contracts/grading/v1/exercise_catalog.schema.json"
_GRADING_SCHEMA = ROOT / "contracts/grading/v1/schema.json"


def parse_catalog(data: dict[str, Any], limits: Limits = DEFAULT_LIMITS) -> dict[str, Exercise]:
    catalog_validator = Draft202012Validator(json.loads(_CATALOG_SCHEMA.read_text("utf-8")))
    contract_validator = Draft202012Validator(json.loads(_GRADING_SCHEMA.read_text("utf-8")))
    error = next(catalog_validator.iter_errors(data), None)
    if error is not None:
        raise ExerciseContractError(f"catalogue {error.json_path}: {error.message}")

    exercises: dict[str, Exercise] = {}
    for item in data["exercises"]:
        exercise_id = item["exercise_id"]
        contract = item["contract"]
        error = next(contract_validator.iter_errors(contract), None)
        if error is not None:
            raise ExerciseContractError(f"{exercise_id} {error.json_path}: {error.message}")
        if contract.get("kind") != "contract":
            raise ExerciseContractError(f"{exercise_id}: not a contract")
        if exercise_id in exercises:
            raise ExerciseContractError(f"{exercise_id}: listed twice")
        exercises[exercise_id] = build_exercise(
            exercise_id=exercise_id,
            version=item["exercise_version"],
            title=item["title"],
            start_expression=item["start_expression"],
            steps_required=item["steps_required"],
            contract=contract,
            limits=limits,
        )
    return exercises


def raw_catalog() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(CATALOG_PATH.read_text("utf-8"))
    return data


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Exercise]:
    return parse_catalog(raw_catalog())
