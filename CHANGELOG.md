# Changelog

## Unreleased

- Added output, parameter, request provider, strategy report, and script
  namespace schema contracts for host integrations.
- Added request provider schema v4 structured error categories for host
  diagnostics.
- Added `errorDetail.requestProviderCategory` for request provider failures.
- Added `meta.requestDiagnostics` for successful request calls and cache-hit
  visibility.
- Added `errorDetail.requestProviderRequest` for failed request coordinates.
- Added schema migration policy, release process guidance, documentation index,
  and host integration guide.
- Added host output contract and parameter schema examples.
- Added an examples README that maps packaged examples to their contract focus.
- Added package smoke coverage for built wheels, `py.typed`, CLI entry points,
  packaged examples, and schema output.
- Added public request-provider typing helpers and script namespace drift tests.

## 0.1.0

- Initial standalone Pyne Runtime package scaffold.
- Added `PyneSettings` and standalone error helpers.
- Removed CandleScope `app.*` imports from package code.
- Added friendly API: `run`, `read_ohlcv`, `from_pandas`, `validate`, and `schema`.
- Added `PyneData`, CLI entry point, examples, and package tests.
- Added public API documentation, `result.py`, and schema version helpers.
- Added error code registry with standard hints and documentation URLs.
- Added documentation structure for quickstart, tutorials, concepts, API, and reference pages.
- Added script namespace schema metadata for host editor autocomplete.
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
- Added public provider typing helpers for host request adapters.
- Added `strategy.configure(pyramiding=...)` with same-direction entry limits and weighted average position price replay.
- Added partial `strategy.exit(qty=...)` position reduction semantics.
- Added Pine-like `strategy.configure(slippage=..., commission_type=..., commission_value=...)` replay costs.
- Added callable `strategy(...)` declarations for Pine-like strategy metadata and replay configuration.
- Added Pine-like `strategy.order()`, `strategy.order_when()`, and `strategy.close_all()` strategy events.
- Added lightweight pending `strategy.entry/order` stop-limit triggers plus `strategy.cancel()` and `strategy.cancel_all()`.
- Added lightweight `strategy.oca.cancel` handling for pending entry/order groups.
- Added lightweight `strategy.oca.reduce` quantity reduction for pending entry/order groups.
- Reorganized internal runtime architecture into focused `strategy`, `incremental`,
  `request`, and `plot` subpackages, plus a namespace registry, without public
  API breaking changes.
