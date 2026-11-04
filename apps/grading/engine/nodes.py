"""The written structure of an expression. Nodes are built only by the parser, from valid tokens.

Literals keep their text, so `2/4` stays `2/4` and `1.50` keeps its two places.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IntLit:
    text: str


@dataclass(frozen=True)
class DecLit:
    text: str

    @property
    def places(self) -> int:
        return len(self.text.partition(".")[2])


@dataclass(frozen=True)
class FracLit:
    numerator: str
    denominator: str


@dataclass(frozen=True)
class MixedLit:
    whole: str
    numerator: str
    denominator: str


@dataclass(frozen=True)
class Unary:
    op: str
    operand: "Node"


@dataclass(frozen=True)
class Binary:
    op: str
    left: "Node"
    right: "Node"


@dataclass(frozen=True)
class Group:
    inner: "Node"


Node = IntLit | DecLit | FracLit | MixedLit | Unary | Binary | Group


def unsigned(node: Node) -> Node:
    return node.operand if isinstance(node, Unary) else node


def is_literal(node: Node) -> bool:
    """A number as written, with at most one sign. Brackets or operators make it an expression."""
    return isinstance(unsigned(node), IntLit | DecLit | FracLit | MixedLit)


def count_binary(node: Node) -> int:
    if isinstance(node, Binary):
        return 1 + count_binary(node.left) + count_binary(node.right)
    if isinstance(node, Unary):
        return count_binary(node.operand)
    if isinstance(node, Group):
        return count_binary(node.inner)
    return 0


def render(node: Node) -> str:
    """The normalised form. It never simplifies, so what was written stays visible."""
    if isinstance(node, IntLit | DecLit):
        return node.text
    if isinstance(node, FracLit):
        return f"{node.numerator}/{node.denominator}"
    if isinstance(node, MixedLit):
        return f"{node.whole} {node.numerator}/{node.denominator}"
    if isinstance(node, Unary):
        return f"{node.op}{render(node.operand)}"
    if isinstance(node, Group):
        return f"({render(node.inner)})"
    return f"{render(node.left)} {node.op} {render(node.right)}"


def to_dict(node: Node) -> dict[str, Any]:
    if isinstance(node, IntLit):
        return {"t": "int", "text": node.text}
    if isinstance(node, DecLit):
        return {"t": "decimal", "text": node.text}
    if isinstance(node, FracLit):
        return {"t": "fraction", "n": node.numerator, "d": node.denominator}
    if isinstance(node, MixedLit):
        return {"t": "mixed", "w": node.whole, "n": node.numerator, "d": node.denominator}
    if isinstance(node, Unary):
        return {"t": "unary", "op": node.op, "x": to_dict(node.operand)}
    if isinstance(node, Group):
        return {"t": "group", "x": to_dict(node.inner)}
    return {"t": "binary", "op": node.op, "l": to_dict(node.left), "r": to_dict(node.right)}
