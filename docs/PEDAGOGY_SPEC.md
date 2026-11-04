# Pedagogy specification

Status: **delivered for Milestone 4A only**, in `apps/grading/engine/feedback.py`. It covers feedback on typed, manually confirmed arithmetic. Spatial feedback on the page, voice and tutoring are not implemented, and nothing here has been tried with a child or checked by a teacher.

## Rules

1. **Short and specific.** Each result says what was checked, where a problem can be shown, and gives the first useful hint.
2. **More only on request.** "Explain more" fetches a further explanation. It is not in the first response.
3. **Never the solution.** No text holds a value from an exercise, and API responses leave out computed values. Tests check both. The expected answer never reaches the client.
4. **No speculation.** A wrong value does not show why it was written. Texts never say "you forgot" or name a misconception.
5. **Unclear work is asked about, not marked.** Ambiguous or unfinished input asks for a correction or confirmation, with no mark and no "wrong" verdict.
6. **Deterministic.** The same input gives the same code and text. Codes are stable, and texts are fixed in British English.

## What a result shows

| Part | Source | When |
|---|---|---|
| Summary and mark | Status, compliance, score | Always. "No mark given" for UNSUPPORTED and UNDETERMINED |
| What was checked | `feedback.checked` | Always |
| The problem, with its line | `feedback.problem` | Only when it can be shown |
| First hint | `feedback.hint` | When there is something to do |
| Each line's verdict | Step results | Always |
| Further explanation | `explanation` endpoint | Only on request |

Feedback is per line and per solution. It is **not anchored to any place on the page**, because a typed line has no proven link to any stroke.

## When a cause is named

| Evidence | `error_class` | Code |
|---|---|---|
| One operation on written numbers, with a different number after it: `3 + 8 = 12` | `ARITHMETIC_ERROR` | `STEP_VALUE_CHANGED` |
| One written number rewritten as a different one: `2/4` to `1/3` | `ARITHMETIC_ERROR` | `STEP_VALUE_CHANGED` |
| A written line with a different value from the one before, in any other case: `3 + 4 × 2 = 7 × 2` | `INVALID_TRANSFORMATION` | `TRANSFORMATION_CHANGED_VALUE` |
| A bare answer to a calculation of more than one operation: `14` for `3 + 4 × 2` | none | `ANSWER_VALUE_MISMATCH` |
| The exact value rounded to other places, or truncated | `ROUNDING_ERROR` | `ROUNDING_WRONG` |
| A division by zero | `DOMAIN_VIOLATION` | `DIVISION_BY_ZERO` |
| The right value in the wrong form | `FORMAT_REQUIREMENT` | `VALUE_RIGHT_NOT_SIMPLIFIED`, `VALUE_RIGHT_FORM_WRONG` or `NOT_ROUNDED_AS_ASKED` |
| A calculation left unfinished, or required working missing | `INCOMPLETE_REASONING` | `ANSWER_NOT_FINAL` or `STEPS_REQUIRED` |

`ARITHMETIC_ERROR` means only that the written values differ. It does not diagnose why. `INVALID_TRANSFORMATION` means a rewritten line changed the value, and says nothing about the reasoning. The `2/4` to `1/3` row exists because the approved fixture `contract_simplify_fraction` requires it.

`UNJUSTIFIED_TRANSFORMATION` is never produced. A line with the same value is accepted, because equal value shows only that the value was kept. It does not show how the writer got there, and the explanation says so.

## Codes

- **Solution:** `SOLUTION_COMPLETE`, `VALUE_RIGHT_NOT_SIMPLIFIED`, `VALUE_RIGHT_FORM_WRONG`, `NOT_ROUNDED_AS_ASKED`, `ANSWER_NOT_FINAL`, `STEPS_REQUIRED`, `ANSWER_VALUE_MISMATCH`, `FINAL_RIGHT_AFTER_STEP_ERROR`.
- **Line:** `STEP_VALUE_KEPT`, `STEP_ROUNDED`, `STEP_NOT_CHECKED`, `STEP_VALUE_CHANGED`, `TRANSFORMATION_CHANGED_VALUE`, `ROUNDING_WRONG`, `DIVISION_BY_ZERO`.
- **Ask for correction:** `EMPTY_EXPRESSION`, `INCOMPLETE_EXPRESSION`, `MISSING_OPERATOR`, `AMBIGUOUS_FRACTION_CHAIN`, `AMBIGUOUS_MIXED_NUMBER`, `AMBIGUOUS_NUMBER_FORMAT`, `AMBIGUOUS_MULTIPLY_X`, `AMBIGUOUS_REPEATED_SIGN`.
- **Cannot read:** `UNSUPPORTED_SYMBOL`, `UNSUPPORTED_OPERATOR`, `APPROX_NOT_SUPPORTED`.
- **Over budget:** `RESOURCE_LIMIT_EXCEEDED`.

## Known limits

- `requires_review` is only a flag. No review queue or reviewer exists, so the interface asks for a corrected transcription and says a person is needed if the work stays unclear.
- Whether these texts help a child is **unverified**. They need review by a teacher, and the wording will change.
- A partial mark exists only where an exercise declares a rule. Whether those marks are fair is an open judgement for whoever approves the exercises.
