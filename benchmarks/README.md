# Benchmarks

The recognition benchmark harness is Milestone 3, and its method is fixed in `docs/RECOGNITION_EVALUATION.md`. Nothing here measures recognition yet.

Rules for what goes here:

- Downloaded datasets are git-ignored and listed in a manifest with SHA-256 and licence.
- Results are committed with the exact data split, model version and hardware.
- No result here may come from a mocked recogniser.

## Arithmetic engine latency

`math_engine_latency.py` measures the engine in-process, for Milestone 4A. It uses no recogniser and no data about anyone. Results are recorded in `docs/PROGRESS.md`, with the environment. They come from one development machine, and do not predict production.
