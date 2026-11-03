# Page semantics, version 1

Status: **contract only, not implemented.** Schema and fixtures: `contracts/page_semantics/v1/`. The implementation is Milestone 3.

## Why this layer exists

Raw recogniser text never goes straight to grading. The graph records what the system believes is on one exact page revision and how the pieces relate, including what it is unsure about. Grading reads a versioned graph, and a page is never assumed to have one global top-to-bottom order.

## Semantic layers

| Layer | Owner | Who edits | Visible to | Persistence | In grading | In AI context |
|---|---|---|---|---|---|---|
| Page background | System | Nobody | Everyone | Page template | No | No |
| System exercise content | System or parent | Parent, before assignment | Student, parent | Versioned with the assignment | As the task, never as an answer | Only if permitted |
| Student handwriting | Student | Student, by new operations | Student, parent | Journal | Yes | Only if permitted; minimised |
| Student revisions and crossed-out work | Student | Student | Student, parent | Journal; always recoverable | As history, never automatically as the final answer | Only if permitted; minimised |
| Recognition annotations | System | Nobody; corrections are separate records | Parent; student when asking for clarification | Immutable per revision | Input, with its uncertainty | Only if permitted |
| Grading feedback | System | Nobody; overrides are separate records | Student, parent | Immutable per revision | Output only | No |
| Tutor assistance | System | Nobody | Student, parent | Recorded as assistance used | No | Only if permitted |
| Parent or teacher annotations | Parent or teacher | Their author | Parent; student if shared | Separate from student ink | No | No |

Rule enforced by the fixtures: exercise content has no stroke IDs, so the system's own text can never be read as new student handwriting.

## Graph

Top level: `source` (the exact page revision and visible hash), `producer` (recogniser, model version, time, parameters), `nodes`, `edges`, `hypothesis_groups`.

**Nodes:** Page, Region, ContentBlock, Expression, Symbol, TextBlock, Diagram, Problem, Solution, SolutionStep, Correction, RecognitionCandidate, Annotation. Each has a layer, geometry, source stroke IDs or source content, and candidates.

**Edges:** CONTAINS, NEXT_IN_READING_ORDER, BELONGS_TO_PROBLEM, FOLLOWS_STEP, DERIVED_FROM, REFERENCES, CROSSES_OUT, REPLACES, ANNOTATES, SPATIALLY_RELATED_TO.

## Uncertainty

Alternatives are edges that share a `hypothesis_group`. Their confidence values plus `unresolved_mass` must not exceed 1. A group stays `resolved: false` until evidence selects one alternative.

**What a confidence value means.** A value has `calibrated: false` by default, which makes it a raw score: it may be used for ranking and display, and **must not drive an automated decision**. `calibrated: true` needs a `calibration_id` pointing to a recorded calibration on data representative of the input. Only then does 0.8 mean "about 80% of such cases are right", and only for that population. No calibrated model exists today.

## Rules checked beyond the schema

`scripts/validate_contracts.py` rejects:

- `EDGE_ENDPOINT`: an edge to a missing node.
- `HYPOTHESIS_GROUP`: an edge in an undeclared group.
- `HYPOTHESIS_MASS`: a group whose masses exceed 1.
- `READING_ORDER_CYCLE`: a cycle in reading order.
- `PROVENANCE`: handwriting-derived content without stroke IDs.
- `LAYER_SEPARATION`: exercise content claiming student strokes.
- `DUPLICATE_ID`: repeated node IDs.

## Revision safety

A graph is immutable and tied to one revision and hash. If the child edits the page during recognition, the result stays attached to its original revision. Feedback must not be shown on a different revision without a validated remapping. Recognition caching and changed-region detection are designed in Milestone 3, using revision-aware keys.
