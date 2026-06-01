from __future__ import annotations

import pyne_runtime as pn


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 1, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100},
        {"time": 2, "open": 2, "high": 3, "low": 1.5, "close": 2.5, "volume": 120},
        {"time": 3, "open": 3, "high": 4, "low": 2.5, "close": 3.5, "volume": 140},
    ]


def test_input_schema_and_param_overrides() -> None:
    result = pn.run(
        """
length = input.int(20, "Length", minval=1, maxval=100)
mult = input.float(2.0, "Multiplier", minval=0.1)
show = input.bool(True, "Show")
kind = input.string("EMA", "Type", options=["SMA", "EMA"])
col = input.color("#f59e0b", "Color")
src = input.source(close, "Source")
plot(src * mult, kind, color=col)
""",
        _bars(),
        params={"Length": 5, "Multiplier": 3.0, "Show": False, "Type": "SMA"},
        executor_mode="inline",
    )

    assert result.ok
    names = {item["key"] for item in result.param_schema}
    assert names == {"Length", "Multiplier", "Show", "Type", "Color", "Source"}
    assert result.lines[0]["name"] == "SMA"
    assert result.lines[0]["data"][-1]["value"] == 10.5


def test_params_namespace_is_read_only_and_separate_from_input_params() -> None:
    result = pn.run(
        """
try:
    params["Length"] = 9
    readonly = 0
except Exception:
    readonly = 1
length = input.int(2, "Length")
plot(readonly, "Read Only")
plot(length, "Length")
""",
        _bars(),
        params={"Length": 5},
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Read Only") == [1.0, 1.0, 1.0]
    assert result.values("Length") == [5.0, 5.0, 5.0]


def test_input_source_identifies_named_derived_series() -> None:
    result = pn.run(
        """
src = input.source(hlcc4, "Source")
plot(src, "Selected")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.param_schema[0]["default"] == "hlcc4"
    assert result.values("Selected")[-1] == (4 + 2.5 + 3.5 + 3.5) / 4
