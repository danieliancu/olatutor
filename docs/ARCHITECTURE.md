# Architecture

Modular Django monolith, server-rendered, with no SPA framework or microservices. Only what exists is described here; the later plan is in `ROADMAP.md`.

```
Browser (Canvas + Pointer Events)                 Django + PostgreSQL
┌──────────────────────────────┐                 ┌──────────────────────────────┐
│ capture.js   logical integers│                 │ views.py   HTTP and JSON only│
│ core.js      replay + hashes │── ops batch ──▶ │ services.py  sync rules      │
│ store.js     IndexedDB       │◀── acks ─────── │ ink/         replay + hashes │
│ sync.js      bounded retries │                 │              (no Django)     │
│ render.js    display only    │◀─ rebuilt page ─│ ink/render.py  Pillow raster │
└──────────────────────────────┘                 └──────────────────────────────┘
              contracts/digital_ink/v1: schema + shared fixtures
```

## Data flow

1. Pointer events become logical integer points once, at capture.
2. At pointer-up the gesture becomes one operation. It is applied locally, written to IndexedDB, and queued. Ink never waits for the network.
3. The server validates each operation, checks writer position and base sequence, replays it, and appends it to the journal, all within one transaction holding a row lock on the page.
4. **Save page** waits for sync and pins a revision, which succeeds only if the server's replay reproduces the browser's hashes. Python then returns the reconstruction.
5. On opening, the browser combines one server response holding every journal with its IndexedDB journal. Ink the server has not seen stays pending; if the server's journal moved on without this browser, the page is shown in conflict and the user chooses.

## Components

| Path | Role |
|---|---|
| `apps/notebooks/ink/encoding.py` | Canonical bytes, hashes, error type |
| `apps/notebooks/ink/schema.py` | Structural validation against the contract |
| `apps/notebooks/ink/replay.py` | Page and document state; undo, erase, snapshots |
| `apps/notebooks/ink/transform.py` | Physical to logical coordinates |
| `apps/notebooks/ink/render.py` | Raster reconstruction |
| `apps/notebooks/services.py` | Journal, sync rules, snapshots, revisions, quarantine |
| `apps/notebooks/views.py` | Prototype HTTP API, off outside development |
| `apps/accounts/` | Custom user model only, so that later auth needs no painful migration |
| `static/js/ink/core.js` | Separately written equivalent of the Python core, plus eraser hit-testing |
| `static/js/ink/sw.js` | Service worker: reopens a visited notebook offline. Never caches ink |
| `contracts/` | Schemas and fixtures for ink, semantics, grading and the device draft |
| `scripts/validate_contracts.py` | Validates contracts without importing the application |

## Key properties

- **Two independent implementations:** Python and JS share no code, only fixtures. Agreement is therefore evidence, not an assumption.
- **The journal is the truth.** Snapshots are verified caches, revisions are verified pins, and reconstruction at a revision replays from zero.
- **Hardware independence:** nothing on the server knows about a display or touch controller.

## Deliberately absent

Redis, Celery, DRF and object storage, since there is no workload that needs them yet. Tenancy, login and recognition arrive in their own milestones. Grading exists for arithmetic on manual input only (`apps/grading/`, Milestone 4A). See `adr/`.
