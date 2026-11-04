# Mathematical grading specification, version 1

Status: **implemented for arithmetic only (Milestone 4A), on manually confirmed input.** Schema and fixtures: `contracts/grading/v1/`. Engine: `apps/grading/engine/`. Scope: [MATH_SUPPORT_MATRIX_4A.md](MATH_SUPPORT_MATRIX_4A.md). Symbolic grading and full step validation stay in the rest of Milestone 4, and the fixture examples outside 4A stay as acceptance cases for it.

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

- An allowlisted grammar. Milestone 4A uses a hand-written parser and no SymPy (ADR 0005). If SymPy is added, its objects are built from validated parser nodes. `eval`, `exec`, `sympify` and `parse_expr` are never given student input.
- Limits apply before any evaluation: input length, AST depth, integer and exponent magnitude, number of operations and symbols.
- Exact types: `Fraction` and `Decimal`, never float, for arithmetic.
- Expensive symbolic work runs under process isolation with time and memory limits. An application-level timeout alone is not enough, because it cannot stop an exhausted worker.

## Step validation for Milestone 4

For all of Milestone 4, step validation must distinguish: equivalence, implication, valid transformation, incomplete reasoning, unjustified transformation, arithmetic error, domain violation and unsupported method. It supports legitimate alternative methods, and returns review-required rather than guessing outside declared categories.

Milestone 4A implements the arithmetic part: exact value equivalence, arithmetic error, changed value, domain violation, incomplete reasoning and unsupported input. Implication and unjustified transformation are not implemented, because equal value cannot show them.

## Grading output

Every result pins the page revision and hash, and carries exercise, solution and step references, both statuses, error class, both uncertainties, score, grading version, explanation code, review flag and source semantic node IDs. Results are immutable. A parent's override will be a separate record that preserves the original.

## What Milestone 4A implements

**Layers.** `normalize`, `parser` and `nodes` (reading); `evaluate` and `rounding` (exact values); `forms` and `exercise` (exercise rules); `steps` (is each line justified?); `grade` (is the solution complete and correct?); `scoring`; `feedback`; then, outside the engine, `semantics` (the manual graph), `results` (the contract), and `services` and `views` (persistence and HTTP).

**The two questions.** Step results answer "is this line justified by the exercise and the work before it?", and never carry a score. The solution result answers "is the work complete, and the final answer correct?", and carries the score.

**A link** joins neighbouring expressions: `=` or `≈` on a line, or one line and the next. The first expression links to the exercise's start. Links are judged on exact values, so any valid method passes and no text is compared.

**Order of decision for the solution**, first match wins:

| # | Condition | Status / compliance / class | Score |
|---|---|---|---|
| 1 | Over a budget limit | UNDETERMINED / NOT_EVALUATED / none | None |
| 2 | A line uses something outside the scope | UNSUPPORTED / NOT_EVALUATED / UNSUPPORTED_METHOD | None |
| 3 | A line is empty, unfinished or ambiguous | UNDETERMINED / NOT_EVALUATED / none | None |
| 4 | A link is broken or undefined | INCORRECT / NOT_EVALUATED / by evidence (`PEDAGOGY_SPEC.md`) | 0 |
| 5 | The last line still has a calculation in it | INCOMPLETE / NON_COMPLIANT / INCOMPLETE_REASONING | By declared rule, else 0 |
| 6 | Rounding exercise: exact value, not rounded | CORRECT / NON_COMPLIANT / FORMAT_REQUIREMENT | By declared rule, else 0 |
| 7 | Rounding exercise: rounded to the wrong value | INCORRECT / NOT_EVALUATED / ROUNDING_ERROR | 0 |
| 8 | Working required, and only the question and answer appear | INCOMPLETE / NON_COMPLIANT / INCOMPLETE_REASONING | By declared rule, else 0 |
| 9 | Right value, wrong form | CORRECT / NON_COMPLIANT / FORMAT_REQUIREMENT | By declared rule, else 0 |
| 10 | Otherwise | CORRECT / COMPLIANT / none | Maximum |

A right final value does not rescue a broken link (row 4). An unreadable line stops any verdict (rows 2 and 3), even when the final answer looks right.

**Rounding links.** In a rounding exercise only, a link to a decimal is accepted, with `=` or `≈`, when it is the previous value correctly rounded half-up to the places written, or to the places asked, with at least the places asked.

**Uncertainty.** `uncertainty.recognition` is null because no recogniser ran, so nothing was measured. `uncertainty.mathematical` is null because the engine decides exactly or says UNSUPPORTED or UNDETERMINED. Neither null means "certain". No confidence value is ever invented.

**Exercises.** `apps/grading/exercises/catalog_v1.json` wraps unchanged v1 contracts, using `contracts/grading/v1/exercise_catalog.schema.json`, with a start expression and whether working is required. Only the server's copy counts. A contract asking for anything not implemented fails at load.

**Provenance and records.** Grading reads only a Page Semantics v2 graph with manual provenance (ADR 0006). Each `Verification` stores its notebook and page, `PageRevision`, exercise and version, transcription, semantic version, engine and rules versions, and results. Records are append-only by database trigger, and a correction is a new row pointing to the one before. The unique key is `(page, idempotency_key)`. The same key and payload return the original record, and the same key with another payload gets 409 `IDEMPOTENCY_MISMATCH`.

**Current page.** A result is linked to its revision. `is_current_page_state` is true only while the page's journal is still at that revision. Older results stay in the history, and are never shown as a verdict on later ink.
