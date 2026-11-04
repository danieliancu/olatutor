"""Written form, judged from the tree and never from the value alone."""

from math import gcd

from .nodes import DecLit, FracLit, IntLit, MixedLit, Node, is_literal, unsigned

IMPLEMENTED_FORMATS = frozenset(
    {"any", "integer", "lowest_terms", "mixed_number", "decimal_places"}
)


def meets_required_format(node: Node, required: str, places: int | None) -> bool:
    if not is_literal(node):
        return False
    literal = unsigned(node)
    if required == "any":
        return True
    if required == "integer":
        return isinstance(literal, IntLit)
    if required == "lowest_terms":
        return _in_lowest_terms(literal)
    if required == "mixed_number":
        return isinstance(literal, IntLit) or (isinstance(literal, MixedLit) and _lowest(literal))
    if required == "decimal_places":
        return isinstance(literal, DecLit) and places is not None and literal.places == places
    raise ValueError(f"format not implemented: {required}")


def _in_lowest_terms(literal: Node) -> bool:
    if isinstance(literal, IntLit):
        return True
    return isinstance(literal, FracLit | MixedLit) and _lowest(literal)


def _lowest(literal: FracLit | MixedLit) -> bool:
    return gcd(int(literal.numerator), int(literal.denominator)) == 1
