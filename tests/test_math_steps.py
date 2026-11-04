"""Step chains, classification, scoring, feedback and the execution budget, without Django."""

import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from apps.grading import engine
from apps.grading.catalog import load_catalog, parse_catalog, raw_catalog
from apps.grading.engine.exercise import Exercise, ExerciseContractError
from apps.grading.engine.feedback import FEEDBACK, render_explanation, render_feedback
from apps.grading.engine.grade import grade_steps
from apps.grading.engine.limits import Limits
from apps.grading.engine.steps import LinkVerdict
from apps.grading.results import grade_graph
from apps.grading.semantics import GraphRefused, build_manual_graph, confirmed_steps

ORDER = "ks2.order.add-multiply"
TIMES = "ks2.multiply.two-digit"
SIMPLIFY = "ks2.fraction.simplify-2-4"
ADD = "ks2.fraction.add-unlike"
ROUND = "ks2.rounding.divide"


def exercise(exercise_id: str) -> Exercise:
    return load_catalog()[exercise_id]


def graded(exercise_id: str, *lines: str) -> Any:
    return grade_steps(list(lines), exercise(exercise_id))


def axes(result: Any) -> tuple[Any, ...]:
    return (result.mathematical_status, result.task_compliance, result.error_class, result.score)


def engine_source() -> str:
    root = Path(engine.__file__).parent
    return "\n".join(path.read_text("utf-8") for path in root.glob("*.py"))


@pytest.mark.parametrize("item", raw_catalog()["exercises"], ids=lambda item: item["exercise_id"])
def test_every_declared_catalogue_example_holds(item: dict[str, Any]) -> None:
    built = load_catalog()[item["exercise_id"]]
    for example in item["contract"]["examples"]:
        result = grade_steps([example["answer"]], built)
        expected = (
            example["mathematical_status"],
            example["task_compliance"],
            example["error_class"],
            example["score"],
        )
        assert axes(result) == expected, example["answer"]


def test_the_catalogue_is_small_and_versioned() -> None:
    catalogue = raw_catalog()
    assert catalogue["catalog_version"] == 1
    assert all(item["exercise_version"] >= 1 for item in catalogue["exercises"])
    assert 5 <= len(catalogue["exercises"]) <= 12


def test_simplify_two_quarters_keeps_correctness_and_compliance_apart() -> None:
    result = graded(SIMPLIFY, "2/4")
    assert axes(result) == ("CORRECT", "NON_COMPLIANT", "FORMAT_REQUIREMENT", 1)
    assert result.code == "VALUE_RIGHT_NOT_SIMPLIFIED"
    decimal = graded(SIMPLIFY, "0.5")
    assert decimal.code == "VALUE_RIGHT_FORM_WRONG", "0.5 is not an unsimplified fraction"


@pytest.mark.parametrize(
    "lines",
    [
        ["12 × 10 + 12 × 5 = 120 + 60 = 180"],
        ["15 × 12 = 15 × 10 + 15 × 2 = 150 + 30 = 180"],
        ["12 × 15 = 6 × 30", "= 180"],
        ["12 × 15", "10 × 15 + 2 × 15", "150 + 30", "180"],
        ["(10 + 2) × 15 = 150 + 30", "= 180"],
        ["24 × 15 ÷ 2 = 360 ÷ 2 = 180"],
    ],
)
def test_different_legitimate_methods_all_pass_with_no_text_comparison(lines: list[str]) -> None:
    result = graded(TIMES, *lines)
    assert axes(result) == ("CORRECT", "COMPLIANT", None, 3)
    assert all(verdict.mathematical_status == "CORRECT" for verdict in result.step_verdicts)


@pytest.mark.parametrize(
    "lines",
    [
        ["3/6 + 2/6 = 5/6"],
        ["6/12 + 4/12 = 10/12", "= 5/6"],
        ["0.5 + 1/3 = 3/6 + 2/6", "5/6"],
    ],
)
def test_alternative_fraction_methods(lines: list[str]) -> None:
    assert axes(graded(ADD, *lines)) == ("CORRECT", "COMPLIANT", None, 2)


