"""Allowlisted grammar, parsed by recursive descent. Input is never evaluated as code.

    expression := term (("+" | "-") term)*
    term       := factor (("×" | "÷" | "/") factor)*
    factor     := [("+" | "-")] primary
    primary    := number | "(" expression ")"
    number     := integer | decimal | integer "/" integer | integer " " integer "/" integer

Takes text that has been through `normalize`. Fails with `ParseFailure`, and never repairs an
expression into something that merely looks valid.
"""

from dataclasses import dataclass
from typing import NoReturn

from .errors import limit_exceeded, undetermined, unsupported
from .limits import DEFAULT_LIMITS, Limits
from .nodes import Binary, DecLit, FracLit, Group, IntLit, MixedLit, Node, Unary, unsigned
from .normalize import ASCII_DIGITS, VULGAR_FRACTIONS

OPERATORS = frozenset("+-×÷/()")
KNOWN_UNSUPPORTED_OPERATORS = frozenset("^%√²³:<>!")
AMBIGUOUS_SEPARATORS = frozenset(",·⋅")


@dataclass(frozen=True)
class Token:
    kind: str  # "int", "decimal" or the operator character.
    text: str
    space_before: bool


def tokenize(text: str, limits: Limits = DEFAULT_LIMITS) -> list[Token]:
    if len(text.encode("utf-8", "surrogatepass")) > limits.max_expression_bytes:
        raise limit_exceeded("max_expression_bytes")
    tokens: list[Token] = []
    position = 0
    space = False
    while position < len(text):
        char = text[position]
        if char == " ":
            space = True
            position += 1
            continue
        if char in ASCII_DIGITS or char == ".":
            token, position = _read_number(text, position, space, limits)
        elif char in OPERATORS:
            token = Token(char, char, space)
            position += 1
        else:
            _refuse(text, position, tokens)
        tokens.append(token)
        if len(tokens) > limits.max_tokens:
            raise limit_exceeded("max_tokens")
        space = False
    return tokens


def _read_number(text: str, start: int, space: bool, limits: Limits) -> tuple[Token, int]:
    end = start
    while end < len(text) and (text[end] in ASCII_DIGITS or text[end] == "."):
        end += 1
    raw = text[start:end]
    whole, dot, fraction = raw.partition(".")
    if dot and (not whole or not fraction or "." in fraction):
        raise undetermined("AMBIGUOUS_NUMBER_FORMAT")  # `.5`, `5.` or `1.2.3`
    if len(whole) + len(fraction) > limits.max_literal_digits:
        raise limit_exceeded("max_literal_digits")
    return Token("decimal" if dot else "int", raw, space), end


def _refuse(text: str, position: int, tokens: list[Token]) -> NoReturn:
    char = text[position]
    if char in AMBIGUOUS_SEPARATORS or char in VULGAR_FRACTIONS:
        raise undetermined("AMBIGUOUS_NUMBER_FORMAT")
    if char in KNOWN_UNSUPPORTED_OPERATORS:
        raise unsupported("UNSUPPORTED_OPERATOR")
    stands_alone = not text[position + 1 : position + 2].isalpha()
    follows_operand = bool(tokens) and tokens[-1].kind in {"int", "decimal", ")"}
    if char in "xX" and stands_alone and follows_operand:
        raise undetermined("AMBIGUOUS_MULTIPLY_X")  # `3 x 4` could be a times sign or a letter.
    raise unsupported("UNSUPPORTED_SYMBOL")


