# ADR 0003: Milestone 0 prototype has no auth or tenancy

**Status:** accepted for Milestones 0 and 1 only.

**Decision:** the notebook API is unauthenticated and has no tenant model. It is disabled unless development or test settings enable it, binds to localhost by default, and tells users to enter adult test writing only.

**Why:** the brief starts with the ink contract and rules out speculative SaaS scaffolding. The custom `User` model exists from the start, since retrofitting one is painful.

**Consequences and how tenancy will be added (Milestone 5):**

- `Notebook` gains a required tenant foreign key, and every query goes through authorised membership. `NotebookPage`, `InkOperation`, `InkSnapshot` and `PageRevision` already hang off a notebook, so scoping is a single join away.
- `QuarantinedBatch` stores a claimed notebook ID rather than a foreign key, and must become tenant-scoped too.
- Client-generated IDs must stay unguessable and must not be trusted for access. Membership decides.
- Prototype data carries no real users and can be discarded rather than migrated.
