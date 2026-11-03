# Progress

## Milestone 1: functional notebook

**Date:** 2026-11-02. **Environment:** as Milestone 0, plus Firefox and WebKit through Playwright 1.64.1.

**Overall status: PASS** against the milestone's criterion: a page can be saved, restored and reproduced without corruption, across three desktop browser engines, several pages and interruptions. Input is still **simulated**. Whether real writing is acceptable is a separate question (H1), and has no evidence yet.

### Gates

| Gate | Status | Evidence |
|---|---|---|
| Save, restore and reproduce a page | PASS | Geometry and hashes equal after reload, after opening in a fresh browser, and on the server |
| Several pages keep separate ink | PASS | End-to-end test, including undo per page |
| Page deletion hides but keeps evidence | PASS | Server and end-to-end tests; ink written offline is sent before the deletion |
| Zoom and scrolling keep coordinates right | PASS | Writing at 200% and after scrolling lands within 3 logical units (0.3 mm) of the expected spot |
| Conflict recovery loses nothing | PASS | Both user choices tested; set-aside work verified in IndexedDB |
| Reopen a visited notebook offline | PASS | Tested on all three engines over `localhost` |
| Chromium, Firefox, WebKit | PASS | All end-to-end tests pass on each. Playwright's WebKit is not Safari on an iPad |
| Long pages stay usable on the server | PASS for this size | Measurements below |
| Real tablets, real stylus, comfort, latency | **BLOCKED** | No real device tested |
| Offline reopening on a tablet over LAN | **BLOCKED** | Service workers need HTTPS, so testing this needs an HTTPS setup. Without one the notebook works, but cannot reopen offline |
| Palm rejection, board facts, C conformance | **BLOCKED** | Milestone 2: the board is not available yet |
| CI pipeline | **BLOCKED** | Workflow updated, never run; there is no remote |

### Implemented

- `RESTORE_STROKE` and `DELETE_PAGE` in the contract and both cores, with new fixtures. `CHANGE_PAGE` stays on the client.
- Full-state hash now includes palm removals. This changes the hash format within v1, which is acceptable only because no real data exists.
- Server: one-request notebook loading, deleted pages, multi-writer document journal, removal of two unused endpoints.
- Interface: page navigation, new portrait or landscape pages, deletion with confirmation, zoom to 200%, a Move page tool, conflict panel with two choices, service worker for offline reopening, remembered open page, canvas memory limit.
- A fresh browser now stores the server's history in IndexedDB, so it can also reopen offline.

### Tests executed (final run)

| Suite | Result |
|---|---|
| `pytest` (Python units, properties, server, contracts) | **176 passed, 2 skipped** |
| `node --test` (JS conformance) | **110 passed, 0 failed** |
| Playwright end-to-end, simulated pointer input, on Chromium, Firefox and WebKit | **81 passed, 0 failed**, in two consecutive full runs |
| `validate_contracts.py` | 76 checks, 0 failures |
| `ruff check`, `ruff format --check`, `mypy` | clean |

The 2 skips are the same intentional ones as in Milestone 0.

**Failures found and fixed along the way:**

- **A real defect, found through intermittent test failures:** between the end of a stroke and its write to IndexedDB, the operation was not yet queued. For that moment the status could still say "All saved", and **Save page** could pin the page without its newest stroke. An operation now counts as unsaved from the moment it exists, with regression tests.
- **Test infrastructure:** a request still running in the live test server could deadlock against the database flush at teardown. Teardown now closes all browsers and waits for the database to go quiet.
- **Small interface defect:** the orientation selector said Portrait on a wide screen, where the first page is landscape.

Two full runs do not prove the absence of timing problems. They are good evidence for the ones that were found, and more may appear on slower devices.

**Wrong assumption found:** I had skipped the offline test outside Chromium, assuming Playwright could not drive service workers there. It passes on all three, so the skip was removed.

### Performance (one run on the development PC, not a benchmark)

