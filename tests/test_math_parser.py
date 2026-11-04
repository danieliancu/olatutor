"""Parsing, normalisation, exact values and limits. Expected values here are written by hand."""

import ast
import subprocess
import sys
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from apps.grading.engine.errors import FailureKind, ParseFailure, UndefinedValue
from apps.grading.engine.evaluate import evaluate
from apps.grading.engine.forms import meets_required_format
from apps.grading.engine.limits import Budget, Limits
from apps.grading.engine.nodes import FracLit, Group, MixedLit, Unary, render, to_dict
from apps.grading.engine.normalize import normalize
from apps.grading.engine.parser import parse_expression
from apps.grading.engine.rounding import as_decimal, round_half_up, truncate

ENGINE = Path(__file__).resolve().parents[1] / "apps" / "grading" / "engine"


def parse(text: str):
    return parse_expression(normalize(text))


def value(text: str) -> Fraction:
    return evaluate(parse(text))


def failure(text: str, limits: Limits | None = None) -> ParseFailure:
    with pytest.raises(ParseFailure) as caught:
        if limits is None:
            parse(text)
        else:
            parse_expression(normalize(text), limits)
    return caught.value


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("7", Fraction(7)),
        ("3 + 4 × 2", Fraction(11)),
        ("(3 + 4) × 2", Fraction(14)),
        ("20 - 5 - 3", Fraction(12)),
        ("24 ÷ 4 ÷ 2", Fraction(3)),
        ("2 × 3 + 4 × 5", Fraction(26)),
        ("10 - 2 × 3", Fraction(4)),
        ("(2 + 3) × (4 - 1)", Fraction(15)),
        ("((1 + 2) × (3 + 4))", Fraction(21)),
        ("7 ÷ 3", Fraction(7, 3)),
        ("1/2 + 1/3", Fraction(5, 6)),
        ("3/4 × 8", Fraction(6)),
        ("2/4", Fraction(1, 2)),
        ("6 ÷ (2/3)", Fraction(9)),
        ("(1 + 1)/2", Fraction(1)),
        ("1 1/2", Fraction(3, 2)),
        ("1 1/2 + 3/4", Fraction(9, 4)),
        ("-1 1/2", Fraction(-3, 2)),
        ("2 - 1 1/2", Fraction(1, 2)),
        ("-(1 1/2)", Fraction(-3, 2)),
        ("0.1 + 0.2", Fraction(3, 10)),
        ("1.25 + 0.5", Fraction(7, 4)),
        ("1.50", Fraction(3, 2)),
        ("1.5/2", Fraction(3, 4)),
        ("-3 + 5", Fraction(2)),
        ("3 - -2", Fraction(5)),
        ("3 × -2", Fraction(-6)),
        ("+4", Fraction(4)),
        ("007", Fraction(7)),
    ],
)
def test_exact_values_against_hand_worked_references(text: str, expected: Fraction) -> None:
    assert value(text) == expected


def test_decimals_are_exact_where_binary_floats_are_not() -> None:
    assert value("0.1 + 0.2") == value("0.3")
    assert value("0.1 × 3") == Fraction(3, 10)
    assert value("1.1 × 1.1") == Fraction(121, 100)


@pytest.mark.parametrize(
    ("raw", "normal"),
    [
        ("3−2", "3-2"),
        ("3–2", "3-2"),
        ("3*2", "3×2"),
        ("1⁄2", "1/2"),
        ("1∕2", "1/2"),
        ("1 1/2", "1 1/2"),
        ("  3   +\t4 ", "3 + 4"),
        ("½", "1/2"),
        ("1½", "1 1/2"),
        ("2 ¾", "2 3/4"),
    ],
)
def test_normalisation_is_an_explicit_table(raw: str, normal: str) -> None:
    assert normalize(raw) == normal


def test_vulgar_fraction_never_merges_with_a_digit() -> None:
    assert value("1½") == Fraction(3, 2), "NFKC would read this as 11/2"
    assert failure("½3").code == "AMBIGUOUS_NUMBER_FORMAT", "must not become 1/23"


