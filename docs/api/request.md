# Request API

`request` is the Pine-like namespace for host-backed data requests.

Pyne does not fetch exchange or broker data by itself. The host application
provides a data provider, and Pyne owns deterministic alignment back to the
chart bars.

## Data Provider

A provider implements `get_ohlcv(symbol, timeframe, start, end)`:

```python
class MyProvider:
    def get_ohlcv(self, symbol, timeframe, start, end):
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

## `request.security`

```python
request.security(symbol, timeframe, expression, gaps="off", lookahead="off")
```

Supported now:

- `expression` as an OHLCV field series, such as `close`, `high`, or `hlc3`
- history references on fields, such as `close[1]`
- `expression` as a field name string, such as `"close"`
- `expression` as a callable thunk, such as `lambda ctx: ctx.ta.ema(ctx.close, 20)`
- tuple/multi-return expressions that can be unpacked in Python
- `gaps="off"`: carry the latest requested value forward
- `gaps="on"`: only emit values on exact requested bar timestamps
- `lookahead="off"`: use the latest requested bar at or before each chart bar
- `lookahead="on"`: use the next requested bar at or after each chart bar

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
