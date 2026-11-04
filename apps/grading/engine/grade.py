"""Answers the second question: is the solution complete, and its final answer correct?

Takes confirmed step texts and an exercise. It sees no ink, no geometry and no recogniser output.
The order of the checks below is the policy, and it is documented in docs/MATH_GRADING_SPEC.md.
"""

from dataclasses import dataclass
from typing import Any

from .errors import FailureKind, ParseFailure, limit_exceeded
from .exercise import Exercise
from .forms import meets_required_format
from .limits import Budget
from .nodes import FracLit, MixedLit, is_literal, render, unsigned
from .scoring import (
    RULE_NO_FINAL_VALUE,
    RULE_NOT_LOWEST_TERMS,
    RULE_STEPS_MISSING,
    RULE_WRONG_FORM,
    partial_score,
)
from .steps import Link, LinkVerdict, Step, validate_steps

INCORRECT = "INCORRECT"
CORRECT = "CORRECT"
INCOMPLETE = "INCOMPLETE"
UNSUPPORTED = "UNSUPPORTED"
UNDETERMINED = "UNDETERMINED"
COMPLIANT = "COMPLIANT"
NON_COMPLIANT = "NON_COMPLIANT"
NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class StepVerdict:
    index: int
    mathematical_status: str
    error_class: str | None
    code: str
    requires_review: bool
    follows_earlier_error: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "mathematical_status": self.mathematical_status,
            "error_class": self.error_class,
            "code": self.code,
            "requires_review": self.requires_review,
            "follows_earlier_error": self.follows_earlier_error,
        }


@dataclass(frozen=True)
class Assessment:
    mathematical_status: str
    task_compliance: str
    error_class: str | None
    score: int | None
    max_score: int
    code: str
    requires_review: bool
    step_verdicts: tuple[StepVerdict, ...]
    steps: tuple[Step, ...]
    limit: str | None = None

    @property
    def focus_line(self) -> int | None:
        """The 1-based line the feedback is about, if a particular line is at fault."""
        for verdict in self.step_verdicts:
            if verdict.mathematical_status in {INCORRECT, UNSUPPORTED, UNDETERMINED}:
                return verdict.index + 1
        return None


def _no_verdict(
    status: str,
    error_class: str | None,
    code: str,
    exercise: Exercise,
    steps: list[Step],
    limit: str | None = None,
) -> Assessment:
    """UNSUPPORTED and UNDETERMINED: no score, no INCORRECT and a request for review."""
    return Assessment(
        status, NOT_EVALUATED, error_class, None, exercise.max_score, code, True,
        tuple(_step_verdict(step) for step in steps), tuple(steps), limit,
    )  # fmt: skip


def _step_verdict(step: Step) -> StepVerdict:
    follows = step.follows_earlier_error
    if step.failure is not None:
        status = UNSUPPORTED if step.failure.kind is FailureKind.UNSUPPORTED else UNDETERMINED
        error = "UNSUPPORTED_METHOD" if status == UNSUPPORTED else None
        return StepVerdict(step.index, status, error, step.failure.code, True, follows)
    problem = step.problem_link
    if problem is not None:
        return StepVerdict(step.index, INCORRECT, problem.error_class, problem.code, False, follows)
    if any(link.verdict is LinkVerdict.NOT_CHECKED for link in step.links):
        return StepVerdict(step.index, UNDETERMINED, None, "STEP_NOT_CHECKED", True, follows)
    code = _last_kept_code(step.links)
    return StepVerdict(step.index, CORRECT, None, code, False, follows)


def _last_kept_code(links: tuple[Link, ...]) -> str:
    return "STEP_ROUNDED" if any(link.verdict is LinkVerdict.ROUNDED for link in links) else (
        "STEP_VALUE_KEPT"
    )  # fmt: skip


