# Public API

Pyne Runtime keeps a small public API surface at the package root.

Stable imports:

```python
import pyne_runtime as pn

pn.run
pn.read_ohlcv
pn.from_pandas
pn.validate
pn.schema
pn.__version__

pn.PyneData
pn.PyneBarState
pn.PyneResult
pn.PyneSettings
pn.PyneSeries
pn.PyneStateNamespace
pn.PyneVar
pn.PyneRuntime
pn.SymbolInfo
pn.TimeframeInfo
pn.SessionInfo
pn.DataProvider
pn.RequestEvalContext
pn.RequestModule
pn.StrategyModule

pn.execute_pyne_script
pn.execute_pyne_script_in_process
```

Version constants:

```python
pn.__version__
pn.PYNE_INPUT_SCHEMA_VERSION
pn.PYNE_OUTPUT_SCHEMA_VERSION
pn.na
```

`PyneSeries` is the script-facing series value used for Pine-like history references such as `close[1]`.
`pn.na` is the callable missing-value sentinel also injected into scripts as `na`.
`PyneBarState` is the batch-runtime namespace type behind script-level `barstate.*` flags.
`PyneVar` and `PyneStateNamespace` power script-level `var()` / `pyne.var()` state cells.
`SymbolInfo`, `TimeframeInfo`, and `SessionInfo` back the script-level
`syminfo`, `timeframe`, and `session` namespaces.
`DataProvider` is the host protocol for `request.security()` market data access.
`RequestEvalContext` is the calculation-only context passed to `request.security()` expression thunks.
`StrategyModule` is the script-level `strategy.*` event namespace.

Internal helpers and non-exported functions are not part of the compatibility contract.

`PyneResult` also exposes convenience helpers for common series access:

```python
result.series_names
result.get_series("Close")
result.values("Close")
result.latest("Close")
```
