"""Structural validation of incoming operations against the versioned contract."""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .encoding import InkError, scan

CONTRACT_DIR = Path(__file__).resolve().parents[3] / "contracts" / "digital_ink" / "v1"
OPERATION_SCHEMA: dict[str, Any] = json.loads((CONTRACT_DIR / "schema.json").read_text("utf-8"))
_validator = Draft202012Validator(OPERATION_SCHEMA)

# Navigation is local to a client: it is never journaled, hashed or sent.
LOCAL_ONLY = {"CHANGE_PAGE"}


def validate_op(op: Any) -> None:
    """Checks run in the fixed order of spec section 9, so both cores report the same code."""
    if not isinstance(op, dict):
        raise InkError("INVALID_SHAPE", "operation must be an object")
    scan(op)
    if op.get("v") != 1:
        raise InkError("UNKNOWN_VERSION")
    if op.get("type") in LOCAL_ONLY:
        raise InkError("UNSUPPORTED_OP", str(op["type"]))
    error = next(iter(_validator.iter_errors(op)), None)
    if error is not None:
        raise InkError("INVALID_SHAPE", f"{error.json_path}: {error.message}"[:300])