def test_step_justification_is_separate_from_completeness() -> None:
    result = graded(ORDER, "3 + 8")
    assert [verdict.mathematical_status for verdict in result.step_verdicts] == ["CORRECT"]
    assert result.mathematical_status == "INCOMPLETE"
    assert result.code == "ANSWER_NOT_FINAL"
    assert result.score == 1, "by the declared partial-credit rule"


def test_a_wrong_link_is_found_at_its_line_and_later_lines_are_judged_locally() -> None:
    result = graded(ORDER, "3 + 8", "= 12", "= 6 + 6")
    statuses = [verdict.mathematical_status for verdict in result.step_verdicts]
    assert statuses == ["CORRECT", "INCORRECT", "CORRECT"]
    assert [v.follows_earlier_error for v in result.step_verdicts] == [False, False, True]
    assert result.focus_line == 2
    assert axes(result) == ("INCORRECT", "NOT_EVALUATED", "ARITHMETIC_ERROR", 0)


def test_right_final_value_does_not_hide_a_wrong_step() -> None:
    result = graded(ORDER, "3 + 8 = 12", "= 11")
    assert axes(result) == ("INCORRECT", "NOT_EVALUATED", "ARITHMETIC_ERROR", 0)
    assert result.code == "FINAL_RIGHT_AFTER_STEP_ERROR"
    assert result.focus_line == 1


@pytest.mark.parametrize(
    ("line", "error_class", "code"),
    [
        ("3 + 8 = 12", "ARITHMETIC_ERROR", "STEP_VALUE_CHANGED"),
        ("7 × 2", "INVALID_TRANSFORMATION", "TRANSFORMATION_CHANGED_VALUE"),
        ("7 × 2 = 14", "INVALID_TRANSFORMATION", "TRANSFORMATION_CHANGED_VALUE"),
        ("14", None, "ANSWER_VALUE_MISMATCH"),
    ],
)
def test_a_cause_is_named_only_with_evidence(line: str, error_class: str | None, code: str) -> None:
    result = graded(ORDER, line)
    assert result.mathematical_status == "INCORRECT"
    assert result.error_class == error_class
    assert result.code == code


def test_an_explicit_wrong_link_between_long_expressions_is_not_called_arithmetic() -> None:
    assert graded(ORDER, "3 + 4 × 2 = 7 × 2").error_class == "INVALID_TRANSFORMATION"


def test_one_operation_with_a_wrong_result_is_arithmetic() -> None:
    assert graded(TIMES, "12 × 15 = 170").error_class == "ARITHMETIC_ERROR"


@pytest.mark.parametrize("line", ["1/0", "3 + 8 = 3 ÷ 0"])
def test_division_by_zero_is_certain_and_named(line: str) -> None:
    result = graded(ORDER, line)
    assert axes(result) == ("INCORRECT", "NOT_EVALUATED", "DOMAIN_VIOLATION", 0)
    assert result.code == "DIVISION_BY_ZERO"
    assert result.requires_review is False


def test_the_line_after_a_division_by_zero_is_not_blamed_for_it() -> None:
    result = graded(ORDER, "1/0", "11")
    assert [v.code for v in result.step_verdicts] == ["DIVISION_BY_ZERO", "STEP_NOT_CHECKED"]


@pytest.mark.parametrize(
    ("line", "code"),
    [
        ("", "EMPTY_EXPRESSION"),
        ("3 +", "INCOMPLETE_EXPRESSION"),
        ("3 + 8 =", "INCOMPLETE_EXPRESSION"),
        ("= ", "EMPTY_EXPRESSION"),
        ("2 3", "MISSING_OPERATOR"),
        ("1/2/3", "AMBIGUOUS_FRACTION_CHAIN"),
        ("3 x 4", "AMBIGUOUS_MULTIPLY_X"),
        ("1,5", "AMBIGUOUS_NUMBER_FORMAT"),
    ],
)
def test_unclear_work_gets_no_mark_and_no_wrong_verdict(line: str, code: str) -> None:
    result = graded(ORDER, line)
    assert axes(result) == ("UNDETERMINED", "NOT_EVALUATED", None, None)
    assert result.requires_review is True
    assert result.code == code


