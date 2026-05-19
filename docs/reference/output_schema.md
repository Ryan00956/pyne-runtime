# Output Schema

Pyne results use `schemaVersion = 1`.

Top-level result keys:

- `schemaVersion`: output schema version.
- `ok`: whether execution succeeded.
- `error`: error message when execution failed.
- `code`: stable error code when execution failed.
- `errorDetail`: structured error detail when execution failed.
- `lines`: backward-compatible flat plotted series.
- `output`: structured output collections.
- `param_schema`: input parameter declarations collected from scripts.
- `meta`: indicator metadata collected from `indicator()`.

Structured output keys:

- `lines`
- `histograms`
- `markers`
- `hlines`
- `fills`
- `bgcolors`
- `barcolors`
- `signals`
- `strategy`
- `objects`

Point format:

```json
{"time": 1710000000, "value": 123.45}
```

Drawing object snapshot format:

```json
{
  "objects": {
    "lines": [
      {
        "id": "line_1",
        "x1": 0,
        "y1": 123.0,
        "x2": 10,
        "y2": 130.0,
        "color": "#2196f3",
        "width": 2,
        "style": "solid",
        "extend": "none",
        "xloc": "bar_index",
        "pane": "main"
      }
    ],
    "labels": [
      {
        "id": "label_2",
        "x": 10,
        "y": 130.0,
        "text": "Breakout",
        "color": "#ffffff",
        "textcolor": "#000000",
        "style": "label_down",
        "size": "normal",
        "xloc": "bar_index",
        "pane": "main"
      }
    ],
    "boxes": [
      {
        "id": "box_3",
        "left": 0,
        "top": 130.0,
        "right": 10,
        "bottom": 123.0,
        "bgcolor": "rgba(38,166,154,0.15)",
        "border_color": "#26a69a",
        "border_width": 1,
        "border_style": "solid",
        "xloc": "bar_index",
        "pane": "main"
      }
    ],
    "tables": [
      {
        "id": "table_4",
        "position": "top_right",
        "columns": 2,
        "rows": 1,
        "bgcolor": "#ffffff",
        "frame_color": "#787b86",
        "frame_width": 1,
        "border_color": "#787b86",
        "border_width": 1,
        "pane": "main",
        "cells": [
          {
            "column": 0,
            "row": 0,
            "text": "Close",
            "text_color": "#000000",
            "bgcolor": null,
            "width": null,
            "height": null,
            "text_halign": "center",
            "text_valign": "middle"
          }
        ]
      }
    ]
  }
}
```

Strategy event format:

```json
{
  "strategy": {
    "orders": [
      {
        "time": 1710000000,
        "id": "Long",
        "type": "entry",
        "side": "long",
        "qty": 1.0,
        "price": 123.45,
        "position_after": 1.0,
        "comment": ""
      }
    ],
    "position": {
      "size": 1.0,
      "side": "long",
      "avg_price": 123.45
    }
  }
}
```

Pane values:

- `main`
- `separate`

See [error codes](error_codes.md) for structured failure payloads.
