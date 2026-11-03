# ADR 0004: Explicit conflict policy instead of a writer lease

**Status:** accepted, Milestone 1.

**Context:** the brief asks for a single authoritative writer, or an explicit conflict policy, for each editing session. Milestone 0 anticipated a server-issued lease.

**Decision:** an explicit conflict policy.

- Ink on a page has one linear history, checked by `base_seq`. A writer whose view is out of date gets `BASE_CONFLICT`.
- Nothing is merged automatically. The user picks: keep their version as a new page, or use the other version.
- Work set aside stays on the device, and the server's quarantine keeps the rejected batch.
- Page creation and deletion commute, so the document journal accepts several writers.

**Why not a lease:** a device writing offline cannot honour a lease's expiry, so a lease could not replace the `base_seq` check. It would only warn earlier, at the cost of a new server state, renewal traffic and failure modes. Merging ink automatically is rejected because undo and erase operations refer to specific history, so a merge could change what the child's work means.

**Consequences:** a child using two devices at once gets a visible conflict. Copying a version to a new page keeps what was visible, not its history. If real use shows frequent conflicts, a lease can be added on top as an early warning, with no change to the contract.