def grade_steps(texts: list[str], exercise: Exercise) -> Assessment:
    """Never raises for bad student input. Going over budget returns a controlled result."""
    limits = exercise.limits
    if not texts:
        return _no_verdict(UNDETERMINED, None, "EMPTY_EXPRESSION", exercise, [])
    if len(texts) > limits.max_steps:
        failure = limit_exceeded("max_steps")
        return _no_verdict(UNDETERMINED, None, failure.code, exercise, [], failure.limit)
    try:
        steps, _ = validate_steps(texts, exercise, Budget(limits))
    except ParseFailure as failure:
        # Only budget failures escape `validate_steps`; others are recorded on their own step.
        return _no_verdict(UNDETERMINED, None, failure.code, exercise, [], failure.limit)
    return _decide(steps, exercise)


def _decide(steps: list[Step], exercise: Exercise) -> Assessment:
    failures = [step.failure for step in steps if step.failure is not None]
    for failure in failures:
        if failure.kind is FailureKind.UNSUPPORTED:
            return _no_verdict(UNSUPPORTED, "UNSUPPORTED_METHOD", failure.code, exercise, steps)
    if failures:
        return _no_verdict(UNDETERMINED, None, failures[0].code, exercise, steps)

    verdicts = tuple(_step_verdict(step) for step in steps)
    final = steps[-1].expressions[-1]

    def result(
        status: str, compliance: str, error: str | None, score: int, code: str
    ) -> Assessment:
        return Assessment(
            status,
            compliance,
            error,
            score,
            exercise.max_score,
            code,
            False,
            verdicts,
            tuple(steps),
        )

    problems = [step.problem_link for step in steps if step.problem_link is not None]
    if problems:
        first = problems[0]
        code = first.code
        if final.value == exercise.expected_value and first.verdict is LinkVerdict.VALUE_CHANGED:
            code = "FINAL_RIGHT_AFTER_STEP_ERROR"
        return result(INCORRECT, NOT_EVALUATED, first.error_class, 0, code)

    assert final.node is not None and final.value is not None
    if not is_literal(final.node):
        score = partial_score(exercise.partial_credit, RULE_NO_FINAL_VALUE)
        return result(INCOMPLETE, NON_COMPLIANT, "INCOMPLETE_REASONING", score, "ANSWER_NOT_FINAL")

    if final.value != exercise.expected_value:
        # With every link valid, this can only be a rounding exercise.
        if final.value == exercise.start_value:
            score = partial_score(exercise.partial_credit, RULE_WRONG_FORM)
            return result(
                CORRECT, NON_COMPLIANT, "FORMAT_REQUIREMENT", score, "NOT_ROUNDED_AS_ASKED"
            )
        return result(INCORRECT, NOT_EVALUATED, "ROUNDING_ERROR", 0, "ROUNDING_WRONG")

    # Copying out the question and adding the answer shows no working.
    written = [expression for step in steps for expression in step.expressions]
    working = [item for item in written[:-1] if item.normalized != render(exercise.start)]
    if exercise.steps_required and not working:
        score = partial_score(exercise.partial_credit, RULE_STEPS_MISSING)
        return result(INCOMPLETE, NON_COMPLIANT, "INCOMPLETE_REASONING", score, "STEPS_REQUIRED")

    if not meets_required_format(final.node, exercise.required_format, exercise.rounding_places):
        lowest = exercise.required_format == "lowest_terms"
        rule = RULE_NOT_LOWEST_TERMS if lowest else RULE_WRONG_FORM
        score = partial_score(exercise.partial_credit, rule)
        # The "not simplified" wording is true only of a written fraction, not of `0.5`.
        is_fraction = isinstance(unsigned(final.node), FracLit | MixedLit)
        code = "VALUE_RIGHT_NOT_SIMPLIFIED" if lowest and is_fraction else "VALUE_RIGHT_FORM_WRONG"
        return result(CORRECT, NON_COMPLIANT, "FORMAT_REQUIREMENT", score, code)

    return result(CORRECT, COMPLIANT, None, exercise.max_score, "SOLUTION_COMPLETE")
