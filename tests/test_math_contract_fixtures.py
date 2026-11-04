"""Which existing grading fixtures became implementation tests in Milestone 4A, and which did not.

The fixtures themselves are not edited. Cases outside 4A must not be guessed: the engine either
returns UNSUPPORTED with no mark or refuses the contract. They remain acceptance cases for later.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from apps.grading.engine.exercise import ExerciseContractError, build_exercise
from apps.grading.engine.grade import grade_steps

FIXTURES = Path(__file__).resolve().parents[1] / "contracts" / "grading" / "v1" / "fixtures"
AXES = ("mathematical_status", "task_compliance", "error_class", "score")


def contract(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text("utf-8"))


def built(data: dict[str, Any], start: str) -> Any:
    return build_exercise(
        exercise_id="fixture",
        version=1,
        title="Fixture",
        start_expression=start,
        steps_required=False,
        contract=data,
    )


def axes(result: Any) -> tuple[Any, ...]:
    return tuple(getattr(result, name) for name in AXES)


def declared(example: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(example[name] for name in AXES)


SIMPLIFY = contract("contract_simplify_fraction")
ROUNDING = contract("contract_rounding_units")


@pytest.mark.parametrize("example", SIMPLIFY["examples"], ids=lambda e: e["answer"])
def test_simplify_fixture_is_implemented_in_full(example: dict[str, Any]) -> None:
    assert axes(grade_steps([example["answer"]], built(SIMPLIFY, "2/4"))) == declared(example)


def test_the_rounding_fixture_as_written_is_refused_because_it_declares_units() -> None:
    with pytest.raises(ExerciseContractError, match="units"):
        built(ROUNDING, "7 ÷ 3")


# The statement is prose, so the fixture gives no start expression; "7 ÷ 3" is read from it by hand.
# Only the unit rule is removed, for the unit-free answers below. The fixture file stays unchanged.
UNITLESS = {**ROUNDING, "units": None}
ROUNDING_IN_SCOPE = [e for e in ROUNDING["examples"] if e["answer"] in {"2.33", "2.3"}]
ROUNDING_OUT_OF_SCOPE = [e for e in ROUNDING["examples"] if e not in ROUNDING_IN_SCOPE]


@pytest.mark.parametrize("example", ROUNDING_IN_SCOPE, ids=lambda e: e["answer"])
def test_rounding_examples_without_units_are_implemented(example: dict[str, Any]) -> None:
    assert axes(grade_steps([example["answer"]], built(UNITLESS, "7 ÷ 3"))) == declared(example)


@pytest.mark.parametrize("example", ROUNDING_OUT_OF_SCOPE, ids=lambda e: e["answer"])
def test_answers_with_units_are_outside_4a_and_never_guessed(example: dict[str, Any]) -> None:
    assert " " in example["answer"], "only answers with a unit should be listed here"
    result = grade_steps([example["answer"]], built(UNITLESS, "7 ÷ 3"))
    assert result.mathematical_status == "UNSUPPORTED"
    assert result.score is None
    assert result.requires_review is True


@pytest.mark.parametrize("name", ["contract_quadratic_roots", "contract_rational_domain"])
def test_algebra_contracts_are_outside_4a_and_refused(name: str) -> None:
    with pytest.raises(ExerciseContractError):
        built(contract(name), "1")


@pytest.mark.parametrize("name", ["contract_quadratic_roots", "contract_rational_domain"])
def test_algebra_answers_are_never_marked_wrong(name: str) -> None:
    for example in contract(name)["examples"]:
        result = grade_steps([example["answer"]], built(SIMPLIFY, "2/4"))
        assert result.mathematical_status == "UNSUPPORTED", example["answer"]
        assert result.score is None
