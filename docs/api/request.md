# Request API

`request` is the Pine-like namespace for host-backed data requests.

Pyne does not fetch exchange or broker data by itself. The host application
provides a data provider, and Pyne owns deterministic alignment back to the
chart bars.

The public request API is stable through both `pyne_runtime.request` and the
package top level. These imports continue to work:

```python
from pyne_runtime.request import (
    DataProvider,
    LowerTimeframeSeries,
    PyneInvalidSymbolError,
    PyneRequestError,
    RequestEvalContext,
    RequestModule,
    barmerge,
)
```

## Data Provider

A provider implements `get_ohlcv(symbol, timeframe, start, end)`:

```python
import pyne_runtime as pn


class MyProvider:
    def get_ohlcv(self, symbol, timeframe, start, end):
        if symbol not in self.supported_symbols:
            raise pn.PyneInvalidSymbolError(symbol)
        return [
            {"time": 1710000000, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100},
        ]
```

Pass it through `pn.run(..., data_provider=provider)` or
`PyneSettings(data_provider=provider)`.

```python
result = pn.run(
    """
indicator("Higher TF", overlay=True)
higher_close = request.security("BTCUSDT", "1h", lambda ctx: ctx.close)
plot(higher_close, "1h Close")
""",
    chart_bars,
    data_provider=provider,
    executor_mode="inline",
)
```

When using the process executor, the provider must be pickleable. For local host
adapters with open sockets, database handles, or closures, prefer
`executor_mode="inline"`.

Within one script run, Pyne caches requested contexts by
`(symbol, timeframe, start, end)`. Repeated `request.security()` or
`request.security_lower_tf()` calls for the same requested context reuse the
same provider OHLCV response and requested metadata, while each expression is
still evaluated independently. Pyne does not cache provider data across
separate `pn.run()` executions.

Providers may optionally declare request capabilities with either a
`capabilities` attribute or a `capabilities()` method:

```python
class MyProvider:
    capabilities = {"request.security": True, "request.security_lower_tf": True}

    def get_ohlcv(self, symbol, timeframe, start, end):
        ...
```

Accepted aliases:

- `request.security`, `security`, or `ohlcv` for `request.security()`
- `request.security_lower_tf`, `security_lower_tf`, or `lower_tf` for
  `request.security_lower_tf()`

If no capabilities are declared, Pyne assumes the provider can answer both
request types. If `capabilities` is `None`, Pyne treats the provider as
supporting no request capabilities. For dict capabilities, at least one matching
alias must be present and truthy. For list/set/tuple capabilities, the
capability must be present. If a `capabilities()` method or property raises,
Pyne returns `PYNE_RUNTIME_ERROR` with a request-capability-specific message.

Providers may also supply metadata for requested contexts. This is optional;
without it, Pyne uses the requested `symbol` as `syminfo.ticker` /
`syminfo.tickerid`, uses the requested `timeframe` as `timeframe.period`, and
derives session flags from requested bars.

```python
class MyProvider:
    def get_request_metadata(self, symbol, timeframe):
        return {
            "syminfo": {
                "tickerid": "BINANCE:BTCUSDT",
                "mintick": 0.01,
                "currency": "USDT",
                "type": "crypto",
            },
            "timeframe": timeframe,
            "session": {"ismarket": True},
        }
```

The same metadata can be exposed as a `request_metadata` mapping or
`request_metadata(symbol, timeframe)` method. Accepted keys are `syminfo` or
`symbol_info`, `timeframe` or `timeframe_info`, and `session` or
`session_info`. Bar-level session flags in requested OHLCV rows still override
the provider-level session default.

The provider contract is also exposed through `pn.schema()["requestProvider"]`.
That schema lists the required `get_ohlcv(...)` method, required OHLCV fields,
capability aliases, metadata keys, requested-context cache semantics, and
stable error categories.

## `request.security`

```python
request.security(
    symbol,
    timeframe,
    expression,
    gaps="off",
    lookahead="off",
    ignore_invalid_symbol=False,
)
```

Supported now:

- `expression` as an OHLCV field series, such as `close`, `high`, or `hlc3`
- history references on fields, such as `close[1]`
- `expression` as a field name string, such as `"close"`
- `expression` as a callable thunk, such as `lambda ctx: ctx.ta.ema(ctx.close, 20)`
- tuple/multi-return expressions that can be unpacked in Python
- `gaps="off"` or `gaps=barmerge.gaps_off`: carry the latest requested value forward
- `gaps="on"` or `gaps=barmerge.gaps_on`: only emit values on exact requested bar timestamps
- `lookahead="off"` or `lookahead=barmerge.lookahead_off`: use the latest requested bar at or before each chart bar
- `lookahead="on"` or `lookahead=barmerge.lookahead_on`: use the next requested bar at or after each chart bar
- `ignore_invalid_symbol=True`: return `na` values when the provider raises
  `pn.PyneInvalidSymbolError`

Pyne also accepts the string aliases `"gaps_on"`, `"gaps_off"`,
`"lookahead_on"`, `"lookahead_off"`, `"barmerge.gaps_on"`,
`"barmerge.gaps_off"`, `"barmerge.lookahead_on"`, and
`"barmerge.lookahead_off"`. Unknown `gaps` or `lookahead` values return
`PYNE_UNSUPPORTED_FEATURE` before the provider is called.

## Expression Thunks

Python evaluates function arguments before `request.security()` receives them.
That means Pyne cannot capture this expression for recalculation in the
requested context:

