# Acceptance criteria

Statuses: PASS, PARTIAL, BLOCKED, FAIL, each with evidence. A feature is not complete because a file or class exists. All numeric targets are provisional and require empirical validation; they are not claims about current performance. Evidence for what has been run is in `PROGRESS.md`.

## Provisional product targets

| Area | Target | Measured so far |
|---|---|---|
| Deterministic grading | All approved contract tests pass | Not implemented |
| Short-answer recognition | At least 95% exact after the specified confirmation | Not implemented |
| Confidently wrong automatic reading | Below 0.5% on representative validation data | Not implemented |
| Simple grading latency | p95 under 1 s on selected server hardware | Not implemented |
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

Criteria for Milestones 2–7 are in the brief, and are summarised in `ROADMAP.md`. Each must be turned into measurable values here before that milestone starts.
