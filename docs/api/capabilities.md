# Runtime Capabilities

Hosts should discover the runtime surface instead of assuming that batch and
incremental scripts expose the same functions.

```python
import pyne_runtime as pn

capabilities = pn.runtime_capabilities()
incremental_ta = capabilities["modes"]["incremental"]["ta"]
```

The returned document has its own `schemaVersion` and lists mode-specific TA,
request, strategy, drawing, callback, preview, and portable-snapshot support.
It also declares the pinned external-library registry, trace contract, language
boundary, and security boundary. Callers receive a defensive copy and may
modify it without changing the runtime.

The same document is embedded in `pn.schema()["runtimeCapabilities"]`. Hosts
can therefore obtain one complete integration bundle through `pyne schema`.

## Mode-Aware Validation

`pn.validate()` detects incremental mode from `indicator(...,
mode="incremental")` or an `on_bar()` callback. A host can also select the mode
explicitly:

```python
diagnostics = pn.validate(script, runtime_mode="incremental")
```

Statically discoverable unsupported calls such as `ctx.ta.hma()` return a
`PYNE_UNSUPPORTED_FEATURE` diagnostic at the call site. Incremental session
preparation applies the same check before processing any bar. Dynamic Python
attribute construction cannot always be proven statically and can still fail
at runtime.

The capability schema is an implemented-surface contract, not a claim that
Pyne parses Pine source or provides exhaustive TradingView compatibility.