| Measurement | Result |
|---|---|
| Server, batch of 10 operations, journal at 0–500 operations | median 160 ms, max 415 ms |
| Server, same, journal at 1,500–2,000 operations | median 203 ms, max 635 ms |
| Server, load page state through a snapshot, 2,000 operations | 117 ms |
| Server, replay from zero, 2,000 operations | 2,852 ms |

Append cost stays nearly flat as a page grows, thanks to snapshots. Reconstruction and rendering replay from zero by design, so they take seconds on a very long page, and must be queued or rate limited before real use. Opening a notebook replays in the browser from zero too; browser-side cost at this size was not measured. Real-device latency is not measured.

### Known issues and limits

- **Copying a version to a new page drops history:** only the visible result is copied, so undo and erased ink do not carry over. The original journal stays on the device.
- **Other devices' changes appear only on reload,** and a page in conflict stays so until the user chooses.
- **`RESTORE_STROKE` has no button yet;** it is implemented in the cores only.
- **Eraser width on sparse samples,** from Milestone 0, is unchanged and still unmeasured on real input.
- **The local journal and server quarantine grow without limit.** Neither compaction nor payload erasure is implemented.
- **Multi-page submission manifests are not implemented;** revisions pin one page at a time. This belongs with assignments in Milestone 5.
- **Prototype only:** still no authentication or tenancy, so it must stay local.

### Unverified assumptions

Everything listed under Milestone 0, and also: that a Move page tool is an acceptable way to scroll on a tablet, and that default landscape pages suit the 1024×600 panel.

### Next recommended milestone

Milestones 3, 4 and 5 can all proceed without the board:

- **Milestone 4, mathematics:** can be built and fully tested now, needs no external data, and removes the most important product risk that is purely engineering. Recommended next.
- **Milestone 3, recognition:** needs consented adult writers for any honest result, and the board for GT911 ink.
- **Milestone 5, family accounts and dashboard:** can be built, but has little to show until recognition and grading exist. Real child data stays blocked until a DPIA and legal review.

## Milestone 0: repository and technical contracts

**Date:** 2026-11-02. **Environment:** Docker Desktop on Windows 10, 4 CPUs allocated (Intel i5-7300HQ), Python 3.13.18, Django 5.2.18, PostgreSQL 17, Chromium via Playwright 1.64.1, Node 22 for conformance.

**Overall status: PASS** against the milestone's written acceptance criterion (schemas and fixtures validate independently, with no speculative SaaS). The demonstration works with **simulated input only**, and nothing about real writing or hardware has been verified.

### Gates

| Gate | Status | Evidence |
|---|---|---|
| Contract schemas and fixtures validate independently | PASS | `validate_contracts.py`: 73 checks, 0 failures |
| Page reproduced from persisted data | PASS | Browser and server geometry and all three hashes equal, in Chromium, end-to-end tests |
| Python and JS cores agree | PASS | Shared fixtures, including hashes on 300-operation random journals, pass in both |
| Sync: retries, lost responses, offline, conflicts | PASS, Chromium only | End-to-end and server tests below |
| Submitted revision stays immutable | PASS | Trigger, pin and reconstruction tests |
| Fresh start from the README | PASS | Clean copy, separate Docker project, `.env` from the example |
| Real stylus, comfort, touch-to-ink latency | **BLOCKED** | No physical stylus test. Simulated events cannot show this |
| Palm rejection | **BLOCKED** | Only a placeholder pen-over-touch rule exists; the engine is Milestone 2 |
| All board facts | **BLOCKED** | Documentation read; no board connected, ESP-IDF not installed. Everything in the profile is `documented` or `unknown` |
| JS, Python and C agreement | **BLOCKED** | No firmware yet |
| Browsers other than Chromium, real tablets | **BLOCKED** | Not run. Pointer and IndexedDB behaviour may differ |
| CI pipeline | **BLOCKED** | Workflow written, never run; there is no remote |

### Implemented

