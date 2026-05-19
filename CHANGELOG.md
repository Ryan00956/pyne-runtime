# Changelog

## 0.1.0

- Initial standalone Pyne Runtime package scaffold.
- Added `PyneSettings` and standalone error helpers.
- Removed CandleScope `app.*` imports from package code.
- Added friendly API: `run`, `read_ohlcv`, `from_pandas`, `validate`, and `schema`.
- Added `PyneData`, CLI entry point, examples, and package tests.
- Added public API documentation, `result.py`, and schema version helpers.
- Added error code registry with standard hints and documentation URLs.
- Added documentation structure for quickstart, tutorials, concepts, API, and reference pages.
- Added package version access, `pyne --version`, CLI contract tests, and quality gate docs/scripts.
- Added packaged example execution coverage.
- Added `python -m pyne_runtime`, CLI parameter overrides, and CLI reference documentation.
- Added `PyneResult` series lookup helpers.
- Added `PyneData` column, row, head/tail, and range helpers.
- Split Pyne Runtime into an independent repository layout with CI metadata.
- Added `PyneSeries` with Pine-like history references such as `close[1]`.
- Added callable `na` semantics for missing-value checks and series-aware `nz()`.
- Added batch `bar_index`, `last_bar_index`, `time[1]`, and `barstate.*` semantics.
- Added runtime-scoped `var()` / `pyne.var()` state cells with carry-forward `set_each()`.
- Added series-aware `ta.cross`, `ta.dev`, `ta.variance`, `ta.mom`, `ta.linreg`, and `ta.hma`.
- Added series-aware `ta.alma`, `ta.swma`, `ta.correlation`, and rolling percentile helpers.
- Added series-aware `ta.cmo`, `ta.wpr`, `ta.tsi`, `ta.dmi`, and `ta.sar`.
- Added series-aware `when()` and `switch()` expression helpers.
- Added Pine-like `line` and `label` drawing object handles with final object snapshots.
- Added host-backed `request.security()` for aligned OHLCV field requests.
- Added Pine-like `strategy.*` event output with lightweight position replay.
- Added a Pine-like API compatibility matrix and broader semantics examples.
- Added `request.security()` callable expression thunks for requested-context calculations.
- Added Pine-like `box` and `table` drawing objects with drawing object limits.
- Added `strategy.exit()` stop/limit exit events for lightweight strategy replay.
- Added incremental `ctx.bar_index`, `bar.bar_index`, and scalar `ctx.barstate.*` realtime preview/confirmation semantics.
- Added optional OHLCV `time_close` support and batch `time_close` series inference.
- Added tuple/multi-return `request.security()` expressions for Python unpacking.
- Added `strategy.configure(pyramiding=...)` with same-direction entry limits and weighted average position price replay.
- Added partial `strategy.exit(qty=...)` position reduction semantics.
- Added Pine-like `strategy.configure(slippage=..., commission_type=..., commission_value=...)` replay costs.
