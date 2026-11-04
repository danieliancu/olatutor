"""Why an expression could not be read. None of these is a mathematical mistake by the writer."""

from enum import StrEnum


class FailureKind(StrEnum):
    UNDETERMINED = "UNDETERMINED"  # Empty, unfinished or ambiguous: ask, never guess.
    UNSUPPORTED = "UNSUPPORTED"  # Readable as something, but outside the declared scope.
    LIMIT = "LIMIT"  # Over the execution budget.


class ParseFailure(Exception):
    def __init__(self, kind: FailureKind, code: str, limit: str | None = None) -> None:
        super().__init__(code)
        self.kind = kind
        self.code = code
        self.limit = limit


def undetermined(code: str) -> ParseFailure:
    return ParseFailure(FailureKind.UNDETERMINED, code)


def unsupported(code: str) -> ParseFailure:
    return ParseFailure(FailureKind.UNSUPPORTED, code)


def limit_exceeded(limit: str) -> ParseFailure:
    return ParseFailure(FailureKind.LIMIT, "RESOURCE_LIMIT_EXCEEDED", limit)


class UndefinedValue(Exception):
    """The expression is well formed, and undefined because it divides by zero."""
