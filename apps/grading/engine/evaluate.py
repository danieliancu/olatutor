"""Exact evaluation with `Fraction`. No float is involved in any value."""

from fractions import Fraction

from .errors import UndefinedValue, limit_exceeded
from .limits import Budget
from .nodes import DecLit, FracLit, Group, IntLit, MixedLit, Node, Unary


def evaluate(node: Node, budget: Budget | None = None) -> Fraction:
    """Raises `UndefinedValue` on division by zero, and `ParseFailure` when over budget."""
    return _evaluate(node, budget or Budget())


def _checked(value: Fraction, budget: Budget) -> Fraction:
    limit = budget.limits.max_value_bits
    if value.numerator.bit_length() > limit or value.denominator.bit_length() > limit:
        raise limit_exceeded("max_value_bits")
    return value


def _fraction(numerator: str, denominator: str) -> Fraction:
    if int(denominator) == 0:
        raise UndefinedValue
    return Fraction(int(numerator), int(denominator))


def _evaluate(node: Node, budget: Budget) -> Fraction:
    if isinstance(node, IntLit):
        return Fraction(int(node.text))
    if isinstance(node, DecLit):
        whole, _, places = node.text.partition(".")
        return Fraction(int(whole + places), 10 ** len(places))
    if isinstance(node, FracLit):
        return _fraction(node.numerator, node.denominator)
    if isinstance(node, MixedLit):
        return int(node.whole) + _fraction(node.numerator, node.denominator)
    if isinstance(node, Group):
        return _evaluate(node.inner, budget)
    budget.spend()
    if isinstance(node, Unary):
        value = _evaluate(node.operand, budget)
        return -value if node.op == "-" else value
    left = _evaluate(node.left, budget)
    right = _evaluate(node.right, budget)
    if node.op == "+":
        return _checked(left + right, budget)
    if node.op == "-":
        return _checked(left - right, budget)
    if node.op == "×":
        return _checked(left * right, budget)
    if right == 0:
        raise UndefinedValue
    return _checked(left / right, budget)
