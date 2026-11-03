# Product

A parent-managed digital notebook that aims to understand handwritten schoolwork, support learning and identify mistakes. The screen is a notebook page, not a form. Initial market: UK families, starting with a limited, verified subset of England's Key Stage 2 mathematics. Dedicated hardware is optional, and the service must work on tablets and desktop browsers.

## Hypotheses

Every hypothesis below is **unvalidated**. A prototype working once does not validate one. Numeric criteria marked *provisional* are starting points to be fixed before the relevant data is collected.

| # | Hypothesis | Validation method and data | Success | Failure | Fallback |
|---|---|---|---|---|---|
| H1 | Children can write comfortably on the capacitive screen | Governed child pilot, after adult testing; observed tasks and a structured comfort survey | Provisional: most pilot children finish a page without assistance, and report no frequent frustration | Frequent interruptions, or refusal to continue | Other stylus, an active digitizer, or tablets |
| H2 | Software palm rejection is good enough | Timestamped GT911 diagnostics; palm-first and stylus-first scripts; several styluses | Thresholds set after a baseline measurement | Palm strokes accepted, or stylus strokes rejected, often enough to spoil a page | Change hardware; wrist-up guidance as a stopgap |
| H3 | Stroke-first recognition helps maths | Stroke, raster and hybrid compared on the same reference pages | Stroke or hybrid measurably better than raster | No measurable benefit | Raster-first, keeping strokes as the record |
| H4 | A local model reads a useful subset of children's writing | Adult evaluation, then a governed child sample, per `RECOGNITION_EVALUATION.md` | The gates in `ACCEPTANCE_CRITERIA.md` on representative data | Gates missed after a reduced symbol set | Narrower symbols, confirmation always on, keypad, external model where authorised |
| H5 | Python and SymPy grade most supported work without paid LLMs | Share of supported exercises graded deterministically, against human marks | Provisional: at least 90% of supported structured work | Well below that, or any disagreement in approved contract tests | Narrow the supported set; human review |
| H6 | Full-page interpretation associates problems, steps, diagrams and corrections correctly | Hand-labelled representative pages; level 4 and 5 metrics | Thresholds set after collecting representative pages | Associations too often wrong to grade | Prompted regions on the page, with free writing preserved |
| H7 | Parents value this enough to pay | Pilot: time saved, weekly repeat use, satisfaction, willingness to pay; competitor and price review | Set before the pilot | Low repeat use, or no willingness to pay | Reposition or stop |
| H8 | The hardware can be made and supported viably | Bill of materials, supply, certification, support cost, OTA, measured reliability | Margin positive at a validated price | Not viable | Browser and tablet only, which the design already supports |
| H9 | Optional voice improves the experience | Push-to-talk prototype, with accuracy measured on children's speech and task time compared | Measurable improvement at acceptable cost and privacy | No benefit, or privacy or cost too high | Remove voice; buttons remain |

**Evidence so far:** none for any hypothesis. Milestone 0 tested only the ink data path, with simulated input.

The product stays useful if H2 or H8 fails, because the backend and the ink contract do not depend on the board.

## Experience

Students write anywhere on the page, including multiple lines and columns, cross out, erase, undo, move between pages, ask for help, submit, and see feedback beside the relevant work. A keypad exists as a fallback, not the main path.

Parents manage children, curriculum and assignments, review actual handwritten pages, override evaluations, monitor progress by skill, manage devices, and control AI and voice features.

Only the blank-page writing, erase, undo and save parts of this exist today.