@pytest.mark.parametrize(
    ("line", "code"),
    [
        ("half", "UNSUPPORTED_SYMBOL"),
        ("x = 11", "UNSUPPORTED_SYMBOL"),
        ("2^3", "UNSUPPORTED_OPERATOR"),
        ("11 cm", "UNSUPPORTED_SYMBOL"),
        ("3 + 8 ≈ 11", "APPROX_NOT_SUPPORTED"),
    ],
)
def test_unsupported_work_gets_no_mark_and_no_wrong_verdict(line: str, code: str) -> None:
    result = graded(ORDER, line)
    assert axes(result) == ("UNSUPPORTED", "NOT_EVALUATED", "UNSUPPORTED_METHOD", None)
    assert result.requires_review is True
    assert result.code == code


def test_an_unreadable_step_stops_a_verdict_even_with_a_right_final_answer() -> None:
    result = graded(ORDER, "3 + banana", "11")
    assert axes(result) == ("UNSUPPORTED", "NOT_EVALUATED", "UNSUPPORTED_METHOD", None)
    assert [v.mathematical_status for v in result.step_verdicts] == ["UNSUPPORTED", "UNDETERMINED"]
    assert result.steps[1].links[0].verdict is LinkVerdict.NOT_CHECKED


def test_a_step_is_not_invalid_merely_because_the_engine_cannot_read_it() -> None:
    result = graded(ORDER, "3 + 8", "3 + 2^3", "11")
    assert result.mathematical_status == "UNSUPPORTED"
    assert "INCORRECT" not in [v.mathematical_status for v in result.step_verdicts]


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("2.33", ("CORRECT", "COMPLIANT", None, 1)),
        ("7 ÷ 3 = 2.33", ("CORRECT", "COMPLIANT", None, 1)),
        ("7 ÷ 3 ≈ 2.33", ("CORRECT", "COMPLIANT", None, 1)),
        ("2.3", ("INCORRECT", "NOT_EVALUATED", "ROUNDING_ERROR", 0)),
        ("2.330", ("CORRECT", "NON_COMPLIANT", "FORMAT_REQUIREMENT", 0)),
        ("2 1/3", ("CORRECT", "NON_COMPLIANT", "FORMAT_REQUIREMENT", 0)),
        ("2.333", ("INCORRECT", "NOT_EVALUATED", "ROUNDING_ERROR", 0)),
    ],
)
def test_rounding_rules(line: str, expected: tuple[Any, ...]) -> None:
    assert axes(graded(ROUND, line)) == expected


def test_truncating_instead_of_rounding_is_a_rounding_error() -> None:
    raw = deepcopy(raw_catalog())
    item = next(i for i in raw["exercises"] if i["exercise_id"] == ROUND)
    item["start_expression"] = "8 ÷ 3"
    item["contract"]["expected"]["values"] = ["2.67"]
    built = parse_catalog(raw)[ROUND]
    assert grade_steps(["2.67"], built).score == 1
    assert grade_steps(["2.66"], built).error_class == "ROUNDING_ERROR"


def test_required_steps_are_really_required() -> None:
    assert graded(TIMES, "180").code == "STEPS_REQUIRED"
    copied = graded(TIMES, "12 × 15 = 180")
    assert copied.code == "STEPS_REQUIRED", "copying out the question is not working"
    assert graded(TIMES, "6 × 30 = 180").score == 3


def test_scores_come_only_from_declared_rules() -> None:
    assert graded("ks2.brackets.add-multiply", "7 × 2").score == 0, "no rule, so no credit"
    assert graded(ORDER, "3 + 8").score == 1
    assert graded(ORDER, "3 + 8", "1 + 2 + 8", "1 + 10", "12").score == 0, "lines earn no marks"


def test_every_feedback_text_renders_deterministically() -> None:
    for code in FEEDBACK:
        rendered = render_feedback(code, 2)
        assert rendered == render_feedback(code, 2)
        assert "{line}" not in str(rendered)
        assert render_explanation(code, None)
        assert "{" not in render_explanation(code, 2)


def test_every_code_the_engine_can_produce_has_feedback() -> None:
    source = engine_source()
    raised = re.findall(
        r'(?:undetermined|unsupported)\("([A-Z_]+)"\)|ParseFailure\(\w+\.\w+, "([A-Z_]+)"',
        source,
    )
    assert raised
    for pair in raised:
        assert (pair[0] or pair[1]) in FEEDBACK
    for code in re.findall(r'code = "([A-Z_]+)"', source):
        assert code in FEEDBACK
    for code in ("STEP_VALUE_KEPT", "STEP_ROUNDED", "STEP_NOT_CHECKED", "NOT_ROUNDED_AS_ASKED"):
        assert code in FEEDBACK


