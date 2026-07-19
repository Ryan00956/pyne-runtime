"""Deterministic growth checks for Pyne Runtime performance-critical paths.

The checks intentionally use relative growth and fast/slow-path ratios instead
of absolute wall-clock budgets.  This keeps the gate useful across developer
machines while still catching the quadratic regressions it was designed for.
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import sys
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pyne_runtime as pn  # noqa: E402
from pyne_runtime.incremental.limits import Window  # noqa: E402
from pyne_runtime.ta import TaModule  # noqa: E402
from pyne_runtime.utils import pivothigh, rising  # noqa: E402


_DENSE_STRATEGY = """
strategy("Dense", overlay=True)
strategy.order_when(bar_index % 2 == 0, "L", strategy.long, qty=1, price=close)
strategy.order_when(bar_index % 2 == 1, "S", strategy.short, qty=1, price=close)
"""

_CLOSE_STRATEGY = """
strategy("Close", overlay=True)
strategy.entry_when(bar_index % 2 == 0, "L", strategy.long, qty=1, price=close)
strategy.close_when(bar_index % 2 == 1, "L", price=close)
"""


def _bars(count: int) -> list[dict[str, float]]:
    return [
        {
            "time": index + 1,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0 + (index % 2),
            "volume": 1.0,
        }
        for index in range(count)
    ]


def _median_seconds(callback: Callable[[], Any], repeats: int) -> float:
    samples: list[float] = []
    for _ in range(max(int(repeats), 1)):
        gc.collect()
        started = time.perf_counter()
        result = callback()
        samples.append(time.perf_counter() - started)
        if hasattr(result, "ok") and not result.ok:
            raise RuntimeError(result.error)
        del result
    return statistics.median(samples)


def _growth_check(
    name: str,
    *,
    small: float,
    large: float,
    limit: float,
    unit: str,
) -> dict[str, Any]:
    ratio = large / small if small > 0 else float("inf")
    return {
        "name": name,
        "small": small,
        "large": large,
        "unit": unit,
        "ratio": ratio,
        "limit": limit,
        "passed": ratio <= limit,
    }


def _strategy_close_growth(repeats: int) -> dict[str, Any]:
    small_bars = _bars(120)
    large_bars = _bars(240)
    pn.run(_CLOSE_STRATEGY, _bars(12), executor_mode="inline")
    small = _median_seconds(
        lambda: pn.run(_CLOSE_STRATEGY, small_bars, executor_mode="inline"),
        repeats,
    )
    large = _median_seconds(
        lambda: pn.run(_CLOSE_STRATEGY, large_bars, executor_mode="inline"),
        repeats,
    )
    return _growth_check(
        "strategy_close_time_growth",
        small=small,
        large=large,
        limit=3.25,
        unit="seconds",
    )


def _strategy_dense_memory_growth() -> dict[str, Any]:
    pn.run(_DENSE_STRATEGY, _bars(12), executor_mode="inline")

    def peak_bytes(count: int) -> float:
        data = _bars(count)
        gc.collect()
        tracemalloc.start()
        try:
            result = pn.run(_DENSE_STRATEGY, data, executor_mode="inline")
            if not result.ok:
                raise RuntimeError(result.error)
            _, peak = tracemalloc.get_traced_memory()
            return float(peak)
        finally:
            tracemalloc.stop()

    return _growth_check(
        "strategy_dense_memory_growth",
        small=peak_bytes(300),
        large=peak_bytes(600),
        limit=3.0,
        unit="bytes",
    )


def _window_index_growth(repeats: int) -> dict[str, Any]:
    def scan(count: int) -> float:
        window = Window(count)
        for value in range(count):
            window.append(value)
        return _median_seconds(
            lambda: sum(window[index] for index in range(len(window))),
            repeats,
        )

    return _growth_check(
        "window_index_time_growth",
        small=scan(2_000),
        large=scan(4_000),
        limit=3.0,
        unit="seconds",
    )


def _rising_growth(repeats: int) -> dict[str, Any]:
    def evaluate(count: int) -> float:
        source = np.arange(count, dtype=np.float64)
        return _median_seconds(lambda: rising(source, count // 2), repeats)

    return _growth_check(
        "rising_time_growth",
        small=evaluate(1_000),
        large=evaluate(2_000),
        limit=3.0,
        unit="seconds",
    )


def _stdev_nan_penalty(repeats: int) -> dict[str, Any]:
    ta = TaModule()
    clean = np.linspace(1.0, 10_000.0, 100_000, dtype=np.float64)
    with_nan = clean.copy()
    with_nan[0] = np.nan
    clean_time = _median_seconds(lambda: ta.stdev(clean, 20), repeats)
    nan_time = _median_seconds(lambda: ta.stdev(with_nan, 20), repeats)
    return _growth_check(
        "stdev_nan_slow_path_penalty",
        small=clean_time,
        large=nan_time,
        limit=12.0,
        unit="seconds",
    )


def _wma_growth(repeats: int) -> dict[str, Any]:
    module = TaModule()

    def evaluate(count: int) -> float:
        source = np.sin(np.arange(count, dtype=np.float64) / 17.0)
        return _median_seconds(lambda: module.wma(source, count // 2), repeats)

    return _growth_check(
        "wma_time_growth",
        small=evaluate(20_000),
        large=evaluate(40_000),
        limit=3.0,
        unit="seconds",
    )


def _order_statistic_growth(repeats: int) -> dict[str, Any]:
    module = TaModule()

    def evaluate(count: int) -> float:
        source = np.sin(np.arange(count, dtype=np.float64) / 29.0)
        return _median_seconds(
            lambda: module.percentile_linear_interpolation(
                source,
                count // 2,
                75,
            ),
            repeats,
        )

    return _growth_check(
        "rolling_order_statistic_time_growth",
        small=evaluate(4_000),
        large=evaluate(8_000),
        limit=3.25,
        unit="seconds",
    )


def _pivot_growth(repeats: int) -> dict[str, Any]:
    def evaluate(count: int) -> float:
        source = np.sin(np.arange(count, dtype=np.float64) / 23.0)
        flank = count // 4
        return _median_seconds(lambda: pivothigh(source, flank, flank), repeats)

    return _growth_check(
        "pivot_time_growth",
        small=evaluate(10_000),
        large=evaluate(20_000),
        limit=3.0,
        unit="seconds",
    )


def build_report(*, repeats: int) -> dict[str, Any]:
    checks = [
        _strategy_close_growth(repeats),
        _strategy_dense_memory_growth(),
        _window_index_growth(repeats),
        _rising_growth(repeats),
        _stdev_nan_penalty(repeats),
        _wma_growth(repeats),
        _order_statistic_growth(repeats),
        _pivot_growth(repeats),
    ]
    return {
        "schema": "pyne.performance-smoke.v1",
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "repeats": max(int(repeats), 1),
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="return non-zero on a failed budget")
    parser.add_argument("--json", action="store_true", help="print the full JSON report")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    report = build_report(repeats=args.repeats)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for check in report["checks"]:
            status = "PASS" if check["passed"] else "FAIL"
            print(
                f"{status} {check['name']}: ratio={check['ratio']:.3f} limit={check['limit']:.3f}"
            )
        print("PASS" if report["passed"] else "FAIL")
    return 1 if args.check and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
