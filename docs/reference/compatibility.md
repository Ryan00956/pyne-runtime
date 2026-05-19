# Compatibility

Pyne Runtime is currently pre-1.0.

Compatibility goals:

- Patch versions should not break public root imports.
- Minor versions may add new public APIs.
- Breaking changes should be documented in `CHANGELOG.md`.
- `pn.__version__` follows the installed package version.

Stable root imports are documented in [Public API](../api/public_api.md).
The detailed Pine-like feature matrix lives in
[Pine-Like API Matrix](pine_like_api_matrix.md).

The output schema has its own version: `PYNE_OUTPUT_SCHEMA_VERSION`.

## Pine-Like Surface

Supported:

- `close[1]` and other non-negative bars-back history references.
- `na`, `nz()`, `when()`, and `switch()` helpers for Python-friendly series logic.
- `bar_index`, `last_bar_index`, and `barstate.*` in batch execution.
- `var()` / `pyne.var()` state cells.
- `line` and `label` drawing object handles.
- `box` and `table` drawing object handles.
- `request.security()` for host-backed OHLCV field requests and callable expression thunks.
- `strategy.entry_when()` and `strategy.close_when()` event output.

Known differences:

- Pyne scripts are Python, not TradingView Pine source code.
- Python `if` cannot branch directly on a series; use `when()` or `switch()`.
- `request.security()` cannot capture already evaluated Python expressions such
  as `ta.ema(close, 20)`; use `lambda ctx: ctx.ta.ema(ctx.close, 20)`.
- Strategy support emits deterministic events and a lightweight position
  timeline; it is not a full broker simulator.
