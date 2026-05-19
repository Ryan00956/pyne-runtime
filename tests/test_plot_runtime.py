from __future__ import annotations

import pyne_runtime as pn


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 1, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100},
        {"time": 2, "open": 2, "high": 3, "low": 1.5, "close": 2.5, "volume": 120},
        {"time": 3, "open": 3, "high": 4, "low": 2.5, "close": 3.5, "volume": 140},
    ]


def test_extended_plot_outputs_are_collected() -> None:
    result = pn.run(
        """
indicator("Outputs", overlay=False)
p1 = plot(close, "Close", color=color.orange)
p2 = plot(open, "Open", color=color.blue)
fill(p1, p2, color="rgba(59,130,246,0.08)")
hline(2, "Mid")
bgcolor(close > open, color="rgba(34,197,94,0.1)")
barcolor(color.green)
emit_signal(close > open, name="up", message="Close above open")
alertcondition(close < open, title="down", message="Close below open")
label("U")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    output = result.output
    assert output["meta"]["title"] == "Outputs"
    assert len(output["fills"]) == 1
    assert len(output["hlines"]) == 1
    assert len(output["bgcolors"]) == 1
    assert len(output["barcolors"]) == 1
    assert len(output["signals"]) == 1
    assert len(output["labels"]) == 1


def test_line_and_label_objects_are_collected_and_updated() -> None:
    result = pn.run(
        """
indicator("Objects", overlay=True)
trend = line.new(
    bar_index[2],
    close[2],
    bar_index,
    close,
    color=color.orange,
    width=1,
)
line.set_color(trend, color.blue)
line.set_width(trend, 3)
line.set_xy2(trend, bar_index, high)
note = label.new(bar_index, high, text="Hi", color=color.green)
label.set_text(note, "Updated")
label.set_color(note, color.red)
label.set_xy(note, bar_index[1], low[1])
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    objects = result.output["objects"]
    assert set(objects) == {"lines", "labels"}

    line_object = objects["lines"][0]
    assert line_object["id"] == "line_1"
    assert line_object["x1"] == 0
    assert line_object["y1"] == 1.5
    assert line_object["x2"] == 2
    assert line_object["y2"] == 4
    assert line_object["color"] == "#2196f3"
    assert line_object["width"] == 3

    label_object = objects["labels"][0]
    assert label_object["id"] == "label_2"
    assert label_object["x"] == 1
    assert label_object["y"] == 1.5
    assert label_object["text"] == "Updated"
    assert label_object["color"] == "#ef5350"


def test_drawing_objects_can_be_deleted() -> None:
    result = pn.run(
        """
indicator("Deleted", overlay=True)
trend = line.new(bar_index[1], close[1], bar_index, close)
note = label.new(bar_index, high, text="gone")
line.delete(trend)
label.delete(note)
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert "objects" not in result.output
