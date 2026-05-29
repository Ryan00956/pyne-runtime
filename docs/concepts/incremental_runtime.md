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

## Internal Responsibilities

Incremental runtime code is split by lifecycle role:

- `incremental.bar` defines `IncrementalBar` and scalar barstate wiring.
- `incremental.result` defines `IncrementalPyneResult`.
- `incremental.limits` tracks drawing, state, and resource limits.
- `incremental.ta` owns step-by-step technical-analysis helpers.
- `incremental.drawing` owns line, label, box, and table mutation helpers.
- `incremental.strategy` owns scalar current-bar strategy state and callback
    reporting, while reusing shared batch strategy constants and pure helpers.
- `incremental.context` exposes the callback-facing `ctx` object.
- `incremental.session` owns script compilation, preview cloning, and confirmed
    bar commits.
- `incremental.manager` provides reusable shared-session orchestration.
- `incremental.detection` decides whether a script should use incremental mode.

Public imports remain stable through `pyne_runtime.incremental` and the package
top level. These imports continue to work:

```python
from pyne_runtime.incremental import PyneIncrementalSession
from pyne_runtime import PyneIncrementalSession
```