def test_feedback_never_reveals_an_answer() -> None:
    answers = {item["contract"]["expected"]["values"][0] for item in raw_catalog()["exercises"]}
    for code, feedback in FEEDBACK.items():
        for text in (feedback.checked, feedback.problem, feedback.hint, feedback.explanation):
            for answer in answers:
                pattern = rf"(?<![\d./]){re.escape(answer)}(?![\d./])"
                assert text is None or not re.search(pattern, text), code


def test_feedback_does_not_speculate_about_why() -> None:
    speculative = ("forgot", "misunderstood", "confused", "you think", "careless", "probably")
    for code, feedback in FEEDBACK.items():
        for text in (feedback.checked, feedback.problem, feedback.hint, feedback.explanation):
            assert text is None or not any(word in text.lower() for word in speculative), code


# Budget: a limit gives a controlled result, and the next request is unaffected.


@pytest.mark.parametrize(
    ("lines", "limits", "limit"),
    [
        (["1"] * 31, Limits(), "max_steps"),
        (["1" * 2049], Limits(), "max_step_bytes"),
        (["1" * 513], Limits(), "max_expression_bytes"),
        (["1 = " * 8 + "1"], Limits(), "max_expressions_per_step"),
        (["1" * 19], Limits(), "max_literal_digits"),
        (["(" * 25 + "1" + ")" * 25], Limits(), "max_depth"),
        (
            ["1 + 1 + 1 + 1 + 1 + 1 + 1 + 1"] * 3,
            Limits(max_operations_total=10),
            "max_operations_total",
        ),
    ],
)
def test_going_over_a_limit_returns_a_controlled_result(
    lines: list[str], limits: Limits, limit: str
) -> None:
    raw = deepcopy(raw_catalog())
    raw["exercises"] = [i for i in raw["exercises"] if i["exercise_id"] == ORDER]
    built = parse_catalog(raw, limits)[ORDER]
    result = grade_steps(lines, built)
    assert axes(result) == ("UNDETERMINED", "NOT_EVALUATED", None, None)
    assert result.code == "RESOURCE_LIMIT_EXCEEDED"
    assert result.requires_review is True
    assert result.limit == limit
    assert axes(grade_steps(["11"], built)) == ("CORRECT", "COMPLIANT", None, 2), "recovers"


def test_worst_case_inside_the_budget_finishes_fast() -> None:
    """A generous bound against pathological growth. The real distribution is in the benchmark."""
    factor = "999999999999999999/999999999999999989"
    line = " × ".join([factor] * 9)
    worst = [" = ".join([line] * 5)] * 30
    started = time.perf_counter()
    result = grade_steps(worst, exercise(ORDER))
    assert time.perf_counter() - started < 2
    assert result.limit == "max_operations_total"


# Contracts are refused at load when they ask for what is not implemented, or break a limit.


def with_contract(**changes: Any) -> dict[str, Any]:
    raw = deepcopy(raw_catalog())
    raw["exercises"] = [i for i in raw["exercises"] if i["exercise_id"] == SIMPLIFY]
    raw["exercises"][0]["contract"].update(changes)
    return raw


@pytest.mark.parametrize(
    "changes",
    [
        {"required_format": "collected"},
        {"required_format": "complete_solution_set"},
        {"alternative_methods": "listed_only"},
        {"units": {"expected": "cm", "accepted": ["cm"], "required": False}},
        {"variable_domains": {"x": {"set": "real", "excluded": []}}},
        {"expected": {"kind": "solution_set", "values": ["1/2"]}},
        {"expected": {"kind": "value", "values": ["1/3"]}},
        {"expected": {"kind": "value", "values": ["2/4"]}},
        {"expected": {"kind": "value", "values": ["1/0"]}},
        {"expected": {"kind": "value", "values": ["half"]}},
        {"partial_credit": {"max_score": 2, "rules": [{"when": "close enough", "score": 1}]}},
        {
            "partial_credit": {
                "max_score": 1,
                "rules": [{"when": "value equal but not in lowest terms", "score": 1}],
            }
        },
        {"rounding": {"places": 40, "mode": "half_up"}},
        {"extra_field": 1},
    ],
)
def test_contracts_asking_for_the_unimplemented_are_refused(changes: dict[str, Any]) -> None:
    with pytest.raises(ExerciseContractError):
        parse_catalog(with_contract(**changes))


