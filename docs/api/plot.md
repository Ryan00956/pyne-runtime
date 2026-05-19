# Plot API

Plot helpers are injected into scripts.

```python
indicator("Bands", overlay=True)

p1 = plot(upper, "Upper", color=color.blue)
plot(mid, "Middle", color=color.orange)
p2 = plot(lower, "Lower", color=color.blue)
fill(p1, p2, color="rgba(59,130,246,0.08)")
```

Common outputs:

- `plot()`
- `bar()`
- `hline()`
- `fill()`
- `marker()`
- `bgcolor()`
- `barcolor()`
- `emit_signal()`
- `alertcondition()`
- `line.new()` / `line.set_*()` / `line.delete()`
- `label.new()` / `label.set_*()` / `label.delete()`

`label("text")` remains available as a compact legacy helper for fixed-position
layout labels. Use `label.new()` when you need a Pine-like mutable label object
anchored to a bar or price.

## Drawing Objects

`line` and `label` are Pine-like object namespaces. Constructors return opaque
handles that can be passed to setter functions. Pyne serializes the final object
snapshot under `output["objects"]`.

```python
indicator("Objects", overlay=True)

trend = line.new(bar_index[2], close[2], bar_index, close, color=color.orange)
line.set_color(trend, color.blue)
line.set_width(trend, 3)

note = label.new(bar_index, high, text="Breakout", color=color.green)
label.set_text(note, "Confirmed")
```

For object coordinates, series arguments are resolved to their latest valid
value. This makes history references such as `bar_index[2]` and `close[2]`
usable in batch execution.

Supported `line` methods:

- `line.new(x1, y1, x2, y2, color="#2196f3", width=1, style="solid", extend="none")`
- `line.set_xy1(ref, x, y)`
- `line.set_xy2(ref, x, y)`
- `line.set_x1(ref, x)`
- `line.set_y1(ref, y)`
- `line.set_x2(ref, x)`
- `line.set_y2(ref, y)`
- `line.set_color(ref, color)`
- `line.set_width(ref, width)`
- `line.set_style(ref, style)`
- `line.set_extend(ref, extend)`
- `line.delete(ref)`

Supported `label` methods:

- `label.new(x, y, text="", color="#ffffff", textcolor="#000000")`
- `label.set_xy(ref, x, y)`
- `label.set_x(ref, x)`
- `label.set_y(ref, y)`
- `label.set_text(ref, text)`
- `label.set_color(ref, color)`
- `label.set_textcolor(ref, textcolor)`
- `label.set_style(ref, style)`
- `label.set_size(ref, size)`
- `label.delete(ref)`

