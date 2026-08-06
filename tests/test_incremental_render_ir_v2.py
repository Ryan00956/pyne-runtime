from __future__ import annotations

import pyne_runtime as pn
import pytest


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 10, "open": 1, "high": 3, "low": 0.5, "close": 2, "volume": 10},
        {"time": 20, "open": 2, "high": 4, "low": 1.5, "close": 3, "volume": 20},
        {"time": 30, "open": 3, "high": 5, "low": 2.5, "close": 4, "volume": 30},
    ]


def test_incremental_plotcandle_matches_output_schema_v2_shape() -> None:
    script = """
indicator("Incremental Candles", mode="incremental", overlay=True)

def on_bar(ctx, bar):
    body = color.green if bar.close >= bar.open else color.red
    ctx.plotcandle(
        bar.open, bar.high, bar.low, bar.close,
        "Synthetic", color=body, wickcolor=color.blue,
    )
"""

    result = pn.run(script, _bars(), executor_mode="inline")

    assert result.ok, result.error
    assert result.output["candles"] == [
        {
            "title": "Synthetic",
            "pane": "main",
            "data": [
                {
                    "time": 10,
                    "open": 1.0,
                    "high": 3.0,
                    "low": 0.5,
                    "close": 2.0,
                    "color": "#26a69a",
                    "wickcolor": "#2196f3",
                },
                {
                    "time": 20,
                    "open": 2.0,
                    "high": 4.0,
                    "low": 1.5,
                    "close": 3.0,
                    "color": "#26a69a",
                    "wickcolor": "#2196f3",
                },
                {
                    "time": 30,
                    "open": 3.0,
                    "high": 5.0,
                    "low": 2.5,
                    "close": 4.0,
                    "color": "#26a69a",
                    "wickcolor": "#2196f3",
                },
            ],
        }
    ]


def test_incremental_linefill_polyline_and_table_merge_are_stateful() -> None:
    script = """
indicator("Incremental Objects v2", mode="incremental", overlay=True)

def on_bar(ctx, bar):
    first = ctx.state("first")
    second = ctx.state("second")
    cloud = ctx.state("cloud")
    path = ctx.state("path")
    summary = ctx.state("summary")
    if ctx.bar_index == 0:
        first.value = line.new(0, 1, 2, 3)
        second.value = line.new(0, 2, 2, 4)
        cloud.value = linefill.new(first.value, second.value, color=color.blue)
        points = array.new()
        array.push(points, chart.point.from_index(0, 1))
        array.push(points, chart.point.from_index(1, 3))
        path.value = polyline.new(points, curved=True, closed=True)
        summary.value = table.new(position.top_right, 3, 2)
        table.cell(summary.value, 0, 0, "Merged")
        table.merge_cells(summary.value, 0, 0, 2, 0)
    elif ctx.bar_index == 1:
        linefill.set_color(cloud.value, color.green)
"""

    result = pn.run(script, _bars()[:2], executor_mode="inline")

    assert result.ok, result.error
    objects = result.output["objects"]
    assert objects["linefills"] == [
        {
            "id": "linefill_3",
            "line1_id": "line_1",
            "line2_id": "line_2",
            "color": "#26a69a",
            "pane": "main",
        }
    ]
    assert objects["polylines"][0]["points"] == [{"x": 0, "y": 1}, {"x": 1, "y": 3}]
    assert objects["polylines"][0]["curved"] is True
    assert objects["tables"][0]["merges"] == [
        {"start_column": 0, "start_row": 0, "end_column": 2, "end_row": 0}
    ]


def test_incremental_table_merge_rejects_overlap() -> None:
    script = """
indicator("Bad Merge", mode="incremental")

def on_bar(ctx, bar):
    if ctx.bar_index == 0:
        table_ref = table.new(position.top_right, 3, 3)
        table.merge_cells(table_ref, 0, 0, 1, 1)
        table.merge_cells(table_ref, 1, 1, 2, 2)
"""
    session = pn.PyneIncrementalSession(
        script=script,
        settings=pn.PyneSettings(executor_mode="inline"),
    )

    with pytest.raises(ValueError, match="must not overlap"):
        session.seed(_bars()[:1])


def test_incremental_preview_v2_objects_do_not_persist() -> None:
    script = """
indicator("Preview v2", mode="incremental")

def on_bar(ctx, bar):
    ctx.plotcandle(bar.open, bar.high, bar.low, bar.close, "Committed")

def on_preview(ctx, bar):
    points = array.new()
    array.push(points, chart.point.from_index(ctx.bar_index, bar.close))
    polyline.new(points, line_color=color.red)
    ctx.plotcandle(bar.open, bar.high, bar.low, bar.close, "Preview")
"""
    session = pn.PyneIncrementalSession(
        script=script,
        settings=pn.PyneSettings(executor_mode="inline"),
    )
    session.seed(_bars()[:1])

    preview = session.on_bar_updated(_bars()[1])
    committed = session.snapshot_result()

    assert preview.output["candles"][0]["title"] == "Preview"
    assert preview.output["objects"]["polylines"]
    assert committed.output["candles"][0]["title"] == "Committed"
    assert "objects" not in committed.output
