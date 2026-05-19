# Drawing Objects

Pyne supports Pine-like drawing object handles for dynamic chart annotations.
The first object slice covers `line` and `label`.

```python
indicator("Breakout", overlay=True)

level = line.new(bar_index[5], high[5], bar_index, high)
line.set_color(level, color.orange)

tag = label.new(bar_index, high, text="Breakout")
label.set_color(tag, color.green)
```

## Handles

`line.new()` and `label.new()` return opaque object handles. Scripts should pass
those handles back to namespace methods such as `line.set_color()` or
`label.set_text()`.

Handles are not chart data by themselves. They identify mutable drawing objects
inside the current execution.

## Batch Snapshot Semantics

Pyne batch execution returns the final drawing state:

```json
{
  "objects": {
    "lines": [
      {"id": "line_1", "x1": 0, "y1": 10.0, "x2": 5, "y2": 12.0}
    ],
    "labels": [
      {"id": "label_2", "x": 5, "y": 12.0, "text": "Breakout"}
    ]
  }
}
```

Setter calls update the final snapshot. `delete()` removes the object from the
snapshot.

## Series Coordinates

Object coordinate arguments may be scalars or `PyneSeries` values. When a series
is passed as an object coordinate, Pyne resolves it to the latest valid value in
that series.

This keeps common Pine-like expressions usable:

```python
line.new(bar_index[2], close[2], bar_index, close)
```

In batch execution, this creates a line from the current last bar's
two-bars-back coordinate to the current last bar coordinate.

## Current Scope

Supported now:

- `line.new`, `line.set_*`, `line.delete`
- `label.new`, `label.set_*`, `label.delete`
- legacy `label("text")` fixed-position labels
- final snapshot output under `output["objects"]`

Planned later:

- `box`
- `table`
- object limits in settings
- richer incremental object event streams
