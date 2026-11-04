"""The execution budget. Every limit also applies to exercise contracts. See ADR 0005."""

from dataclasses import dataclass

from .errors import limit_exceeded


@dataclass(frozen=True)
class Limits:
    max_expression_bytes: int = 512
    max_step_bytes: int = 2048
    max_tokens: int = 128
    max_depth: int = 24
    max_operations: int = 64
    max_literal_digits: int = 18
    max_value_bits: int = 2048
    max_steps: int = 30
    max_expressions_per_step: int = 8
    max_operations_total: int = 512


DEFAULT_LIMITS = Limits()


class Budget:
    """Counts the operations spent on one verification, across all of its steps."""

    def __init__(self, limits: Limits = DEFAULT_LIMITS) -> None:
        self.limits = limits
        self.operations = 0

    def spend(self, operations: int = 1) -> None:
        self.operations += operations
        if self.operations > self.limits.max_operations_total:
            raise limit_exceeded("max_operations_total")
