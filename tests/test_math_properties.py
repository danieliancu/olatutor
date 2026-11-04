"""Mathematical invariants. References are built here with `Fraction`, not by the engine."""

import contextlib
from decimal import ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction
from math import gcd
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.grading.engine.errors import ParseFailure, UndefinedValue
from apps.grading.engine.evaluate import evaluate
from apps.grading.engine.exercise import build_exercise
from apps.grading.engine.forms import meets_required_format
from apps.grading.engine.grade import grade_steps
from apps.grading.engine.nodes import render
from apps.grading.engine.normalize import normalize
from apps.grading.engine.parser import parse_expression
from apps.grading.engine.rounding import round_half_up

small = st.integers(min_value=0, max_value=999)
positive = st.integers(min_value=1, max_value=999)


@st.composite
def literals(draw: Any) -> tuple[str, Fraction]:
    kind = draw(st.sampled_from(["int", "fraction", "mixed", "decimal"]))
    if kind == "int":
        number = draw(small)
        return str(number), Fraction(number)
    if kind == "fraction":
        top, bottom = draw(small), draw(positive)
        return f"({top}/{bottom})", Fraction(top, bottom)
    if kind == "mixed":
        whole, bottom = draw(small), draw(st.integers(min_value=2, max_value=99))
        top = draw(st.integers(min_value=0, max_value=bottom - 1))
        return f"({whole} {top}/{bottom})", whole + Fraction(top, bottom)
    whole, part = draw(small), draw(st.integers(min_value=0, max_value=999))
    places = draw(st.integers(min_value=1, max_value=3))
    digits = str(part).zfill(places)[:places]
    return f"{whole}.{digits}", whole + Fraction(int(digits), 10**places)


def combine(children: Any) -> Any:
    def build(left: tuple[str, Fraction], right: tuple[str, Fraction], op: str) -> Any:
        text = f"({left[0]} {op} {right[0]})"
        if op == "+":
            return text, left[1] + right[1]
        if op == "-":
            return text, left[1] - right[1]
        if op == "×":
            return text, left[1] * right[1]
        if right[1] == 0:
            return left
        return text, left[1] / right[1]

    return st.builds(build, children, children, st.sampled_from(["+", "-", "×", "÷"]))


expressions = st.recursive(literals(), combine, max_leaves=8)


@settings(max_examples=300)
@given(expressions)
def test_value_matches_an_independently_built_fraction(pair: tuple[str, Fraction]) -> None:
    text, expected = pair
    assert evaluate(parse_expression(normalize(text))) == expected


@settings(max_examples=200)
@given(expressions)
def test_rendering_then_parsing_keeps_structure_and_value(pair: tuple[str, Fraction]) -> None:
    node = parse_expression(normalize(pair[0]))
    again = parse_expression(normalize(render(node)))
    assert again == node
    assert evaluate(again) == evaluate(node)


@given(small, positive, st.integers(min_value=1, max_value=99))
def test_scaling_a_fraction_keeps_its_value(top: int, bottom: int, factor: int) -> None:
    plain = evaluate(parse_expression(f"{top}/{bottom}"))
    scaled = evaluate(parse_expression(f"{top * factor}/{bottom * factor}"))
    assert plain == scaled == Fraction(top, bottom)


@given(small, positive)
def test_lowest_terms_agrees_with_gcd(top: int, bottom: int) -> None:
    node = parse_expression(f"{top}/{bottom}")
    assert meets_required_format(node, "lowest_terms", None) is (gcd(top, bottom) == 1)


@given(
    st.integers(min_value=-(10**9), max_value=10**9),
    st.integers(min_value=0, max_value=6),
    st.integers(min_value=0, max_value=6),
)
def test_half_up_agrees_with_decimal_on_finite_decimals(
    digits: int, written_places: int, places: int
) -> None:
    exact = Decimal(digits).scaleb(-written_places)
    with localcontext() as context:
        context.prec = 40
        reference = exact.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    assert round_half_up(Fraction(digits, 10**written_places), places) == Fraction(reference)


@given(st.fractions(min_value=-1000, max_value=1000, max_denominator=999), st.integers(0, 6))
def test_rounding_stays_within_half_a_unit(value: Fraction, places: int) -> None:
    rounded = round_half_up(value, places)
    assert abs(rounded - value) <= Fraction(1, 2 * 10**places)
    assert round_half_up(rounded, places) == rounded


TEXT = st.text(alphabet="0123456789 +-×÷/().,=≈½xX^%ab−", max_size=30)


@settings(max_examples=500)
@given(TEXT)
def test_any_text_parses_or_fails_with_a_declared_failure(text: str) -> None:
    try:
        node = parse_expression(normalize(text))
    except ParseFailure:
        return
    with contextlib.suppress(UndefinedValue):
        assert isinstance(evaluate(node), Fraction)


def _exercise() -> Any:
    return build_exercise(
        exercise_id="property",
        version=1,
        title="Property",
        start_expression="3 + 4 × 2",
        steps_required=False,
        contract={
            "statement": "Work out 3 + 4 × 2.",
            "variable_domains": {},
            "units": None,
            "required_format": "integer",
            "alternative_methods": "any_valid_chain",
            "expected": {"kind": "value", "values": ["11"]},
            "rounding": None,
            "partial_credit": {"max_score": 2, "rules": []},
        },
    )


EXERCISE = _exercise()


@settings(max_examples=500)
@given(st.lists(TEXT, min_size=1, max_size=4))
def test_grading_any_text_upholds_the_contract_axes(lines: list[str]) -> None:
    result = grade_steps(lines, EXERCISE)
    if result.mathematical_status in {"UNSUPPORTED", "UNDETERMINED"}:
        assert result.score is None
        assert result.requires_review is True
    else:
        assert result.score is not None
        assert 0 <= result.score <= result.max_score
    if result.task_compliance == "COMPLIANT":
        assert result.mathematical_status == "CORRECT"
        assert result.score == result.max_score
    if result.mathematical_status == "INCORRECT":
        assert all(step.failure is None for step in result.steps), "unreadable work is never wrong"


def _outcome(lines: list[str]) -> Any:
    result = grade_steps(lines, EXERCISE)
    return (
        result.mathematical_status,
        result.task_compliance,
        result.error_class,
        result.score,
        result.code,
        [verdict.to_dict() for verdict in result.step_verdicts],
        [[item.to_dict() for item in step.expressions] for step in result.steps],
    )


@settings(max_examples=100)
@given(st.lists(TEXT, min_size=1, max_size=4))
def test_grading_is_deterministic(lines: list[str]) -> None:
    assert _outcome(lines) == _outcome(lines)


@given(st.integers(min_value=-500, max_value=500).filter(lambda n: n != 11))
def test_a_bare_wrong_integer_is_incorrect_with_no_invented_cause(answer: int) -> None:
    result = grade_steps([str(answer)], EXERCISE)
    assert result.mathematical_status == "INCORRECT"
    assert result.error_class is None
    assert result.score == 0
