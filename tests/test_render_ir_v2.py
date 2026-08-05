from __future__ import annotations

from typing import Any

import pyne_runtime as pn


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 10, "open": 1, "high": 3, "low": 0.5, "close": 2, "volume": 10},
        {"time": 20, "open": 2, "high": 4, "low": 1.5, "close": 3, "volume": 20},
        {"time": 30, "open": 3, "high": 5, "low": 2.5, "close": 4, "volume": 30},
    ]


def test_plotcandle_emits_candle_collection_with_per_bar_colors() -> None:
    result = pn.run(
        """
indicator("Candles", overlay=True)
body = when(close >= open, color.green, color.red)
plotcandle(open, high, low, close, "Synthetic", color=body, wickcolor=color.blue)
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    candle = result.output["candles"][0]
    assert candle["title"] == "Synthetic"
    assert candle["pane"] == "main"
    assert candle["data"][0] == {
        "time": 10,
        "open": 1.0,
        "high": 3.0,
        "low": 0.5,
        "close": 2.0,
        "color": "#26a69a",
        "wickcolor": "#2196f3",
    }


def test_linefill_polyline_and_table_merges_are_serialized() -> None:
    result = pn.run(
        """
first = line.new(0, 1, 2, 3)
second = line.new(0, 2, 2, 4)
cloud = linefill.new(first, second, color=color.new(color.blue, 80))
linefill.set_color(cloud, color.new(color.green, 70))

points = array.new()
array.push(points, chart.point.from_index(0, 1))
array.push(points, chart.point.from_index(1, 3))
array.push(points, chart.point.from_index(2, 2))
polyline.new(points, curved=True, closed=True, fill_color=color.new(color.blue, 85))

summary = table.new(position.top_right, 3, 2)
table.cell(summary, 0, 0, "Merged")
table.merge_cells(summary, 0, 0, 2, 0)
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    objects = result.output["objects"]
    assert objects["linefills"] == [
        {
            "id": "linefill_3",
            "line1_id": "line_1",
            "line2_id": "line_2",
            "color": "rgba(38,166,154,0.3)",
            "pane": "main",
        }
    ]
    assert objects["polylines"][0]["points"] == [
        {"x": 0, "y": 1},
        {"x": 1, "y": 3},
        {"x": 2, "y": 2},
    ]
    assert objects["polylines"][0]["curved"] is True
    assert objects["polylines"][0]["closed"] is True
    assert objects["tables"][0]["merges"] == [
        {"start_column": 0, "start_row": 0, "end_column": 2, "end_row": 0}
    ]


def test_table_merge_rejects_overlap_and_out_of_bounds() -> None:
    overlap = pn.run(
        """
t = table.new(position.top_right, 3, 3)
table.merge_cells(t, 0, 0, 1, 1)
table.merge_cells(t, 1, 1, 2, 2)
""",
        _bars(),
        executor_mode="inline",
    )
    bounds = pn.run(
        """
t = table.new(position.top_right, 2, 2)
table.merge_cells(t, 0, 0, 2, 1)
""",
        _bars(),
        executor_mode="inline",
    )

    assert not overlap.ok
    assert "must not overlap" in str(overlap.error)
    assert not bounds.ok
    assert "outside the table" in str(bounds.error)


class _LowerTimeframeProvider:
    capabilities = {"request.security_lower_tf": True}

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> list[dict[str, Any]]:
        _ = symbol, timeframe, start, end
        return [
            {"time": 10, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 5},
            {"time": 12, "open": 2, "high": 2, "low": 1, "close": 1, "volume": 3},
            {"time": 20, "open": 4, "high": 4, "low": 4, "close": 4, "volume": 7},
            {"time": 30, "open": 2, "high": 3, "low": 2, "close": 3, "volume": 11},
        ]


def test_pinned_tradingview_ta_10_adapter_uses_authoritative_intrabar_data() -> None:
    result = pn.run(
        """
tv_ta = pine_library("TradingView/ta/10")
up, down, delta = tv_ta.requestUpAndDownVolume("1")
plot(up, "Up")
plot(down, "Down")
plot(delta, "Delta")
""",
        _bars(),
        data_provider=_LowerTimeframeProvider(),
        syminfo={"tickerid": "TEST:BTCUSD"},
        timeframe={"period": "10"},
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Up") == [5.0, 0.0, 11.0]
    assert result.values("Down") == [-3.0, 0.0, 0.0]
    assert result.values("Delta") == [2.0, 0.0, 11.0]


def test_external_library_registry_fails_closed_for_unknown_library() -> None:
    result = pn.run(
        "pine_library('SomeAuthor/Unknown/1')",
        _bars(),
        executor_mode="inline",
    )

    assert not result.ok
    assert result.code == "PYNE_UNSUPPORTED_FEATURE"
