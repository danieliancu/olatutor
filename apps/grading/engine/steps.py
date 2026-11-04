"""Step validation: is each written link justified by the exercise and the work before it?

This answers only that question. Whether the solution is complete and final is decided in `grade`.

A link joins two neighbouring expressions: `=` or `≈` inside a line, or one line and the next.
The first expression links to the exercise's start. Links are judged on exact values, so any valid
method passes and no text is compared. Equal value shows the value was kept, not how the writer
reasoned.

Interface for later: `check_link` is the only place that decides a link. Other kinds of work, such
as algebra, would add a checker there. Nothing in this package attempts that now.
"""

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Any

from .errors import FailureKind, ParseFailure, UndefinedValue, limit_exceeded, undetermined
from .evaluate import evaluate
from .exercise import Exercise
from .limits import Budget
from .nodes import Binary, DecLit, Node, count_binary, is_literal, render, to_dict, unsigned
from .normalize import normalize
from .parser import parse_expression
from .rounding import round_half_up, truncate


class LinkVerdict(StrEnum):
    VALUE_KEPT = "VALUE_KEPT"
    ROUNDED = "ROUNDED"
    VALUE_CHANGED = "VALUE_CHANGED"
    UNDEFINED = "UNDEFINED"
    NOT_CHECKED = "NOT_CHECKED"


@dataclass(frozen=True)
class Expression:
    """One side of a step: its text, its normal form, its written tree and, if known, its value."""

    text: str
    normalized: str | None
    node: Node | None
    value: Fraction | None
    undefined: bool
    failure: ParseFailure | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "normalized": self.normalized,
            "structure": to_dict(self.node) if self.node is not None else None,
            "value": _fraction_text(self.value),
            "undefined": self.undefined,
            "failure": self.failure.code if self.failure else None,
        }


def _fraction_text(value: Fraction | None) -> str | None:
    return None if value is None else f"{value.numerator}/{value.denominator}"


@dataclass(frozen=True)
class Link:
    verdict: LinkVerdict
    explicit: bool
    approximate: bool
    error_class: str | None
    code: str


@dataclass(frozen=True)
class Step:
    index: int
    text: str
    expressions: tuple[Expression, ...]
    links: tuple[Link, ...]
    failure: ParseFailure | None
    follows_earlier_error: bool

    @property
    def problem_link(self) -> Link | None:
        for link in self.links:
            if link.verdict in {LinkVerdict.VALUE_CHANGED, LinkVerdict.UNDEFINED}:
                return link
        return None


def read_expression(text: str, exercise: Exercise, budget: Budget) -> Expression:
    normalized: str | None = None
    node: Node | None = None
    try:
        normalized_text = normalize(text)
        node = parse_expression(normalized_text, exercise.limits)
        normalized = render(node)
        return Expression(text, normalized, node, evaluate(node, budget), False, None)
    except UndefinedValue:
        return Expression(text, normalized, node, None, True, None)
    except ParseFailure as failure:
        return Expression(text, normalized, node, None, False, failure)


def _classify_change(left: Node, right: Node, explicit: bool) -> str | None:
    """Names a cause only with evidence. See the table in docs/PEDAGOGY_SPEC.md."""
    if is_literal(right):
        left_inner = unsigned(left)
        if is_literal(left):
            return "ARITHMETIC_ERROR"  # One written value rewritten as a different one.
        one_operation = (
            isinstance(left_inner, Binary)
            and is_literal(left_inner.left)
            and is_literal(left_inner.right)
        )
        if one_operation:
            return "ARITHMETIC_ERROR"  # `3 + 8 = 12`: one operation with a wrong result.
        if not explicit and count_binary(left) > 1:
            return None  # A bare answer to a longer sum: wrong, with no evidence of why.
    return "INVALID_TRANSFORMATION"  # Two written forms with demonstrably different values.


def _rounding_link(left: Fraction, right: Expression, places: int) -> Link | None:
    """Rounded values are allowed only in a rounding exercise, and only to a decimal."""
    node = right.node
    if node is None or not isinstance(unsigned(node), DecLit):
        return None
    written = unsigned(node)
    assert isinstance(written, DecLit)
    # `2.33` and `2.333` are rounded forms of 7/3 to 2 places or more. So is `2.330`, by its value.
    keeps_enough_places = written.places >= places
    rounded_as_written = right.value == round_half_up(left, written.places)
    rounded_as_asked = right.value == round_half_up(left, places)
    if keeps_enough_places and (rounded_as_written or rounded_as_asked):
        return Link(LinkVerdict.ROUNDED, True, True, None, "STEP_ROUNDED")
    wrong_places = written.places != places and right.value == round_half_up(left, written.places)
    truncated = right.value == truncate(left, written.places)
    if wrong_places or truncated:
        return Link(LinkVerdict.VALUE_CHANGED, True, True, "ROUNDING_ERROR", "ROUNDING_WRONG")
    return None


