# Execution Trace

Pyne can attach a bounded, structured execution trace to a result for local
diagnostics and host observability. Tracing is disabled by default.

```python
import pyne_runtime as pn

settings = pn.PyneSettings(
    trace_enabled=True,
    trace_max_events=500,
)
result = pn.run(script, bars, settings=settings)
trace = result.meta["trace"]
```

The trace document has its own `schemaVersion`, the configured `maxEvents`, a
`droppedEvents` counter, and an ordered `events` list. Runtime events include
execution lifecycle, incremental bar boundaries, state changes, incremental
plots and markers, request diagnostics, and strategy summaries where applicable.

Scripts can add JSON-like decision evidence:

```python
trace.emit("signal.decision", accepted=True, score=0.82)
```

Incremental callbacks can use either the active callback namespace or the
context directly:

```python
def on_bar(ctx, bar):
    ctx.trace.emit("signal.decision", time=bar.time, accepted=bar.close > bar.open)
```

Preview traces are cloned with preview state. Events produced by
`on_bar_updated()` appear in that preview result but do not enter the committed
session trace. The later `on_bar_closed()` callback records its own committed
events.

The event budget is strict. Once it is full, new events are discarded and
`droppedEvents` increases; script execution continues. Values are converted to
bounded JSON-like representations, with collection item and nesting limits.

Tracing is diagnostic evidence, not a security audit log. It may include values
that a script explicitly emits, so hosts should apply their normal retention and
access controls. A process killed by the hard timeout cannot return its in-memory
trace to the parent process.
