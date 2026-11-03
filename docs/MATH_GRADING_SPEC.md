# Mathematical grading specification, version 1

Status: **contract only, not implemented.** Schema and fixtures: `contracts/grading/v1/`. The parser, SymPy grading and StepValidationEngine are Milestone 4. The examples in the fixtures are the acceptance cases that implementation must pass.

## Responsibilities stay separate

1. **Recognition:** what did the child write?
2. **Parsing:** what mathematical expression does that represent?
3. **Grading:** is it correct under the exercise's contract?
4. **Pedagogical feedback:** what should the child learn next?

These never collapse into one LLM call.

## Two independent axes, two uncertainties

- `mathematical_status`: CORRECT, INCORRECT, INCOMPLETE, UNSUPPORTED, UNDETERMINED.
- `task_compliance`: COMPLIANT, NON_COMPLIANT, NOT_EVALUATED. For "Simplify 2/4", the answer `2/4` is mathematically correct but non-compliant.
- `uncertainty.recognition` and `uncertainty.mathematical` are separate. A single confidence value is rejected by the schema.

## Grading contract

Every exercise category defines:

- exercise type
- variable domains, with excluded values
- assumptions
- expected result (value, expression or complete solution set)
- accepted forms and required format
- rounding and unit rules
- valid and invalid transformations
- alternative-method policy
- partial-credit rules
- unsupported cases
- worked examples

Seed fixtures:

| Fixture | What it pins down |
|---|---|
| `contract_simplify_fraction` | Value equivalence versus the simplification requirement |
| `contract_quadratic_roots` | One root of x² = 9 is INCOMPLETE; an extraneous root is INCORRECT |
| `contract_rational_domain` | x + 1 equals (x² − 1)/(x − 1) only with x ≠ 1 retained |
| `contract_rounding_units` | Rounding, unit error, and unit conversion as unsupported |

These categories are examples for the contract's shape. KS2 coverage comes first, and algebra only after benchmarks justify it.

## Uncertainty is never "wrong"

Enforced on fixtures by `scripts/validate_contracts.py`:

- Unreadable work must not be INCORRECT (`UNCERTAINTY_IS_NOT_WRONG`).
- UNSUPPORTED or UNDETERMINED work has no score (`UNDETERMINED_HAS_NO_SCORE`) and must require review (`REVIEW_REQUIRED`).
- A compliant verdict needs mathematically correct work.

## Parser requirements for Milestone 4

- An allowlisted grammar (Lark or equivalent). SymPy objects are built from validated parser nodes. `eval`, `exec`, `sympify` and `parse_expr` are never given student input.
- Limits apply before any evaluation: input length, AST depth, integer and exponent magnitude, number of operations and symbols.
- Exact types: `Fraction` and `Decimal`, never float, for arithmetic.
- Expensive symbolic work runs under process isolation with time and memory limits. An application-level timeout alone is not enough, because it cannot stop an exhausted worker.

## Step validation for Milestone 4

The StepValidationEngine must distinguish: equivalence, implication, valid transformation, incomplete reasoning, unjustified transformation, arithmetic error, domain violation and unsupported method. It supports legitimate alternative methods, and returns review-required rather than guessing outside declared categories.

## Grading output

Every result pins the page revision and hash, and carries exercise, solution and step references, both statuses, error class, both uncertainties, score, grading version, explanation code, review flag and source semantic node IDs. Results are immutable. A parent's override will be a separate record that preserves the original.
