# Incremental Runtime

Batch scripts are the default. Incremental scripts define `on_bar(ctx, bar)` and can maintain state across bars.

```python
indicator("Incremental MA", mode="incremental", overlay=True)

def init(ctx):
    ctx.ta.sma("ma", period=20)

def on_bar(ctx, bar):
    value = ctx.ta.sma("ma").update(bar.close)
    ctx.plot("MA", value, color=color.orange)
```

Incremental mode is useful for realtime hosts because updates can avoid recomputing the full history.

Callback context exposes Pine-like scalar clock values for the current event:

- `ctx.bar_index` and `bar.bar_index`
- `ctx.last_bar_index` and `bar.last_bar_index`
- `ctx.barstate.isrealtime`
- `ctx.barstate.isnew`
- `ctx.barstate.isconfirmed`
- `ctx.barstate.ishistory`

`on_bar_updated()` runs as an unconfirmed realtime preview on a cloned context,
so preview state does not mutate the persistent session. `on_bar_closed()`
confirms the realtime bar and advances persistent state.