```python
request.security("BTCUSDT", "1h", ta.ema(close, 20))  # unsupported
```

Use a callable expression thunk instead:

```python
higher_ema = request.security(
    "BTCUSDT",
    "1h",
    lambda ctx: ctx.ta.ema(ctx.close, 20),
)
```

The `ctx` object is a calculation-only requested context. It exposes:

- `ctx.open`, `ctx.high`, `ctx.low`, `ctx.close`, `ctx.volume`
- `ctx.time`, `ctx.time_close`, `ctx.bar_index`, `ctx.last_bar_index`, `ctx.barstate`
- `ctx.hl2`, `ctx.hlc3`, `ctx.ohlc4`, `ctx.hlcc4`
- `ctx.syminfo`, `ctx.timeframe_info`, `ctx.session`
- `ctx.ta`
- `ctx.when()`, `ctx.where()`, `ctx.switch()`

History references inside the thunk are applied in the requested context:

```python
higher_prev = request.security("BTCUSDT", "1h", lambda ctx: ctx.close[1])
```

Callable expressions may return a single series-like value, a scalar, or a tuple
of series-like values:

```python
higher_open, higher_close = request.security(
    "BTCUSDT",
    "1h",
    lambda ctx: (ctx.open, ctx.close),
)
```

Field tuples are also supported:

```python
higher_high, higher_low = request.security("BTCUSDT", "1h", ("high", "low"))
```

Dicts, object handles, and nested request outputs are rejected.

Unsupported for now:

- direct capture of already evaluated Python expressions, such as `ta.ema(close, 20)`
- nested request expressions
- provider-owned lookahead or gap semantics

If no data provider is configured, `request.security()` returns a
`PYNE_UNSUPPORTED_FEATURE` error.

If a provider raises `pn.PyneInvalidSymbolError`, the default behavior is a
`PYNE_INVALID_SYMBOL` error. With `ignore_invalid_symbol=True`, Pyne returns
`na` values for that request. Other provider exceptions are not treated as
invalid symbols; Pyne wraps them as `PYNE_RUNTIME_ERROR` with a
`request data provider failed` message.

If provider metadata is not a mapping, or a metadata callback raises, Pyne also
returns `PYNE_RUNTIME_ERROR` with a request-metadata-specific message.

## `request.security_lower_tf`

```python
request.security_lower_tf(symbol, timeframe, expression, ignore_invalid_symbol=False)
```

`request.security_lower_tf()` requests lower-timeframe OHLCV from the same host
provider and returns an array-per-chart-bar object. Pyne evaluates the
expression in the requested lower-timeframe context, then groups requested bars
into chart-bar buckets using `[chart_time, next_chart_time)`.

```python
lower = request.security_lower_tf("BTCUSDT", "1", lambda ctx: ctx.close)
plot(lower.size(), "Lower TF Count")
plot(lower.last(), "Lower TF Last Close")
plot(lower.max(), "Lower TF High")
```

Supported now:

- field expressions such as `close`, `"close"`, or `("high", "low")`
- callable thunks such as `lambda ctx: ctx.ta.sma(ctx.close, 3)`
- tuple/multi-return expressions
- bars-back on the grouped result, such as `lower[1].last()`
- `ignore_invalid_symbol=True`: return empty lower-timeframe groups when the
  provider raises `pn.PyneInvalidSymbolError`

The returned object exposes:

- `.to_lists()`: Python lists of requested values per chart bar
- `.size()`: number of lower-timeframe bars per chart bar
- `.first(default=na)`: first grouped value per chart bar
- `.last(default=na)`: last grouped value per chart bar
- `.get(index, default=na)`: value at a zero-based index in each group
- `.sum(default=na)`, `.min(default=na)`, `.max(default=na)`, `.avg(default=na)`:
  numeric aggregations for each group

Provider capability negotiation uses the same mechanism described above. If the
provider explicitly disables lower-timeframe requests or omits the capability
from a list/set declaration, Pyne returns `PYNE_UNSUPPORTED_FEATURE` without
calling `get_ohlcv(...)`.

## Golden Coverage

The request test suite includes deterministic fixtures for:

- higher-timeframe `gaps` and `lookahead` alignment
- history references evaluated in the requested context
- tuple field expressions and tuple callable thunks
- requested-context `time_close`, `session.*`, and `timeframe_info.*` isolation
  from chart metadata in both higher-timeframe and lower-timeframe requests
- lower-timeframe `[chart_time, next_chart_time)` grouping
- empty lower-timeframe buckets and aggregation defaults
- invalid-symbol ignore behavior and provider capability rejection before
  provider calls
- requested-context cache reuse within one script run and cache reset across
  separate `pn.run()` executions
- provider failure and provider metadata contract failures

## Internal Responsibilities

The request implementation is split into focused helpers while keeping the same
public namespace:

- `request.provider` defines the provider protocol, capability checks, and
    requested metadata defaults.
- `request.eval` owns `RequestEvalContext`, field lookup, history references,
    callable expression thunks, and expression-result normalization.
- `request.alignment` owns `barmerge` constants plus gaps/lookahead alignment.
- `request.lower_tf` owns lower-timeframe grouping and numeric aggregations.
- `request.errors` owns stable request exception types and error codes.
- `request.module` keeps the user-facing `RequestModule` facade, provider
    calls, requested-context caching, and error conversion.

This boundary keeps provider integration, expression evaluation, bar alignment,
and lower-timeframe grouping independently testable without changing script
syntax or result shape.
