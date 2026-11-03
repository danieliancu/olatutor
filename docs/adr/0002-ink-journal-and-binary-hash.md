# ADR 0002: Operation journal, integer coordinates and binary hashing

**Status:** accepted, Milestone 0. Detail: `DIGITAL_INK_SPEC.md`.

**Context:** the browser, the firmware and Python must reconstruct identical pages. Rounding differs between languages (half-even in Python, half-up in JS), and JSON canonicalisation is awkward in C.

**Decision:**

- Integer logical units (0.1 mm). The coordinate transform runs once, at capture, and stored integers are the truth.
- Hash a tagged, length-prefixed binary encoding, not JSON. Hash both the operation chain (evidence) and the state (convergence).
- Append-only journal per page with verified snapshots, plus a separate document journal for page lifecycle. No event sourcing outside ink.
- Erase operations store explicit ranges of the root's immutable points, so replay never re-runs geometry.
- Undo is per-page LIFO, derived from the journal.

**Rejected:**

- Screenshots as the record, which the brief rules out.
- Floats in the contract, which are not portable.
- Re-running eraser geometry at replay, which would make results depend on the implementation.
- UUIDv7 ordering, because a client clock cannot be trusted.

**Consequences:** erasing cuts at vertices, so on sparse samples it can look wider than the eraser (risk R21). Python replay took about 1.6 ms per operation in one measurement on the development PC (not profiled), so snapshots matter for long pages.
