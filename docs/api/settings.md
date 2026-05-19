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

Object limits:

- `max_drawing_objects`: maximum active `line`, `label`, `box`, and `table`
  handles in one execution.
- Environment variable: `PYNE_MAX_DRAWING_OBJECTS`.