def test_limits_also_apply_to_exercise_contracts() -> None:
    with pytest.raises(ExerciseContractError, match="RESOURCE_LIMIT_EXCEEDED"):
        parse_catalog(with_contract(), Limits(max_tokens=2))
    long_start = with_contract()
    long_start["exercises"][0]["start_expression"] = "+".join(["1"] * 65)
    with pytest.raises(ExerciseContractError, match="RESOURCE_LIMIT_EXCEEDED"):
        parse_catalog(long_start)


def test_malformed_catalogues_are_refused() -> None:
    with pytest.raises(ExerciseContractError):
        parse_catalog({"schema": "tutor.exercise_catalog", "catalog_version": 1, "exercises": []})
    duplicated = with_contract()
    duplicated["exercises"] = duplicated["exercises"] * 2
    with pytest.raises(ExerciseContractError, match="listed twice"):
        parse_catalog(duplicated)


# The semantic layer: grading reads a graph with honest provenance, and nothing else.


def graph_of(*steps: str) -> dict[str, Any]:
    return build_manual_graph(
        notebook_id="nb",
        page_id="p",
        revision=1,
        seq=2,
        visible_hash="a" * 64,
        exercise_ref="x@1",
        steps=list(steps),
        processed_at="2026-11-04T12:00:00Z",
    )


def test_manual_graph_has_no_invented_evidence() -> None:
    graph = graph_of("3 + 8", "11")
    assert graph["version"] == 2
    assert graph["producer"]["kind"] == "manual_transcription"
    for node in graph["nodes"]:
        assert node["stroke_ids"] == []
        assert node["bbox"] is None
        assert all(candidate["confidence"] is None for candidate in node["candidates"])
    assert all(edge["confidence"] is None for edge in graph["edges"])
    assert confirmed_steps(graph) == [("step-1", "3 + 8"), ("step-2", "11")]


def test_the_graph_never_holds_the_expected_answer() -> None:
    graph = graph_of("3 + 8")
    assert "expected" not in str(graph)
    assert "11" not in str(graph["nodes"])


def test_grading_reads_steps_from_the_graph_and_results_meet_the_contract() -> None:
    assessment, solution, steps = grade_graph(graph_of("3 + 8", "= 11"), exercise(ORDER))
    assert assessment.score == 2
    assert solution["uncertainty"] == {"recognition": None, "mathematical": None}
    assert solution["source_node_ids"] == ["step-1", "step-2"]
    assert solution["step_ref"] is None
    assert [step["step_ref"] for step in steps] == ["step-1", "step-2"]
    assert all(step["score"] is None for step in steps)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda g: g.update(version=1),
        lambda g: g["producer"].update(kind="recogniser"),
        lambda g: g["nodes"][2].update(stroke_ids=["s1"]),
        lambda g: g["nodes"][2].update(bbox=[1, 2, 3, 4]),
        lambda g: g["nodes"][2].update(layer="student"),
        lambda g: g["nodes"][2]["candidates"][0].update(
            confidence={"value": 1, "calibrated": False, "calibration_id": None}
        ),
    ],
)
def test_graphs_that_are_not_honestly_manual_are_refused(mutate: Any) -> None:
    graph = graph_of("3 + 8", "11")
    mutate(graph)
    with pytest.raises(GraphRefused):
        confirmed_steps(graph)


def test_a_looping_step_order_is_refused_and_does_not_hang() -> None:
    graph = graph_of("1", "2", "3")
    graph["edges"].append(
        {
            "id": "loop",
            "type": "FOLLOWS_STEP",
            "from": "step-2",
            "to": "step-3",
            "confidence": None,
            "hypothesis_group": None,
        }
    )
    with pytest.raises(GraphRefused):
        confirmed_steps(graph)
