# Risk register

Likelihood and impact are judgement calls (L, M, H) from documents and design review, not measurements. Reviewed at the end of each milestone. Last review: Milestone 1, 2026-11-02.

| ID | Risk | L | I | Mitigation | Validation | Owner milestone |
|---|---|---|---|---|---|---|
| R1 | The capacitive panel cannot separate a passive stylus from a palm or finger | H | H | Palm engine experiment; contract is hardware-independent; alternative styluses and digitizers evaluated | Timestamped GT911 diagnostics with real writers | 2 |
| R2 | Stylus precision on a capacitive panel (tip size, jitter) is too poor for small maths | H | H | Measure jitter and tip options; larger writing scale; hardware decision gate | Physical test | 2 |
| R3 | 1024×600 on 10.1" (about 0.22 mm per pixel) is too coarse, and an A4 page does not fit without panning | M | M | Zoom, a Move page tool and landscape pages now exist; comfort still unknown | Real users | 2 |
| R4 | Writing latency above target on the P4 with LVGL at this resolution | M | H | Local partial redraw, no network wait | Camera-based latency measurement | 2 |
| R5 | Power: 8–10 W documented, USB alone may blank the screen, battery charging limited to 430 mA | M | H | Measure; assume mains or a large battery until shown otherwise | Power meter on the board | 2 |
| R6 | Board revision differences break firmware (LVGL version, pins), and vendor documentation has conflicts | M | M | Versioned hardware profile; read revision from the board; check the schematic | Physical inspection | 2 |
| R7 | No speaker in the package, and mic quality unknown, so voice may not work without extra parts | M | L | Treat voice as optional; smoke test | Physical test | 2, 6 |
| R8 | Local models cannot read children's maths writing reliably | H | H | Reduced symbol set, confirmation, keypad, typed fallback; measured gates | Governed child sample | 3 |
| R9 | No licensed stroke data for `+ × ÷ = /`, and no public consented child data | H | M | Consented adult capture; governed pilot; do not claim from synthetic data | Dataset audit | 3 |
| R10 | Full-page interpretation is much harder than symbol recognition, and may not reach useful accuracy | H | H | Semantic graph with explicit uncertainty; abstain rather than guess; prompted regions as fallback | Hand-labelled pages | 3 |
| R11 | Too few writers to prove accuracy gates (about 30 for 95%, about 60 for 0.5%) | H | M | Recruit consented adults; report as exploratory until reached | Statistical plan | 3 |
| R12 | Wrong grades damage trust, or hidden uncertainty harms a child's confidence | M | H | Contracts, separate uncertainties, "uncertain is never wrong", overrides | Contract tests, pilot | 4 |
| R13 | Parser or symbolic mathematics exhausts server resources | M | H | Allowlisted grammar, limits before evaluation, process isolation | Hostile-input tests | 4 |
| R14 | Leak of children's data between families | L | H | Explicit tenant scoping, tests; prototype off outside development | Security tests | 5 |
| R15 | UK GDPR and Children's Code obligations, especially retained hidden ink, handwriting and profiling | M | H | DPIA before pilot, data inventory, legal review | Independent legal review | 5 |
| R16 | Paid AI costs grow without control | M | M | Single gateway, budgets, deterministic first | Cost per evaluated page | 7 |
| R17 | Parents will not pay, regardless of technology | M | H | Pilot metrics, competitor and pricing review before building billing | Pilot | 5, 7 |
| R18 | Hardware unit economics, supply or support make the device unviable | M | M | Browser and tablet remain first-class | Bill of materials, supplier review | 7 |
| R19 | Browser storage eviction or tab conflicts lose unsynced ink | L | H | Sync status always visible; documented limits; conflict keeps local work; tested on three desktop engines | Real tablets, long use, storage pressure: not tested | 5 |
| R20 | Hash divergence between JS, Python and future C | L | H | Binary canonical form, shared vectors, two implementations already agreeing | C conformance run | 2 |
| R21 | Erasing looks wider than intended on sparse touch samples, since v1 does not interpolate | M | L | Versioned synthetic end caps if needed | Real-device test | 1, 2 |
| R22 | The vendor example code licence is unclear | M | M | Check before reuse; otherwise write from public ESP-IDF drivers | Licence review | 2 |
| R23 | Results from typed transcription are mistaken for what recognition could achieve | M | H | Manual provenance in the schema, a visible label, separate records | Milestone 3 benchmark, kept separate | 3, 4 |
| R24 | Value equality accepts a line reached by faulty reasoning, because equal value does not show method | M | M | Stated in the feedback and spec; `UNJUSTIFIED_TRANSFORMATION` is not claimed | Teacher review of the rules | 4 |
| R25 | Feedback wording or partial marks do not help a child, as nobody has reviewed them | M | M | Short fixed texts, no speculation, marks only by declared rule | Teacher review, then an approved pilot | 4, 5 |
