# Changelog

## Unreleased

- Added a versioned, mode-aware runtime capability contract through
  `pn.runtime_capabilities()` and `pn.schema()`, with early diagnostics for
  unsupported incremental TA/request calls.
- Expanded incremental TA with `rma`, `wma`, `vwma`, `variance`, `stdev`,
  `stoch`, `cci`, `supertrend`, `hma`, `dmi`, `adx`, `sar`, `mfi`, `vwap`,
  `barssince`, `valuewhen`, `crossover`, `crossunder`, and `cross`, including
  batch parity and portable-restore coverage.
- Expanded the pinned `TradingView/ta/10` adapter to nine reviewed members,
  including dynamic-length `ema2`, `rma2`, and `atr2`; only the two volume
  members declare authoritative lower-timeframe host-data requirements.
- Added `pn.inspect_script()` and `pyne inspect` for source-free hashes,
  mode-aware capability requirements, compatibility diagnostics, external
  library demand, and host-resource hints before execution.
- Added portable typed-state snapshot v2 as an opt-in cross-process restore
  format that omits replay history, uses a fixed runtime type allowlist, and
  fails closed for arbitrary user types. Replay snapshot v1 remains the default.
- Added opt-in bounded execution trace schema v2 with hierarchical timing
  spans, slow-span summaries, configurable field redaction, preview isolation,
  dropped-event accounting, and script-defined decision events.
- Added corpus demand reports for the next incremental TA and external-library
  candidates without executing or copying Pine source.
- Stabilized the portable-restore performance gate with alternating paired
  measurements and retained raw samples, plus typed-state-v2/replay-v1 restore
  and trace-v2 overhead comparisons.
- Converged batch and incremental strategy order lifecycle serialization on a
  shared core and added a full lifecycle parity scenario.
- Isolated ordinary execution and incremental-session caches by default while
  retaining an explicit host-owned shared execution scope.
- Added typed provider error categories and a test-runner-independent provider
  conformance kit; bumped the request-provider schema to version 10.
- Added bounded TTL/LRU incremental session management, rolling history
  retention, and process-local snapshot/restore with fail-closed state checks.
- Added output schema version 2 with `plotcandle`, linefill and polyline drawing
  objects, and validated merged table cells; output schema version 1 remains a
  documented legacy fallback.
- Added a fail-closed pinned external-library registry and the project-required
  `TradingView/ta/10#requestUpAndDownVolume` adapter backed by authoritative
  host lower-timeframe OHLCV.
- Added a reusable batch/incremental parity runner with normalized semantic
  output comparisons and assertion-ready difference reports.
- Completed incremental Render IR v2 coverage for candles, line fills,
  polylines, merged table cells, lifecycle events, retention, and preview
  isolation.
- Added incremental `request.security()` and `request.security_lower_tf()`
  support with typed diagnostics, bounded provider-range caching, and batch
  parity coverage.
- Added deterministic, checksummed, size/depth/node-bounded portable session
  snapshots with fresh-process restore, script/settings validation, and
  fail-closed provider and retained-history requirements.
- Added multi-session scaling, bounded-memory, snapshot/restore performance,
  and stability smoke gates.
- Split plot namespace/value assembly and TA numerical kernels into focused
  internal modules without changing the public package API.

## 0.2.0rc1 - 2026-07-20

- Added a tag-gated GitHub Release workflow that publishes the universal wheel,
  source distribution, changelog-derived notes, and SHA-256 checksums after an
  installed-wheel smoke test.
- Updated the official checkout and Python setup actions to their Node 24
  releases so CI and release jobs do not rely on deprecated Node 20 runner
  compatibility.
- Added a generated current-status contract backed by package metadata and the
  request, strategy, and TA capture inventories, with fail-closed drift and
  parity checks in local and CI quality gates.
- Unified the local and CI release-candidate gates around source compilation,
  lint, tests, external-capture parity, distribution validation, and installed
  wheel smoke checks, and routed superseded execution plans to the current
  capability and roadmap document.
- Hardened incremental previews by isolating mutable function defaults and
  script namespace attributes, safely rejecting closure/class and stateful
  external-module state, enforcing monotonic preview/close event times, and
  making custom parameter objects copy-on-read.
- Fixed incremental `highest()` and `lowest()` helpers so missing values advance
  the rolling window without poisoning later extrema.
- Fixed request-provider fetch windows with bounded four-times adaptive widening
  (at most six widenings) across weekends and market halts, final-range
  diagnostics/cache semantics, and complete final
  `request.security_lower_tf()` chart buckets for variable calendar intervals.
- Fixed lowercase minute timeframe suffixes such as `15m` being interpreted as
  months, and reject negative string history offsets as unsupported forward
  references.
- Restored request error precedence so missing providers, unsupported
  capabilities, nesting, and request options are checked before field-history
  expressions are parsed.
- Added request provider schema v9 fetch-window semantics while keeping the
  inclusive `get_ohlcv(symbol, timeframe, start, end)` signature.
- Added a TradingView parity capture for lower-timeframe
  `request.security_lower_tf()` grouping and request capture tooling for
  lower-TF provider bar slots.
- Added a TradingView parity capture for requested-context
  `request.security()` `time_close` behavior.
- Added a TradingView parity capture for requested-context `request.security()`
  `syminfo`, `timeframe`, and `session` metadata.
