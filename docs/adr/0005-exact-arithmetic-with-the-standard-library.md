# ADR 0005: Exact arithmetic with the standard library, in-process

**Status:** accepted for Milestone 4A. **Date:** 2026-11-04.

## Context

`MATH_GRADING_SPEC.md` and the roadmap name Lark and SymPy as candidates, and require process isolation for expensive symbolic work. Milestone 4A covers arithmetic on integers, fractions, finite decimals and mixed numbers. It has no variables, exponents or symbolic simplification.

## Decision

- A hand-written tokeniser and recursive-descent parser over an allowlisted grammar. No Lark and no SymPy.
- `fractions.Fraction` for values and `decimal.Decimal` for presenting rounded decimals. No `float` in any decision.
- Evaluation runs in the request's process. No subprocess pool.

Cost is bounded by construction, because every limit in `apps/grading/engine/limits.py` is checked before or during evaluation:

- input bytes, tokens and depth are checked before recursion;
- digits per literal and operations are checked before evaluation;
- numerator and denominator bits are checked after each operation;
- steps, expressions per step and total operations are checked per verification.

The grammar has no operator that can grow a value faster than multiplication, so the work has a known upper bound. Going over a limit returns a controlled result: UNDETERMINED, `RESOURCE_LIMIT_EXCEEDED`, no score, review required.

## Consequences

- No new runtime dependency and no change to `uv.lock`.
- No process is started from HTTP, so there is nothing to terminate, leak or multiply.
- **There is no pre-emptive timeout.** A wall-clock limit inside the same process could not stop the calculation, and this design does not pretend to have one. The evidence is the deterministic budget plus the measured worst-case corpus in `PROGRESS.md`, on the development PC only.
- Request concurrency is still unlimited, as for the rest of the prototype. It must stay local (`SECURITY_PRIVACY.md`).

## When this must change

Any symbolic work (algebra, general implication, SymPy) must run in a separate process with enforced time and memory limits, tested for termination and recovery, as the grading specification requires. This ADR does not relax that rule. The engine's step interface can take other checkers later, and no generic algebra is implemented now.
