# ADR 0006: Page Semantics v2 for manual provenance

**Status:** accepted for Milestone 4A. **Date:** 2026-11-04.

## Context

Grading reads a versioned semantic graph, never raw text. Milestone 4A has no recogniser, so its steps are typed and confirmed by a person. Page Semantics v1 cannot say that honestly:

- `candidate.confidence` and `edge.confidence` need a number, and any number would be invented;
- `PROVENANCE` needs stroke IDs on student handwriting nodes, and a typed transcription has no proven link to any stroke;
- `producer` describes a recogniser, and has no way to say that none ran.

## Decision

Add `contracts/page_semantics/v2/` and leave v1, its fixtures and its validation untouched. v2 is v1 plus:

- `version: 2`.
- `producer.kind`: `recogniser` (the v1 fields) or `manual_transcription` (`tool`, `tool_version`, `processed_at`, `confirmed_by`).
- A layer `manual_transcription`, separate from `student`, so typed text is never presented as ink. `PROVENANCE` is unchanged for the student layers.
- `confidence: null` on candidates and edges, meaning "no score exists". It does not mean 0 or 1.

Rules beyond the schema, checked by `scripts/validate_contracts.py` and by the graph builder:

- `MANUAL_NOT_INK`: a manual-layer node with stroke IDs or geometry.
- `MANUAL_PRODUCER`: a manual node in a recogniser graph, or a student-layer node or a hypothesis group in a manual graph.
- `CONFIDENCE_ORIGIN`: a null confidence in a recogniser graph, or a number in a manual graph.

## Compatibility

- A v1 graph remains valid under the v1 schema and means what it meant. No v1 graphs are stored, since nothing produced them.
- A v1 reader must reject v2, because `version` is a constant.
- In Milestone 4A the grading adapter accepts only `version: 2` with `producer.kind: manual_transcription`. Anything else is refused, not reinterpreted.
- Milestone 3 may emit v2 with `kind: recogniser`, where confidence is required. Grading of such graphs is not implemented.

## Consequences

Manually confirmed results can never be mistaken for recognition results, and they say nothing about recognition accuracy. `uncertainty.recognition` and `uncertainty.mathematical` in the grading result are `null`, meaning "not measured" and "not estimated".
