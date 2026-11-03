# Recognition evaluation methodology

Status: **methodology only.** No recogniser and no benchmark results exist yet. Implementation is Milestone 3. `benchmarks/` is intentionally empty apart from its README.

This method is fixed before data is collected, so that thresholds cannot be chosen to suit results. Changes are recorded with a date and a reason.

## Five levels, each measured on its own

| Level | Question | Primary metrics |
|---|---|---|
| 1 Ink capture | Are strokes preserved exactly? | Replay equality (implemented, see `PROGRESS.md`) |
| 2 Symbols | Which symbol is this? | Symbol error rate, per-class confusion |
| 3 Structure | Fractions, superscripts, equations, lines | Expression exact match, structural accuracy |
| 4 Page | Problems, steps, corrections, reading order | Problem association, step sequence accuracy |
| 5 End to end | Does the reasoning support a correct grade? | Grading agreement against human marks |

Symbol accuracy never supports a claim about full-page understanding.

## Metrics always reported

Exact accuracy, false-confident rate, abstention rate, clarification rate, latency (p50, p95, p99, end to end), memory and CPU or GPU use, failure rate, spread across writers, and monetary **cost per correctly interpreted and evaluated page**, including retries and human review where measurable. Local inference is not assumed to be cheaper than an API: local CPU, local or hosted GPU, external multimodal API and hybrid are compared on the same reference pages.

**Never pooled:** raw accuracy, accuracy after student confirmation and accuracy after human review stay separate. Results are not pooled across symbol sets or devices.

## Data

| Source | Use | Note |
|---|---|---|
| Licensed public datasets | Training and level 2 checks | Licence for commercial training and deployment checked per dataset |
| Synthetic fixtures | Deterministic pipeline tests | Never evidence of accuracy |
| Consented adult samples | Early technical evaluation | Says nothing about children |
| Authorised child samples | Later validation only | Requires a DPIA and a governed pilot. None are collected now |

Dataset facts found so far (from the publishers' pages; re-check before use):

- **UJI Pen Characters v2:** CC BY 4.0, 60 writers, stroke data with no timing or pressure. It has digits, `.`, `-` and brackets, but **no `+`, `×`, `÷`, `=` or `/`**.
- **UCI Pen-Based Digits:** CC BY 4.0, 44 writers. Released features are resampled; contents of the `orig` files are unverified.
- **MathWriting:** reported as CC BY-NC-SA, so it is excluded from anything commercial.
- **HASYv2:** the author states ODbL; raster only; writer IDs unverified.
- **MNIST:** licence unverified, so it is not used for a shipped model unless that changes.

The operator gap means operators have no known licensed stroke source. They can be evaluated from consented adult capture, but must not be claimed as supported from composed or synthetic data.

## Avoiding misleading numbers

- Splits are by **writer**, and a test proves no writer appears twice. The product owner's own writing never enters a test set.
- A test set is frozen and scored once. Choosing between models uses validation writers.
- Pages composed from isolated symbols share layout assumptions with the segmenter, so they are pipeline checks only and can never pass a gate.
- Calibration uses real capture from the target device class. A threshold calibrated on a public dataset does not transfer to browser or GT911 ink.
- The false-confident rate reports coverage beside it, and counts rejects, blanks and crashes as failures, since low coverage flatters it.
- Limiting allowed characters hides some errors, so valid-but-wrong confusions (1↔7, 0↔6, dropped `.` or `-`) are reported as critical classes. Answer length is stratified, because 99% per symbol over 4 symbols is about 96%.
- Confirmation hides raw errors, so post-confirmation results come with a raw-accuracy floor, a correction-burden limit and a test using deliberately seeded errors.
- Recognition never receives the expected answer. The interface enforces this, and a test checks it.

## Statistics and how much data is needed

One-sided 95% Clopper-Pearson bounds, adjusted for clustering by writer: `effective n = n / (1 + (m − 1) × ICC)`, with `m` answers per writer. The ICC (how strongly errors cluster within a writer) is estimated from the data, and a writer-level bootstrap is used for intervals. These computed planning figures assume an ICC of 0.05–0.10, which is itself an assumption.

| Claim | Effective n needed |
|---|---|
| Accuracy bound ≥ 95%, observed 97% | 311 |
| Accuracy bound ≥ 95%, observed 98% | 124 |
| False-confident bound < 0.5%, with 0 errors | 599 |
| Same, with 1 or 2 errors | 949 or 1,259 |

At 5 writers and 300 answers, results are **exploratory**: they can reveal failure but cannot prove success. The 95% gate needs about 30 writers × 40 answers. The 0.5% gate needs about 60 writers × 30 accepted answers, and only if there are zero errors.

## Status rule

Provisional thresholds are in `ACCEPTANCE_CRITERIA.md`. For a measured gate:

| Status | Meaning |
|---|---|
| PASS | The 95% bound clears the threshold at full sample size |
| PARTIAL | The point estimate meets it, the bound does not, with at least 5 writers and 300 answers |
| FAIL | The bound is on the wrong side at any size, or the point estimate misses at the minimum size |
| BLOCKED | Below the minimum size, or no real data |

Performance on children stays BLOCKED until a governed pilot exists, whatever adult results show. Full-page thresholds are set only after representative pages have been collected.

## Recognition failure handling

Keep multiple candidates, show the interpreted region, ask for clarification when useful, let the child correct it, use external AI only when authorised and justified, and otherwise return REVIEW_REQUIRED. Never invent symbols or steps, and never mark correct work wrong because recognition failed.
