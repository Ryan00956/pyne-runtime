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
- Incremental preview/update semantics will be refined in a later phase.
- Host-specific realtime state should be supplied through the runtime/session layer, not inferred by indicators.
