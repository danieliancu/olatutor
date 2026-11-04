"""Scoring. Marks come only from a declared rule, and never from counting steps.

UNSUPPORTED and UNDETERMINED have no score at all: they are not given zero.
"""

RULE_NOT_LOWEST_TERMS = "value equal but not in lowest terms"
RULE_WRONG_FORM = "value equal but not in the required form"
RULE_NO_FINAL_VALUE = "valid steps but no final value"
RULE_STEPS_MISSING = "correct value but the required steps are missing"

PARTIAL_CREDIT_RULES = frozenset(
    {RULE_NOT_LOWEST_TERMS, RULE_WRONG_FORM, RULE_NO_FINAL_VALUE, RULE_STEPS_MISSING}
)


def partial_score(partial_credit: dict[str, int], rule: str) -> int:
    """A rule the exercise did not declare earns nothing."""
    return partial_credit.get(rule, 0)