class _Parser:
    def __init__(self, tokens: list[Token], limits: Limits) -> None:
        self.tokens = tokens
        self.limits = limits
        self.position = 0
        self.operations = 0

    def parse(self) -> Node:
        if not self.tokens:
            raise undetermined("EMPTY_EXPRESSION")
        node = self.expression(depth=0)
        if self.peek() is not None:
            # Only an unmatched closing bracket can stop the expression here.
            raise undetermined("INCOMPLETE_EXPRESSION")
        return node

    def peek(self) -> Token | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def advance(self) -> Token:
        token = self.tokens[self.position]
        self.position += 1
        return token

    def spend(self) -> None:
        self.operations += 1
        if self.operations > self.limits.max_operations:
            raise limit_exceeded("max_operations")

    def expression(self, depth: int) -> Node:
        if depth > self.limits.max_depth:
            raise limit_exceeded("max_depth")
        node = self.term(depth)
        while (token := self.peek()) is not None and token.kind in {"+", "-"}:
            self.advance()
            self.spend()
            node = Binary(token.kind, node, self.term(depth))
        return node

    def term(self, depth: int) -> Node:
        node = self.factor(depth)
        # Whether a following slash would chain onto a division already read.
        after_division = isinstance(unsigned(node), FracLit)
        while (token := self.peek()) is not None and token.kind in {"×", "÷", "/"}:
            self.advance()
            self.spend()
            if token.kind == "/" and after_division:
                raise undetermined("AMBIGUOUS_FRACTION_CHAIN")  # `1/2/3` reads two ways.
            right = self.factor(depth)
            if token.kind in {"÷", "/"} and isinstance(unsigned(right), FracLit):
                raise undetermined("AMBIGUOUS_FRACTION_CHAIN")  # So do `6÷2/3` and `(1+1)/2/3`.
            node = Binary(token.kind, node, right)
            after_division = token.kind in {"÷", "/"} or isinstance(unsigned(right), FracLit)
        return node

    def factor(self, depth: int) -> Node:
        token = self.peek()
        if token is None or token.kind not in {"+", "-"}:
            return self.primary(depth)
        self.advance()
        self.spend()
        following = self.peek()
        if following is not None and following.kind in {"+", "-"}:
            raise undetermined("AMBIGUOUS_REPEATED_SIGN")
        return Unary(token.kind, self.primary(depth))

    def primary(self, depth: int) -> Node:
        token = self.peek()
        if token is None:
            raise undetermined("INCOMPLETE_EXPRESSION")
        if token.kind == "(":
            self.advance()
            inner = self.expression(depth + 1)
            closing = self.peek()
            if closing is None or closing.kind != ")":
                raise undetermined("INCOMPLETE_EXPRESSION")
            self.advance()
            self.refuse_implied_multiplication()
            return Group(inner)
        if token.kind == "decimal":
            self.advance()
            self.refuse_implied_multiplication()
            return DecLit(token.text)
        if token.kind == "int":
            return self.integer_or_fraction()
        raise undetermined("INCOMPLETE_EXPRESSION")  # An operator where a number should be.

    def integer_or_fraction(self) -> Node:
        first = self.advance()
        if self.kinds_ahead(2) == ["/", "int"]:
            self.advance()
            denominator = self.advance().text
            self.refuse_after_literal()
            return FracLit(first.text, denominator)
        following = self.peek()
        if (
            following is not None
            and following.space_before
            and self.kinds_ahead(3) == ["int", "/", "int"]
        ):
            numerator = self.advance().text
            self.advance()
            denominator = self.advance().text
            if int(denominator) != 0 and int(numerator) >= int(denominator):
                raise undetermined("AMBIGUOUS_MIXED_NUMBER")  # `1 3/2` is not a mixed number.
            self.refuse_after_literal()
            return MixedLit(first.text, numerator, denominator)
        self.refuse_implied_multiplication()
        return IntLit(first.text)

    def kinds_ahead(self, count: int) -> list[str]:
        return [token.kind for token in self.tokens[self.position : self.position + count]]

    def refuse_after_literal(self) -> None:
        following = self.peek()
        if following is not None and following.kind == "/":
            raise undetermined("AMBIGUOUS_FRACTION_CHAIN")
        self.refuse_implied_multiplication()

    def refuse_implied_multiplication(self) -> None:
        following = self.peek()
        if following is not None and following.kind in {"int", "decimal", "("}:
            raise undetermined("MISSING_OPERATOR")  # `2 3`, `2(3)`, `(2)3`: nothing is assumed.


def parse_expression(text: str, limits: Limits = DEFAULT_LIMITS) -> Node:
    """Parses one side of a step. Raises `ParseFailure`; the caller decides what that means."""
    return _Parser(tokenize(text, limits), limits).parse()
