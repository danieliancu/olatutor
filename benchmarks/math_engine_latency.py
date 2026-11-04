"""Latency of the arithmetic engine, in-process. One machine and one run: this is not a promise.

Run: docker compose run --rm --no-deps web python benchmarks/math_engine_latency.py
"""

import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.grading.catalog import load_catalog  # noqa: E402
from apps.grading.engine.grade import grade_steps  # noqa: E402

RUNS = 2000
ORDER = "ks2.order.add-multiply"
LONG_LINE = " × ".join(["999999999999999999/999999999999999989"] * 9)

CORPUS = {
    "single answer": (ORDER, ["11"]),
    "ambiguous": (ORDER, ["1/2/3"]),
    "typical chain, 3 lines": ("ks2.multiply.two-digit", ["12 × 10 + 12 × 5", "120 + 60", "180"]),
    "fractions, 3 links": ("ks2.fraction.add-mixed", ["3/2 + 3/4 = 6/4 + 3/4 = 9/4 = 2 1/4"]),
    "worst case in budget: 30 lines, stops at 512 operations": (
        ORDER,
        [" = ".join([LONG_LINE] * 5)] * 30,
    ),
    "over budget: 31 lines": (ORDER, ["1"] * 31),
}


def main() -> None:
    catalog = load_catalog()
    cases: dict[str, Any] = {}
    report: dict[str, Any] = {
        "python": platform.python_version(),
        "machine": platform.machine(),
        "cpus_seen": os.cpu_count(),
        "runs_per_case": RUNS,
        "unit": "milliseconds",
        "cases": cases,
    }
    for name, (exercise_id, lines) in CORPUS.items():
        exercise = catalog[exercise_id]
        samples = []
        outcome = grade_steps(lines, exercise)
        for _ in range(RUNS):
            started = time.perf_counter()
            outcome = grade_steps(lines, exercise)
            samples.append((time.perf_counter() - started) * 1000)
        samples.sort()
        cases[name] = {
            "p50": round(statistics.median(samples), 3),
            "p95": round(samples[int(RUNS * 0.95)], 3),
            "p99": round(samples[int(RUNS * 0.99)], 3),
            "max": round(samples[-1], 3),
            "outcome": f"{outcome.mathematical_status}/{outcome.code}",
        }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
