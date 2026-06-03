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
pn.SessionNamespace
pn.DataProvider
pn.OHLCVBar
pn.REQUEST_METADATA_KEY_ALIASES
pn.REQUEST_METADATA_SESSION_KEYS
pn.REQUEST_METADATA_SYMBOL_KEYS
pn.REQUEST_METADATA_TIMEFRAME_KEYS
pn.REQUEST_API_VALUES
pn.REQUEST_SECURITY_API
pn.REQUEST_SECURITY_CAPABILITY_ALIASES
pn.REQUEST_SECURITY_LOWER_TF_API
pn.REQUEST_SECURITY_LOWER_TF_CAPABILITY_ALIASES
pn.RequestCapabilities
pn.RequestCapabilityProvider
pn.RequestMetadata
pn.RequestMetadataProvider
pn.RequestSessionMetadata
pn.RequestSymbolMetadata
pn.RequestTimeframeMetadata
pn.PyneInvalidSymbolError
pn.PyneRequestError
pn.RequestEvalContext
pn.RequestModule
pn.barmerge
pn.StrategyModule

pn.execute_pyne_script
pn.execute_pyne_script_in_process
```

Version constants:

```python
pn.__version__
pn.PYNE_INPUT_SCHEMA_VERSION
pn.PYNE_OUTPUT_SCHEMA_VERSION
pn.PYNE_PARAM_SCHEMA_VERSION
pn.PYNE_REQUEST_PROVIDER_SCHEMA_VERSION
pn.na
pn.nz
pn.fixnan
```

`PyneSeries` is the script-facing series value used for Pine-like history references such as `close[1]`.
`pn.na` is the callable missing-value sentinel also injected into scripts as `na`.
`pn.nz` and `pn.fixnan` expose the same missing-value helpers available to
scripts as `nz()` and `fixnan()`.
`PyneBarState` is the batch-runtime namespace type behind script-level `barstate.*` flags.
`PyneVar` and `PyneStateNamespace` power script-level `var()` / `pyne.var()` state cells.
`SymbolInfo`, `TimeframeInfo`, `SessionInfo`, and `SessionNamespace` back the
script-level `syminfo`, `timeframe`, and `session` namespaces.
`DataProvider` is the host protocol for `request.security()` market data access.
`OHLCVBar`, `REQUEST_METADATA_KEY_ALIASES`,
`REQUEST_METADATA_SESSION_KEYS`, `REQUEST_METADATA_SYMBOL_KEYS`,
`REQUEST_METADATA_TIMEFRAME_KEYS`, `REQUEST_API_VALUES`,
`REQUEST_SECURITY_API`, `REQUEST_SECURITY_CAPABILITY_ALIASES`,
`REQUEST_SECURITY_LOWER_TF_API`,
`REQUEST_SECURITY_LOWER_TF_CAPABILITY_ALIASES`, `RequestCapabilities`,
`RequestMetadata`, and related provider protocols are typing helpers for host
data adapters.
`PyneInvalidSymbolError` is the provider-side signal used by
`ignore_invalid_symbol=True`.
`PyneRequestError` is the stable runtime request error type used by host-backed
request adapters.
`RequestEvalContext` is the calculation-only context passed to `request.security()` expression thunks.
`pn.barmerge` exposes Pine-like request alignment constants such as
`pn.barmerge.gaps_on` and `pn.barmerge.lookahead_off`.
`StrategyModule` is the script-level `strategy.*` event namespace.

Internal helpers and non-exported functions are not part of the compatibility contract.

`PyneResult` also exposes convenience helpers for common series access:

```python
result.series_names
result.get_series("Close")
result.values("Close")
result.latest("Close")
```
