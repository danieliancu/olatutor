# Roadmap

One milestone at a time. A milestone does not start merely because time remains.

| # | Milestone | Key deliverables | Acceptance | Docs created then |
|---|---|---|---|---|
| 0 | Repository and contracts | Ink, semantics and grading contracts, risk register, ink prototype | Schemas and fixtures validate independently | This set |
| 1 | Functional notebook | Multiple pages, zoom and scrolling, offline reopening, conflict recovery, three browser engines | Save, restore and reproduce with no corruption | |
| 2 | Hardware feasibility (parallel) | Verified board, LVGL writing, touch capture, palm experiment, audio smoke test | Capabilities measured; BLOCKED without a board | |
| 3 | Recognition and page semantics | Baseline recogniser, segmentation, semantic graph, benchmark harness | Results on representative complete pages | `RECOGNITION_SPEC.md` |
| 4 | Mathematics and spatial feedback | Secure parser, symbolic grading if justified, step validation, anchored feedback, review | Approved cases pass, including alternatives and failures | `PEDAGOGY_SPEC.md` |
| 4A | Stage of Milestone 4: deterministic arithmetic with manual transcription | Exact parser and engine, arithmetic step chains, deterministic feedback, manual notebook flow pinned to a revision | Criteria in `ACCEPTANCE_CRITERIA.md`. Does not pass Milestone 4 | `MATH_SUPPORT_MATRIX_4A.md` |
| 5 | Family SaaS pilot | Accounts, tenancy, assignments, dashboard, data protection preparation | Small authorised pilot runs without routine developer help | |
| 6 | Parent content and voice | Uploads, extraction, approval, voice commands, tutoring policy | Supported workflows tested and protected | `VOICE_SPEC.md` |
| 7 | AI optimisation and commercialisation | External AI fallback, cost comparison, Stripe, monitoring, secure OTA, security review | Documented launch criteria met | `AI_COST_MODEL.md` |

## Gates that block progress

- **No real child data** before a DPIA and legal review (`SECURITY_PRIVACY.md`).
- **No recognition claims** from synthetic or isolated-symbol results.
- **No commercial device distribution** before validated OTA and recovery.
- **No paid plans** before unit economics are validated.

Milestones 1 to 3 can begin in parallel only where they do not depend on each other. Milestone 2 needs the physical board. Milestone 3 needs consented adult writers (see the sample sizes in `RECOGNITION_EVALUATION.md`).

## The route from here

A letter marks a stage of work, not a renumbering of the milestones above. Only A has been started, and nothing in B to F is implemented.

| Stage | Scope | Milestones |
|---|---|---|
| A | Mathematics engine | 4A |
| B | Recognition and page semantics | 3, then the rest of 4 |
| C | Families, homework, curriculum and progress | 5 |
| D | Parents' materials and voice | 6 |
| E | Device integration, controlled AI, security and commercial launch | 2, 7 |
| F | Mandatory physical validation: real stylus, board, tablets, adult writers, then an approved pilot | 2, 3, 5 |