@pytest.mark.parametrize(
    "text",
    [
        "١٢",  # Arabic-Indic digits
        "１２",  # full-width digits
        "1​2",  # zero-width space between digits
        "3‮+4",  # bidirectional override
        "\x00",
        "\n",
    ],
)
def test_unlisted_characters_are_refused_and_never_mapped(text: str) -> None:
    assert failure(text).kind is FailureKind.UNSUPPORTED


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("", "EMPTY_EXPRESSION"),
        ("   ", "EMPTY_EXPRESSION"),
        ("3 +", "INCOMPLETE_EXPRESSION"),
        ("3 + × 2", "INCOMPLETE_EXPRESSION"),
        ("(1 + 2", "INCOMPLETE_EXPRESSION"),
        ("1 + 2)", "INCOMPLETE_EXPRESSION"),
        ("()", "INCOMPLETE_EXPRESSION"),
        ("×3", "INCOMPLETE_EXPRESSION"),
        ("1/", "INCOMPLETE_EXPRESSION"),
        ("2 3", "MISSING_OPERATOR"),
        ("2(3)", "MISSING_OPERATOR"),
        ("(2)3", "MISSING_OPERATOR"),
        ("(2)(3)", "MISSING_OPERATOR"),
        ("1/2 3", "MISSING_OPERATOR"),
        ("1.5 2", "MISSING_OPERATOR"),
        ("1/2/3", "AMBIGUOUS_FRACTION_CHAIN"),
        ("6÷2/3", "AMBIGUOUS_FRACTION_CHAIN"),
        ("3/4 ÷ 2/5", "AMBIGUOUS_FRACTION_CHAIN"),
        ("(1+1)/2/3", "AMBIGUOUS_FRACTION_CHAIN"),
        ("1 2/3/4", "AMBIGUOUS_FRACTION_CHAIN"),
        ("(1)/(2)/3", "AMBIGUOUS_FRACTION_CHAIN"),
        ("1.5/2.5/3", "AMBIGUOUS_FRACTION_CHAIN"),
        ("8÷2.5/2", "AMBIGUOUS_FRACTION_CHAIN"),
        ("1 3/2", "AMBIGUOUS_MIXED_NUMBER"),
        ("1 2/2", "AMBIGUOUS_MIXED_NUMBER"),
        (".5", "AMBIGUOUS_NUMBER_FORMAT"),
        ("5.", "AMBIGUOUS_NUMBER_FORMAT"),
        ("1.2.3", "AMBIGUOUS_NUMBER_FORMAT"),
        ("1,5", "AMBIGUOUS_NUMBER_FORMAT"),
        ("1,000", "AMBIGUOUS_NUMBER_FORMAT"),
        ("1·5", "AMBIGUOUS_NUMBER_FORMAT"),
        ("--2", "AMBIGUOUS_REPEATED_SIGN"),
        ("3 + - - 2", "AMBIGUOUS_REPEATED_SIGN"),
        ("3 x 4", "AMBIGUOUS_MULTIPLY_X"),
        ("3 X 4", "AMBIGUOUS_MULTIPLY_X"),
    ],
)
def test_unfinished_or_ambiguous_input_asks_rather_than_guesses(text: str, code: str) -> None:
    found = failure(text)
    assert found.code == code
    assert found.kind is FailureKind.UNDETERMINED


def test_brackets_settle_what_was_ambiguous() -> None:
    assert value("6 ÷ (2/3)") == Fraction(9)
    assert value("(6 ÷ 2)/3") == Fraction(1)
    assert value("(1/2)/3") == Fraction(1, 6)
    assert value("3/4 ÷ (2/5)") == Fraction(15, 8)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("half", "UNSUPPORTED_SYMBOL"),
        ("x", "UNSUPPORTED_SYMBOL"),
        ("x + 1", "UNSUPPORTED_SYMBOL"),
        ("3 cm", "UNSUPPORTED_SYMBOL"),
        ("2.33 cm", "UNSUPPORTED_SYMBOL"),
        ("sqrt(4)", "UNSUPPORTED_SYMBOL"),
        ("__import__('os')", "UNSUPPORTED_SYMBOL"),
        ("2^3", "UNSUPPORTED_OPERATOR"),
        ("50%", "UNSUPPORTED_OPERATOR"),
        ("6:2", "UNSUPPORTED_OPERATOR"),
        ("√4", "UNSUPPORTED_OPERATOR"),
        ("2²", "UNSUPPORTED_OPERATOR"),
        ("3 > 2", "UNSUPPORTED_OPERATOR"),
    ],
)
def test_outside_the_declared_scope_is_unsupported(text: str, code: str) -> None:
    found = failure(text)
    assert found.code == code
    assert found.kind is FailureKind.UNSUPPORTED


@pytest.mark.parametrize("text", ["1/0", "3 ÷ 0", "1 1/0", "5 ÷ (2 - 2)", "0/0", "1.5 / 0.0"])
def test_division_by_zero_is_undefined_and_not_a_parse_failure(text: str) -> None:
    node = parse(text)
    with pytest.raises(UndefinedValue):
        evaluate(node)


def test_written_structure_is_kept_before_simplification() -> None:
    node = parse("2/4")
    assert node == FracLit("2", "4")
    assert render(node) == "2/4"
    assert to_dict(node) == {"t": "fraction", "n": "2", "d": "4"}
    assert render(parse("1.50")) == "1.50"
    assert render(parse("(1+2)*3")) == "(1 + 2) × 3"
    assert parse("-1 1/2") == Unary("-", MixedLit("1", "1", "2"))
    assert isinstance(parse("(2)"), Group)