def check_link(
    left: Expression, right: Expression, explicit: bool, approximate: bool, exercise: Exercise
) -> Link:
    if right.undefined:
        return Link(
            LinkVerdict.UNDEFINED, explicit, approximate, "DOMAIN_VIOLATION", "DIVISION_BY_ZERO"
        )
    if left.value is None or right.value is None or left.node is None or right.node is None:
        return Link(LinkVerdict.NOT_CHECKED, explicit, approximate, None, "STEP_NOT_CHECKED")
    if left.value == right.value:
        return Link(LinkVerdict.VALUE_KEPT, explicit, approximate, None, "STEP_VALUE_KEPT")
    if exercise.rounding_places is not None:
        rounded = _rounding_link(left.value, right, exercise.rounding_places)
        if rounded is not None:
            return Link(rounded.verdict, explicit, approximate, rounded.error_class, rounded.code)
    error_class = _classify_change(left.node, right.node, explicit)
    if error_class == "ARITHMETIC_ERROR":
        code = "STEP_VALUE_CHANGED"
    elif error_class == "INVALID_TRANSFORMATION":
        code = "TRANSFORMATION_CHANGED_VALUE"
    else:
        code = "ANSWER_VALUE_MISMATCH"
    return Link(LinkVerdict.VALUE_CHANGED, explicit, approximate, error_class, code)


def _split_chain(text: str) -> tuple[list[str], list[bool]]:
    """Splits a line at `=` and `≈`. Returns the sides, and whether each join is approximate."""
    sides: list[str] = []
    approximate: list[bool] = []
    current: list[str] = []
    for char in text:
        if char in {"=", "≈"}:
            sides.append("".join(current))
            approximate.append(char == "≈")
            current = []
        else:
            current.append(char)
    sides.append("".join(current))
    return sides, approximate


def validate_steps(
    texts: list[str], exercise: Exercise, budget: Budget
) -> tuple[list[Step], Expression]:
    """Returns one verdict per line, and the expression standing before the first line."""
    limits = exercise.limits
    start = Expression(
        exercise.start_text,
        render(exercise.start),
        exercise.start,
        exercise.start_value,
        False,
        None,
    )
    previous = start
    steps: list[Step] = []
    seen_error = False

    for index, text in enumerate(texts):
        if len(text.encode("utf-8", "surrogatepass")) > limits.max_step_bytes:
            raise limit_exceeded("max_step_bytes")
        sides, joins = _split_chain(text)
        if len(sides) > limits.max_expressions_per_step:
            raise limit_exceeded("max_expressions_per_step")

        continues_previous = len(sides) > 1 and not sides[0].strip()
        if continues_previous:
            # A leading `=` continues from the previous line, so the empty side is not a gap.
            sides = sides[1:]
        approximate_outside_rounding = any(joins) and exercise.rounding_places is None

        expressions = []
        links = []
        failure: ParseFailure | None = None
        follows_error = seen_error
        for position, side in enumerate(sides):
            expression = read_expression(side, exercise, budget)
            if expression.failure is not None:
                if expression.failure.kind is FailureKind.LIMIT:
                    raise expression.failure
                failure = failure or _empty_side_as_unfinished(expression.failure, len(sides))
            if position == 0:
                explicit = continues_previous
                approximate = continues_previous and joins[0]
            else:
                explicit = True
                approximate = joins[position - (0 if continues_previous else 1)]
            link = check_link(previous, expression, explicit, approximate, exercise)
            links.append(link)
            expressions.append(expression)
            previous = expression

        if failure is None and approximate_outside_rounding:
            failure = ParseFailure(FailureKind.UNSUPPORTED, "APPROX_NOT_SUPPORTED")
        step = Step(index, text, tuple(expressions), tuple(links), failure, follows_error)
        if step.problem_link is not None:
            seen_error = True
        steps.append(step)
    return steps, start


def _empty_side_as_unfinished(failure: ParseFailure, sides: int) -> ParseFailure:
    # `3 + 4 =` has an empty side: the line is unfinished, not an empty answer.
    if failure.code == "EMPTY_EXPRESSION" and sides > 1:
        return undetermined("INCOMPLETE_EXPRESSION")
    return failure