- Added a TradingView parity capture for `request.security()` gaps/lookahead
  combinations.
- Added a TradingView parity capture for `request.security()` daily-context
  requested `time_close` and non-intraday timeframe metadata.
- Added a TradingView parity capture for `request.security()` session-flags
  requested-context `session.ismarket`, `session.isfirstbar`, and
  `session.islastbar`.
- Added a prepared `request.security()` timezone TradingView capture fixture for
  requested-context UTC and Asia/Shanghai hour and day-of-week components.
- Fixed batch session metadata so explicit per-bar `session_isfirstbar=False`
  or `session_islastbar=False` values are not overwritten by default first/last
  loaded-bar fallbacks.
- Added strategy trade `profit_percent()` accessors.
- Added strategy trade `entry_comment()` and `exit_comment()` accessors.
- Tested environment-configured collection resource limits.
- Documented and tested nested incremental collection history snapshots.
- Documented and tested empty-array pop/shift errors.
- Rejected negative `array.new_*()` constructor sizes.
- Rejected recursive collection values at mutation time.
- Exported `pn.nz` and `pn.fixnan` as public missing-value helpers.
- Added top-level Pine-like `fixnan()` script helper.
- Added Pine-like `math.fixnan()` helper.
- Added Pine-like typed matrix constructors for bool, string, and color values.
- Added Pine-like `array.sort_indices()` helper.
- Added Pine-like `map.put_all()` merge helper.
- Added output, parameter, request provider, strategy report, and script
  namespace schema contracts for host integrations.
- Added request provider schema v4 structured error categories for host
  diagnostics.
- Added `errorDetail.requestProviderCategory` for request provider failures.
- Added `meta.requestDiagnostics` for successful request calls and cache-hit
  visibility.
- Added `errorDetail.requestProviderRequest` for failed request coordinates.
- Documented and tested stable request exception metadata.
- Added lower-timeframe request diagnostics and error-detail golden coverage.
- Added request provider schema v7 `supportedApis` discovery metadata.
- Exported request capability alias constants for host adapters.
- Exported request metadata key alias constants for host adapters.
- Exported canonical request API name constants for host adapters.
- Added request metadata key alias golden coverage.
- Added request capability alias golden coverage.
- Aligned dict capability alias checks with schema truthy-alias semantics.
- Added lower-timeframe ignored-invalid-symbol cache coverage.
- Added lower-timeframe repeated-request cache diagnostics coverage.
- Added lower-timeframe cross-run cache boundary coverage.
- Added lower-timeframe metadata error-detail golden coverage.
- Added lower-timeframe provider data error-detail golden coverage.
- Added lower-timeframe tuple thunk expression golden coverage.
- Added a runnable request provider contract example and refreshed host request
  tutorial coverage.
- Documented and tested provider bar sorting before request alignment/grouping.
- Added lower-timeframe expression failure request-context golden coverage.
- Added lower-timeframe invalid thunk and nested request rejection coverage.
- Added lower-timeframe provider availability error-detail golden coverage.
- Added lower-timeframe capability failure error-detail golden coverage.
- Fixed request providers returning `None` so `ignore_invalid_symbol=True` no
  longer hides invalid return-type contract failures.
- Aligned request provider schema wording for invalid return types with
  `ignore_invalid_symbol` behavior.
- Added successful empty-data request diagnostics coverage for both
  higher-timeframe and lower-timeframe requests.
- Added empty-data requested-context cache reuse coverage across request shapes.
- Clarified request provider schema and docs for empty-result cache semantics.
- Refreshed the Pine-like API matrix request-provider contract notes.
- Documented empty-result request cache semantics in compatibility references.
- Added incremental preview-created drawing object isolation coverage.
- Added incremental strategy preview pending-order isolation coverage.
- Documented incremental preview output as temporary overlay state.
- Aligned incremental marker size output with batch marker output.
- Added incremental marker `shape` and `location` enum namespaces.
- Aligned incremental histogram plot output with batch `plot.style_columns`.
- Aligned incremental styled line plot output with batch plot output.
- Aligned incremental default plot and marker panes with indicator overlay.
- Documented incremental committed plot and marker output convergence.
- Assigned stable suffixed input schema keys for repeated input titles.
- Added Pine-like `math.round(..., precision=...)` and `math.trunc()`.
- Added timezone-first `time.timestamp(...)` compatibility.
- Added Pine-like `str.match()` regex matching helper.
- Added series-aware `color.r/g/b/t()` channel helpers.
- Added Pine-like `order.ascending` / `order.descending` for `array.sort()`.
- Added Pine-like `array.first()` and `array.last()` helpers.
- Added schema migration policy, release process guidance, documentation index,
  and host integration guide.
- Added host output contract and parameter schema examples.
- Added an examples README that maps packaged examples to their contract focus.
- Added package smoke coverage for built wheels, `py.typed`, CLI entry points,
  packaged examples, and schema output.
- Added public request-provider typing helpers and script namespace drift tests.
- Narrowed public `data_provider` type hints to the request `DataProvider`
  protocol.
- Added public API documentation drift coverage for package-root exports.
- Made full package check scripts use a repository-local temporary root and
  non-isolated local builds.
- Added an offline package smoke mode for package-index-restricted environments.

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
