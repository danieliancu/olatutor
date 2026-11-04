# Security and privacy

These are engineering notes, not legal advice and not a statement of compliance. Items marked **Legal** need independent review.

## Current state (Milestone 0)

The prototype has **no authentication and no tenancy**. These controls limit its exposure:

- `INK_PROTOTYPE_ENABLED` is off in base settings, so routes return 404 unless dev or test settings are used (tested). There are no production settings yet.
- Web binds to `127.0.0.1` by default, and Postgres is not published to the host.
- The page tells users to enter adult test writing only. **Real child data must not be entered at this stage.**

Other controls in place:

- CSRF is enforced on writes (tested). Requests are parsed strictly: invalid JSON, duplicate keys, NaN and over-deep nesting are refused safely (tested). Request bodies have Django's default size limit.
- Student ink is treated as untrusted: batch size, point counts and values are bounded. Internal errors are not shown in the interface.
- The journal is append-only, enforced by a database trigger on UPDATE (tested). DELETE stays possible for erasure.
- Secrets come from the environment, and `.env` is git-ignored.

Milestone 4A adds the following:

- `MATH_DEMO_ENABLED` is off in base settings, and the grading routes also need `INK_PROTOTYPE_ENABLED` (tested). It does not make the prototype ready for public access, tenancy or a pilot.
- Grading requests are limited to 64 KB, and refuse unknown fields, cross-page references, U+0000 and lone surrogates (tested). The client cannot send an expected answer, score or rule.
- Student text never reaches `eval` or similar, and is written to the page as text only (tested).
- Typed transcriptions are kept in the database, and are not logged. Grading records are append-only, including against DELETE, so **erasure of these rows needs a designed path before any real data** (**Legal**).
- Grading endpoints have no rate limit, like the rest of the prototype.

Known gaps, for the milestones that add real users:

- Authentication, roles, object-level access, tenant isolation and audit logs
- Rate limiting, which matters for the expensive replay and render endpoints
- A Content Security Policy
- Production TLS and secure-cookie settings
- Quarantine retention: rejected batches are currently kept indefinitely and are unbounded

## Before any real child data (a blocking gate for Milestone 5)

Required, with **Legal** review:

- A Data Protection Impact Assessment
- Lawful-basis assessment; parental consent alone does not settle every obligation
- ICO Children's Code assessment, including age-appropriate information about parental monitoring
- Processor agreements, an incident response plan, tested export and deletion

## Data inventory (initial; to be completed before Milestone 5)

| Category | Purpose | Lawful basis | Retention | Deletion |
|---|---|---|---|---|
| Raw handwriting strokes | Educational record, grading evidence | **Legal: to decide** | To decide; minimise | Payload erasure planned (spec section 8) |
| Hidden or erased ink | Undo, evidence, learning process | **Legal: to decide** | To decide | Must be disclosed to parents |
| Recognition artifacts | Interpretation | **Legal: to decide** | Shorter than the source | Derived, so rebuildable |
| Audio | Voice commands (Milestone 6) | **Legal: to decide** | Not retained indefinitely | To design |
| Device diagnostics | Support, palm-rejection research | **Legal: to decide** | Short | To design |
| Billing | Subscriptions (Milestone 7) | **Legal: to decide** | Statutory | To design |
| AI usage | Cost control | **Legal: to decide** | To decide | To design |

These categories stay separated in storage.

## Open legal questions

- Whether hashes retained after a stroke is erased are personal data. The design keeps them for evidence integrity.
- Retention of crossed-out and erased work, and how to explain it to families.
- Whether handwriting by itself identifies a child, which affects how it may be processed and whether it can be shared with an AI provider.
- Separate permission for using any handwriting to improve models. The default must be no.
- Whether selling a connected device triggers UK product-security duties (PSTI). This needs checking before any hardware sale.

## Principles for later milestones

- No targeted advertising, public profiles or unrestricted child-facing chat.
- No names or identifying information sent to external AI unless strictly necessary, authorised and justified.
- External AI configuration is visible to parents, and external providers do not train on children's data by default.
- Uploaded documents and mathematical input are untrusted. Expensive inference is protected from abuse.
