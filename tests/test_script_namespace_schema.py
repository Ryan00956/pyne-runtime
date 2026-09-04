from __future__ import annotations

import pyne_runtime as pn
from pyne_runtime.context import PyneContext
from pyne_runtime.namespace import RuntimeServices, build_script_namespace
from pyne_runtime.security import PyneSecurityPolicy


def test_script_namespace_schema_matches_runtime_namespace() -> None:
    settings = pn.PyneSettings()
    ctx = PyneContext.from_ohlcv([
        {"time": 1, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100},
    ])
    services = RuntimeServices(
        ctx=ctx,
        settings=settings,
        params={},
        policy=PyneSecurityPolicy.from_settings(settings),
    )

    runtime_names = set(build_script_namespace(services)) - {"__builtins__"}
    schema_names = set(pn.schema()["scriptNamespace"]["names"])

    assert schema_names == runtime_names


def test_legacy_aliases_and_runtime_error_are_executable() -> None:
    result = pn.run(
        """
plot(stdev(close, 2), "Deviation")
plot(pivothigh(high, 1, 1), "Pivot")
plot(1 if tostring(2.5) == "2.5" else 0, "String")
plot(floor(close), "Floor")
plot(max(open, close), "Maximum")
plot(1 if timestamp(2024, 1, 2) == time.timestamp(2024, 1, 2) else 0, "Timestamp")
plot(1 if heikinashi("TEST:PAIR").endswith("chart=heikinashi") else 0, "Ticker")
plot(vwap(close), "Legacy VWAP")
""",
        [
            {"time": 1, "open": 1, "high": 2, "low": 0, "close": 1, "volume": 1},
            {"time": 2, "open": 2, "high": 4, "low": 1, "close": 3, "volume": 1},
            {"time": 3, "open": 2, "high": 3, "low": 1, "close": 2, "volume": 1},
        ],
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("String") == [1.0, 1.0, 1.0]
    assert result.values("Floor") == [1.0, 3.0, 2.0]
    assert result.values("Maximum") == [1.0, 3.0, 2.0]
    assert result.values("Timestamp") == [1.0, 1.0, 1.0]
    assert result.values("Ticker") == [1.0, 1.0, 1.0]
    assert result.values("Legacy VWAP") == [1.0, 2.0, 2.0]

    failed = pn.run(
        'runtime.error("unsupported configuration")',
        [{"time": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}],
        executor_mode="inline",
    )
    assert not failed.ok
    assert failed.code == "PYNE_RUNTIME_ERROR"
    assert "unsupported configuration" in str(failed.error)


def test_script_namespace_schema_categories_are_disjoint() -> None:
    categories = pn.schema()["scriptNamespace"]["categories"]
    categorized_names: list[str] = []
    for entries in categories.values():
        if isinstance(entries, list):
            categorized_names.extend(entries)

    assert len(categorized_names) == len(set(categorized_names))