@pytest.mark.parametrize(
    ("text", "required", "places", "expected"),
    [
        ("1/2", "lowest_terms", None, True),
        ("2/4", "lowest_terms", None, False),
        ("0.5", "lowest_terms", None, False),
        ("3", "lowest_terms", None, True),
        ("7/6", "lowest_terms", None, True),
        ("1 1/4", "lowest_terms", None, True),
        ("1 2/8", "lowest_terms", None, False),
        ("(1/2)", "lowest_terms", None, False),
        ("1/2 + 0", "lowest_terms", None, False),
        ("-1/2", "lowest_terms", None, True),
        ("2 1/4", "mixed_number", None, True),
        ("9/4", "mixed_number", None, False),
        ("2 2/8", "mixed_number", None, False),
        ("3", "mixed_number", None, True),
        ("6", "integer", None, True),
        ("6.0", "integer", None, False),
        ("6/1", "integer", None, False),
        ("2.33", "decimal_places", 2, True),
        ("2.3", "decimal_places", 2, False),
        ("2.330", "decimal_places", 2, False),
        ("2", "decimal_places", 2, False),
        ("1 3/4", "any", None, True),
        ("1 + 1", "any", None, False),
    ],
)
def test_required_form_is_judged_on_what_was_written(
    text: str, required: str, places: int | None, expected: bool
) -> None:
    assert meets_required_format(parse(text), required, places) is expected


@pytest.mark.parametrize(
    ("value_", "places", "expected"),
    [
        (Fraction(7, 3), 2, Fraction(233, 100)),
        (Fraction(8, 3), 2, Fraction(267, 100)),
        (Fraction(5, 2), 0, Fraction(3)),
        (Fraction(-5, 2), 0, Fraction(-3)),
        (Fraction(1, 8), 2, Fraction(13, 100)),
        (Fraction(-1, 8), 2, Fraction(-13, 100)),
        (Fraction(0), 2, Fraction(0)),
    ],
)
def test_half_up_on_hand_worked_cases(value_: Fraction, places: int, expected: Fraction) -> None:
    assert round_half_up(value_, places) == expected


def test_truncation_and_decimal_presentation() -> None:
    assert truncate(Fraction(8, 3), 2) == Fraction(266, 100)
    assert truncate(Fraction(-8, 3), 2) == Fraction(-266, 100)
    assert as_decimal(Fraction(233, 100), 2) == Decimal("2.33")
    assert str(as_decimal(Fraction(23, 10), 2)) == "2.30"
    assert str(as_decimal(Fraction(-1, 2), 1)) == "-0.5"
    with pytest.raises(ValueError, match="more decimal places"):
        as_decimal(Fraction(1, 3), 2)
    assert Decimal("2.5").quantize(Decimal(1), rounding=ROUND_HALF_UP) == Decimal(3)


@pytest.mark.parametrize(
    ("text", "limits", "limit"),
    [
        ("1" * 600, Limits(), "max_expression_bytes"),
        ("1" * 19, Limits(), "max_literal_digits"),
        ("1." + "1" * 18, Limits(), "max_literal_digits"),
        ("+".join(["1"] * 65), Limits(), "max_tokens"),
        ("(" * 25 + "1" + ")" * 25, Limits(), "max_depth"),
        ("1+1+1+1", Limits(max_operations=2), "max_operations"),
        ("-1+-1", Limits(max_operations=2), "max_operations"),
    ],
)
def test_limits_apply_before_any_evaluation(text: str, limits: Limits, limit: str) -> None:
    found = failure(text, limits)
    assert found.kind is FailureKind.LIMIT
    assert found.code == "RESOURCE_LIMIT_EXCEEDED"
    assert found.limit == limit


def test_multibyte_input_counts_in_bytes_rather_than_characters() -> None:
    assert failure("× " * 200, Limits()).limit == "max_expression_bytes"


def test_growth_of_intermediate_values_is_limited() -> None:
    limits = Limits(max_value_bits=40)
    node = parse_expression(normalize("999999999 × 999999999 × 999999999"), limits)
    with pytest.raises(ParseFailure) as caught:
        evaluate(node, Budget(limits))
    assert caught.value.limit == "max_value_bits"


def test_budget_is_shared_across_evaluations() -> None:
    budget = Budget(Limits(max_operations_total=3))
    node = parse("1 + 1")
    evaluate(node, budget)
    evaluate(node, budget)
    evaluate(node, budget)
    with pytest.raises(ParseFailure) as caught:
        evaluate(node, budget)
    assert caught.value.limit == "max_operations_total"


def test_engine_source_never_evaluates_input_or_uses_floats() -> None:
    banned_calls = {"eval", "exec", "compile", "float", "sympify", "parse_expr", "__import__"}
    for path in ENGINE.glob("*.py"):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in banned_calls, f"{path.name} calls {node.func.id}"
            if isinstance(node, ast.Constant):
                assert not isinstance(node.value, float), f"{path.name} has a float literal"
            if isinstance(node, ast.Import | ast.ImportFrom):
                module = getattr(node, "module", None) or ""
                names = [alias.name for alias in node.names]
                for name in [module, *names]:
                    assert not name.startswith(("django", "sympy", "lark")), path.name


def test_engine_imports_and_runs_without_django() -> None:
    code = (
        "import sys\n"
        "from apps.grading.engine.grade import grade_steps\n"
        "from apps.grading.engine.feedback import render_feedback\n"
        "from apps.grading.engine.parser import parse_expression\n"
        "assert not any(name == 'django' or name.startswith('django.') for name in sys.modules)\n"
    )
    env = {"PYTHONPATH": str(ENGINE.parents[2])}
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
