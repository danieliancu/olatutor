"""Exercise rules: what one exercise declares, checked against what the engine actually implements.

A contract that asks for something unimplemented is refused at load time, so it can never be graded
by a rule that does not exist. All budget limits apply to contracts too.
"""

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .errors import ParseFailure, UndefinedValue
from .evaluate import evaluate
from .forms import IMPLEMENTED_FORMATS, meets_required_format
from .limits import DEFAULT_LIMITS, Budget, Limits
from .nodes import Node
from .normalize import normalize
from .parser import parse_expression
from .rounding import round_half_up
from .scoring import PARTIAL_CREDIT_RULES

IMPLEMENTED_METHOD_POLICIES = frozenset({"any_valid_chain", "not_applicable"})
MAX_ROUNDING_PLACES = 6


class ExerciseContractError(ValueError):
    """The contract cannot be graded by this engine. A configuration fault, not a student's."""


@dataclass(frozen=True)
class Exercise:
    exercise_id: str
    version: int
    title: str
    statement: str
    start_text: str
    start: Node
    start_value: Fraction
    expected_value: Fraction
    required_format: str
    rounding_places: int | None
    steps_required: bool
    max_score: int
    partial_credit: dict[str, int]
    limits: Limits

    @property
    def ref(self) -> str:
        return f"{self.exercise_id}@{self.version}"


def _parse_contract_expression(text: str, what: str, limits: Limits) -> tuple[Node, Fraction]:
    try:
        node = parse_expression(normalize(text), limits)
        return node, evaluate(node, Budget(limits))
    except ParseFailure as error:
        raise ExerciseContractError(f"{what} cannot be parsed: {error.code}") from error
    except UndefinedValue as error:
        raise ExerciseContractError(f"{what} divides by zero") from error


def build_exercise(
    *,
    exercise_id: str,
    version: int,
    title: str,
    start_expression: str,
    steps_required: bool,
    contract: dict[str, Any],
    limits: Limits = DEFAULT_LIMITS,
) -> Exercise:
    if contract["variable_domains"]:
        raise ExerciseContractError("variables are outside this engine's scope")
    if contract["units"] is not None:
        raise ExerciseContractError("units are outside this engine's scope")
    if contract["required_format"] not in IMPLEMENTED_FORMATS:
        raise ExerciseContractError(f"format not implemented: {contract['required_format']}")
    if contract["alternative_methods"] not in IMPLEMENTED_METHOD_POLICIES:
        raise ExerciseContractError(
            f"method policy not implemented: {contract['alternative_methods']}"
        )
    expected = contract["expected"]
    if expected["kind"] != "value" or len(expected["values"]) != 1:
        raise ExerciseContractError("only one expected value is implemented")

    rounding = contract["rounding"]
    places = None
    if rounding is not None:
        places = rounding["places"]
        if rounding["mode"] != "half_up" or places > MAX_ROUNDING_PLACES:
            raise ExerciseContractError("rounding rule not implemented")
    if contract["required_format"] == "decimal_places" and places is None:
        raise ExerciseContractError("decimal_places needs a rounding rule")

    max_score = contract["partial_credit"]["max_score"]
    partial_credit: dict[str, int] = {}
    for rule in contract["partial_credit"]["rules"]:
        if rule["when"] not in PARTIAL_CREDIT_RULES:
            raise ExerciseContractError(f"partial credit rule not implemented: {rule['when']}")
        if rule["score"] >= max_score:
            raise ExerciseContractError("partial credit must stay below the maximum score")
        partial_credit[rule["when"]] = rule["score"]

    start, start_value = _parse_contract_expression(start_expression, "start expression", limits)
    expected_node, expected_value = _parse_contract_expression(
        expected["values"][0], "expected value", limits
    )
    exact_or_rounded = start_value if places is None else round_half_up(start_value, places)
    if exact_or_rounded != expected_value:
        raise ExerciseContractError("expected value does not follow from the start expression")
    if not meets_required_format(expected_node, contract["required_format"], places):
        raise ExerciseContractError("expected value does not meet its own required format")

    return Exercise(
        exercise_id=exercise_id,
        version=version,
        title=title,
        statement=contract["statement"],
        start_text=start_expression,
        start=start,
        start_value=start_value,
        expected_value=expected_value,
        required_format=contract["required_format"],
        rounding_places=places,
        steps_required=steps_required,
        max_score=max_score,
        partial_credit=partial_credit,
        limits=limits,
    )