- Digital Ink v1 contract: specification, JSON schema, fixtures.
- Python core and a separately written JS core: canonical encoding, three hashes, validation, replay, partial erase, undo and redo, pins, coordinate transforms. Snapshots are in the Python core, and server-side only.
- Server: append-only journal, batch sync with idempotency, sequence and base checks, quarantine, verified snapshots, verified revisions, Pillow reconstruction.
- Browser prototype: blank page, Pointer Events, high-DPI canvas, pen, eraser, undo, redo, save, IndexedDB persistence, offline queue with bounded retries, visible sync state, server comparison view.
- Contracts only, not implemented: Page Semantic Graph, grading contracts, device API draft, recognition evaluation method.
- Documents: risk register, H1–H9, hardware profile, ADRs.

### Tests executed (final run)

| Suite | Result |
|---|---|
| `pytest` (Python units, properties, server, contracts) | **150 passed, 2 skipped** |
| `node --test` (JS conformance) | **93 passed, 0 failed** |
| Playwright end-to-end, simulated pointer input | **15 passed, 0 failed** |
| `validate_contracts.py` | 73 checks, 0 failures |
| `ruff check`, `ruff format --check`, `mypy` (32 files) | clean |

The 2 skips are intentional: a pinned fixture and an empty page, neither with anything to upload through that test. Pins are covered elsewhere.

**Test sensitivity check:** 5 defects were deliberately introduced into a throwaway copy of the JS core, and all were caught. Removing map key sorting failed 54 tests, wrong z-position 12, no stack-top check 2, shifted erase range 12, corrupted integer encoding 29. This was only done on the JS core, and is not a full mutation test.

**Failures found and fixed along the way:** a wrong hand-written vector for decomposed Unicode (the fixture was wrong); U+0000 accepted by the contract but refused by PostgreSQL, which would have returned a 500 (now rejected by both cores); a late palm removal that could be undone back into existence through another operation on history (now rejected); conflict recovery that could fail to start, and a pin lost on an offline reload (both fixed, with tests).

### Performance (one run on the development PC, not a benchmark)

| Measurement | Result |
|---|---|
| JS replay, 300-operation journal | 92 ms |
| Python replay, same journal (910 points) | 484 ms |
| JS commit of a 20,000-point stroke | 92 ms |
| JS visible hash, 20,000 points | 48 ms |
| Size of a 20,000-point stroke as JSON | 430 KB |

Not measured: touch-to-ink latency, frame times, or anything on tablets or the board.

### Known issues and limits

- **Eraser width on sparse samples:** cutting at vertices can look wider than the eraser (seen in a screenshot with deliberately sparse simulated points). Unmeasured on real input.
- **A4 portrait on a 1024×600 screen:** the page is much taller than the screen, and the canvas blocks touch panning, so scrolling must start outside the canvas. Page navigation needs real design in Milestone 1.
- **Conflict recovery has no UI:** conflicting work is kept in IndexedDB and in server quarantine, but cannot yet be promoted or discarded by a user.
- **Writer leases are not implemented;** safety currently comes from `base_seq` alone. Two tabs of one notebook conflict.
- **Reload while offline fails,** as there is no service worker, although writing continues in an already open page.
- **Single page only** in the interface; the data model supports more.
- **Specified but unimplemented:** `RESTORE_STROKE`, `DELETE_PAGE`, `CHANGE_PAGE`, compaction, payload erasure, multi-page submission manifests.
- **Quarantine is unbounded,** and there is no rate limiting, authentication or tenancy. The prototype must stay local (`SECURITY_PRIVACY.md`).

### Unverified assumptions

- All values in the hardware profile.
- That a conductive stylus works acceptably on this panel at all.
- That 0.1 mm integer units are fine enough at every capture rate.
- That Python rounding and JS rounding stay within ±1 unit for every transform; only the fixture cases were tested.
- The planning ICC values in the recognition sample sizes.
- Dataset licences, which were read from publisher pages and must be re-checked before use.
- CI behaviour.

### Next recommended milestone

**Milestone 1, functional notebook,** after one short manual test: writing with a real stylus on a tablet, using the steps in the README. It is cheap, and it could change the design of Milestone 1. The hardware track (Milestone 2) can start when the physical board is available.
