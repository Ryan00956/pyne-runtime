# Bar Execution Model

Pyne batch scripts expose a Pine-like bar clock as series values.

```python
plot(bar_index, "Bar Index")
plot(last_bar_index, "Last Bar Index")
plot(time[1], "Previous Time")
```

Available clock values:

- `time`: chart bar timestamps as a series.
- `bar_index`: zero-based bar index as a series.
- `last_bar_index`: the last available bar index as a series.
- `bar_count`: scalar number of input bars.

`time` follows the same history-reference rule as price series:

```python
time[1]  # previous bar timestamp
```

## `barstate`

The `barstate` namespace exposes batch-runtime flags as boolean series:

```python
marker(barstate.isfirst, text="First")
marker(barstate.islast, text="Last")
marker(barstate.isconfirmed, text="Confirmed")
```

Batch-mode fields:

- `barstate.isfirst`: true only on the first bar.
- `barstate.islast`: true only on the final input bar.
- `barstate.ishistory`: true for all batch bars.
- `barstate.isrealtime`: false for all batch bars.
- `barstate.isnew`: true for all batch bars.
- `barstate.isconfirmed`: true for all batch bars.
- `barstate.islastconfirmedhistory`: true on the final input bar.

These are represented as series, so they can be combined with other conditions:

```python
signal = barstate.isconfirmed & (close > close[1])
marker(signal, text="Confirmed Up")
```

Current scope:

- The batch runtime exposes deterministic historical barstate flags.
- Incremental callbacks expose scalar `ctx.bar_index`, `ctx.last_bar_index`, and `ctx.barstate` values for the bar currently being processed.
- Host-specific realtime state is supplied through the runtime/session layer, not inferred by indicators.

## Incremental Callbacks

Incremental scripts process one bar at a time with callback context values:

```python
def on_bar(ctx, bar):
    ctx.marker(ctx.barstate.isconfirmed, text="Confirmed")
    ctx.plot("Index", ctx.bar_index)
    ctx.plot("Bar Index", bar.bar_index)

def on_preview(ctx, bar):
    ctx.marker(ctx.barstate.isrealtime and not ctx.barstate.isconfirmed, text="Preview")
```

During `seed(ohlcv)`, bars are treated as historical:

- `ctx.bar_index` and `bar.bar_index` advance from zero.
- `ctx.last_bar_index` and `bar.last_bar_index` point to the final seeded bar.
- `ctx.barstate.ishistory`, `ctx.barstate.isnew`, and `ctx.barstate.isconfirmed` are true.
- `ctx.barstate.islastconfirmedhistory` is true only on the final seeded bar.

During `on_bar_updated(item)`, the bar is a realtime preview:

- `ctx.barstate.isrealtime` is true.
- `ctx.barstate.isconfirmed` and `ctx.barstate.ishistory` are false.
- `ctx.barstate.isnew` is true only for the first preview update seen for that bar time.
- Preview callbacks run on a cloned context, so state, TA helpers, windows, and output from the preview do not mutate the persistent session.

During `on_bar_closed(item)`, the realtime bar is confirmed and committed:

- `ctx.barstate.isrealtime` and `ctx.barstate.isconfirmed` are true.
- `ctx.barstate.ishistory` and `ctx.barstate.islastconfirmedhistory` are false because this is a live confirmation event, not seeded history.
- `ctx.barstate.isnew` is false if a preview for the same bar time was already seen; it is true when the closed bar is the first event for that bar.
- Persistent state advances only after this confirmed callback succeeds.
