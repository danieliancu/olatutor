# Acceptance criteria

Statuses: PASS, PARTIAL, BLOCKED, FAIL, each with evidence. A feature is not complete because a file or class exists. All numeric targets are provisional and require empirical validation; they are not claims about current performance. Evidence for what has been run is in `PROGRESS.md`.

## Provisional product targets

| Area | Target | Measured so far |
|---|---|---|
| Deterministic grading | All approved contract tests pass | Arithmetic only (4A). Unit and algebra fixtures are not implemented: `MATH_SUPPORT_MATRIX_4A.md` |
| Short-answer recognition | At least 95% exact after the specified confirmation | Not implemented |
| Confidently wrong automatic reading | Below 0.5% on representative validation data | Not implemented |
| Simple grading latency | p95 under 1 s on selected server hardware | Engine alone on the development PC: `PROGRESS.md`. Whole requests and server hardware not measured |
| Local recognition latency | p95 under 3 s | Not implemented |
| Stylus visual latency | p95 under 30 ms | Not measured; needs real hardware |
| Cross-tenant security | No unauthorised access in defined tests | Tenancy not implemented |
| Confirmed submissions | No loss in tested recovery scenarios | Ink operations only: see `PROGRESS.md` |

Full-page thresholds are set only after representative benchmark data exists.

## Pre-registered gates for recognition (Milestone 3)

Values are proposals without evidence behind them, and must be fixed before data collection. Method and status rule: `RECOGNITION_EVALUATION.md`.

- Accuracy after confirmation ≥ 95%, raw accuracy ≥ 85%
- Confidently wrong < 0.5%, with coverage reported beside it
- Corrections needed on ≤ 15% of answers
- At least 95% of deliberately seeded errors are caught at confirmation
- Critical-class errors (1↔7, 0↔6, dropped `.` or `-`) reported separately
- p95 end-to-end latency under 3 s, under concurrency, on deployment hardware
- Recognition cannot see the expected answer (tested)
- Failure without loss of the child's work

## Milestone 0

Acceptance: schemas and fixtures validate independently, with no speculative full SaaS. Results in `PROGRESS.md`.

## Milestone 1

The same page can be saved, restored and reproduced without semantic or geometric corruption, including across browser engines, multiple pages and interruptions. Results are in `PROGRESS.md`. Whether real stylus writing is acceptable is outside this criterion and is tracked as hypothesis H1.

## Later milestones

Criteria for Milestones 2, 3 and 5–7, and for the rest of Milestone 4, are in the brief, and are summarised in `ROADMAP.md`. Each must be turned into measurable values here before that milestone starts.

## Milestone 4A: deterministic arithmetic engine and manually confirmed demonstration

Milestone 4A is a stage of Milestone 4, not a renumbering. Passing it does **not** pass Milestone 4, which also needs recognition input, spatially anchored feedback, a real review path and a decision on algebra. These criteria were written before the implementation. Scope and tests per feature: [MATH_SUPPORT_MATRIX_4A.md](MATH_SUPPORT_MATRIX_4A.md).

| # | Criterion | Measurable evidence |
|---|---|---|
| 1 | Safe parsing and exact arithmetic for the declared scope | Allowlisted grammar with no `eval`, `exec`, `sympify`, `parse_expr` or `float` (source scan test). Values match independently built `Fraction` references across generated expressions and hand-written tables |
| 2 | Mathematical correctness stays separate from task compliance | "Simplify 2/4" with `2/4` returns CORRECT, NON_COMPLIANT, FORMAT_REQUIREMENT, score 1. All 5 examples in `contract_simplify_fraction.json` pass unmodified |
| 3 | Chains of arithmetic steps, including alternative methods | At least two different valid methods accepted for the same exercise with no text comparison. Each link has its own verdict, and "step justified" stays separate from "solution complete and correct" |
| 4 | Deterministic, evidence-backed feedback | Same input gives byte-identical output. Every code has fixed English text. `ARITHMETIC_ERROR` and other causes appear only under the rules in `PEDAGOGY_SPEC.md`. A wrong bare answer on a multi-operation expression has no claimed cause |
| 5 | Manual notebook flow tied to a verified revision | In all three browser engines: write, press Verify, revision pinned with server-verified hashes, manual steps confirmed, result shown for that revision. Graph records manual provenance with no stroke IDs, geometry or confidence |
| 6 | No regression in ink saving and sync | The existing Python, JS and browser suites still pass, with no change to Digital Ink semantics, schema or fixtures |
| 7 | Unsupported, ambiguous and over-budget input is safe | These return UNSUPPORTED or UNDETERMINED with no score, `requires_review: true` and never INCORRECT. The next request still works. Malformed requests get a controlled error with no traceback |

Also required: idempotent retries, rejection of a reused key with another payload, one record under concurrent duplicates, original records preserved on correction, and results for an old revision never shown as the verdict for the current page.

Status values for this stage are reported in `PROGRESS.md`. Latency is measured and reported, with no target claimed for production hardware.
