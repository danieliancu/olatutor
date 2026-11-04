# Agent guide

Parent-managed intelligent digital notebook for UK children. A modular Django monolith; the screen is a notebook page, not a form.

**Active milestone:** none. Milestone 4A is the latest stage worked on, and Milestone 4 as a whole is not finished, see `docs/PROGRESS.md`. Milestone 2 is blocked until the physical board arrives. Do not start another milestone without being asked.

## Sources of truth

- Digital ink: `docs/DIGITAL_INK_SPEC.md` and `contracts/digital_ink/v1/`
- Page semantics: `docs/PAGE_SEMANTICS.md` and `contracts/page_semantics/` (v1, and v2 for manual provenance)
- Grading: `docs/MATH_GRADING_SPEC.md`, `docs/MATH_SUPPORT_MATRIX_4A.md`, `docs/PEDAGOGY_SPEC.md` and `contracts/grading/v1/`
- Hardware facts: `firmware/elecrow_esp32p4/hardware-profile.yaml`
- Status and evidence: `docs/PROGRESS.md`. Targets: `docs/ACCEPTANCE_CRITERIA.md`. Risks: `docs/RISK_REGISTER.md`.

## Commands (everything runs in Docker)

```
docker compose up -d --build --wait web
docker compose run --rm web pytest
docker compose run --rm web sh -c "ruff check . && ruff format --check . && mypy ."
docker compose run --rm --no-deps web python scripts/validate_contracts.py
docker compose --profile js run --rm js
docker compose --profile e2e run --rm --build e2e
docker compose run --rm --no-deps web python scripts/generate_ink_fixtures.py
```

## Rules

- Inspect before editing. One milestone at a time. Smallest useful change, with tests, and report real test outcomes.
- Never fabricate results, hardware compatibility or features. Mark anything unmeasured as unverified. Never substitute a mock recogniser silently, or present mock results as model accuracy.
- Use PASS, PARTIAL, BLOCKED or FAIL with evidence. Never weaken an acceptance criterion in order to report completion.
- Changing ink behaviour means changing the spec, schema, fixtures, the Python core and the JS core together. Bump the version if stored data would be read differently.
- `apps/notebooks/ink/`, `apps/grading/engine/` and `static/js/ink/core.js` stay free of Django and of the DOM. Business rules do not go in views.
- Recognition must never see the expected answer. Uncertainty must never become "wrong".
- No child data in development. Record decisions needing legal review in `docs/SECURITY_PRIVACY.md`.
- No Redis, Celery, microservices or vector database until a measured workload requires them. Record important decisions in `docs/adr/`.
- Update `docs/PROGRESS.md` after each milestone, and `docs/STATUS.md` (the owner's tracking file, in Romanian) whenever a milestone, decision or blocker changes. Commit only when asked.
