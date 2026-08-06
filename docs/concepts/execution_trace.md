# Execution Trace

Pyne can attach a bounded, structured execution trace to a result for local
diagnostics and host observability. Tracing is disabled by default.

```python
import pyne_runtime as pn

settings = pn.PyneSettings(
    trace_enabled=True,
    trace_max_events=500,
    trace_timings_enabled=True,
    trace_slow_span_ms=10.0,
)
result = pn.run(script, bars, settings=settings)
trace = result.meta["trace"]
```

Trace schema v2 has the configured `maxEvents`, a `droppedEvents` counter, an
ordered `events` list, redaction metadata, and a timing summary. Runtime spans
cover security validation, script execution, output collection, incremental
callbacks, and host-backed requests. Nested work carries `spanId` and
`parentSpanId`; the timing summary aggregates count, errors, total duration, and
maximum duration by span name. Up to 32 spans at or above
`trace_slow_span_ms` are retained as bounded slow-span evidence.

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

Fields whose normalized names contain `api_key`, `authorization`, `cookie`,
`password`, `secret`, or `token` are replaced with `[REDACTED]`, including in
nested mappings. Configure the exact case-insensitive field set with
`trace_redacted_fields` or `PYNE_TRACE_REDACTED_FIELDS`. Unsupported objects are
represented only by their type name; the recorder does not store their `repr`.

Timing uses a monotonic process clock and is diagnostic rather than
deterministic output. Disable only timing samples with
`trace_timings_enabled=False` while retaining ordered trace events. The
performance smoke gate records raw paired trace-enabled/disabled samples so the
opt-in overhead remains visible.

Tracing is diagnostic evidence, not a security audit log. Redaction is a bounded
field-name defense, not content inspection; scripts can still place sensitive
text under an innocuous key. Hosts should apply their normal retention and
access controls. A process killed by the hard timeout cannot return its
in-memory trace to the parent process.
