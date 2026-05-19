# PyneSettings

`PyneSettings` controls security, execution, and resource limits.

```python
settings = pn.PyneSettings(
    security_mode="safe",
    executor_mode="process",
    timeout_seconds=5,
    max_bars=50_000,
    max_drawing_objects=500,
    data_provider=None,
    syminfo={"tickerid": "NASDAQ:AAPL", "mintick": 0.01},
    timeframe="1h",
    session={"ismarket": True},
)
```

Environment-backed settings:

```python
settings = pn.PyneSettings.from_env()
```

Supported security modes:

- `safe`
- `research`
- `unsafe`

Supported executor modes:

- `inline`
- `process`

`data_provider` supplies host-backed OHLCV data for `request.security()`. The
process executor requires a pickleable provider; use `inline` for local adapters
that hold live connections or non-pickleable state.

Runtime metadata:

- `syminfo` supplies the Pine-like `syminfo` namespace. Supported fields include
  `ticker`, `tickerid`, `prefix`, `currency`, `basecurrency`, `mintick`,
  `pointvalue`, and `type`.
- `timeframe` supplies the Pine-like `timeframe` namespace. Common strings such
  as `"1"`, `"5"`, `"1h"`, `"1D"`, `"1W"`, and `"1M"` are parsed into
  `period`, `multiplier`, `isintraday`, `isdaily`, `isweekly`, and `ismonthly`.
- `session` supplies lightweight host-owned session flags: `ismarket`,
  `isfirstbar`, and `islastbar`.

`syminfo.mintick` defaults to `1.0`. Strategy slippage uses it when
`strategy(..., slippage=...)` does not pass an explicit `mintick` / `min_tick`.

The same metadata can be supplied directly to `pn.run(...)`:

```python
result = pn.run(
    script,
    data,
    syminfo={"tickerid": "NASDAQ:AAPL", "mintick": 0.01},
    timeframe="1h",
    session={"ismarket": True},
)
```

Environment variables are also supported for simple host launches:

- `PYNE_TICKERID`
- `PYNE_TICKER`
- `PYNE_SYMBOL_PREFIX`
- `PYNE_CURRENCY`
- `PYNE_BASE_CURRENCY`
- `PYNE_MINTICK`
- `PYNE_POINTVALUE`
- `PYNE_SYMBOL_TYPE`
- `PYNE_TIMEFRAME`

Object limits:

- `max_drawing_objects`: maximum active `line`, `label`, `box`, and `table`
  handles in one execution.
- Environment variable: `PYNE_MAX_DRAWING_OBJECTS`.

