# Pine-Like API Matrix

Pyne is a Python runtime with Pine-like semantics. It does not run TradingView
Pine source code directly. This matrix tracks the supported mental model, the
Pyne API surface, and the test/doc evidence behind each claim.

| Feature | Pyne API | Status | Known Differences | Tests | Docs |
| --- | --- | --- | --- | --- | --- |
| OHLCV sources | `open`, `high`, `low`, `close`, `volume` | Supported | Values are `PyneSeries`, not Pine native series | `tests/test_series.py` | `docs/concepts/data_model.md` |
| History references | `close[1]`, `high[2]` | Supported | Negative indexes are rejected; Python positional indexing uses `.values`/NumPy internally | `tests/test_series.py` | `docs/concepts/series_semantics.md` |
| Series arithmetic | `high + low`, `(close - open) / open` | Supported | Python operator precedence applies | `tests/test_series.py` | `docs/concepts/series_semantics.md` |
| Series comparisons | `close > open` | Supported | Use `&`, `|`, `~` for boolean composition | `tests/test_series.py` | `docs/concepts/expression_helpers.md` |
| Series conditionals | `when(cond, a, b)`, `switch(...)` | Supported | Python ternary and `if` cannot branch on a series | `tests/test_expression_helpers.py` | `docs/concepts/expression_helpers.md` |
| Missing values | `na`, `na(x)`, `nz(x, fallback)` | Supported | `na` is a callable sentinel object in Python | `tests/test_na_semantics.py` | `docs/concepts/na_semantics.md` |
| Bar clock | `bar_index`, `last_bar_index`, `time`, `time_close`; incremental `ctx.bar_index`, `bar.bar_index` | Supported | Batch runtime exposes full-series values; inferred final `time_close` is `na` when not supplied; incremental callbacks expose scalar current-bar values | `tests/test_barstate.py`, `tests/test_incremental.py` | `docs/concepts/bar_execution_model.md` |
| Bar flags | `barstate.isfirst`, `barstate.islast`, `barstate.isconfirmed`; incremental `ctx.barstate.*` | Supported | Incremental preview state is runtime-event based; exact market-session open/closed inference is host responsibility | `tests/test_barstate.py`, `tests/test_incremental.py` | `docs/concepts/bar_execution_model.md` |
| Runtime metadata | `syminfo.mintick`, `syminfo.tickerid`, `timeframe.period`, `timeframe.multiplier`, `session.ismarket` | Supported | Metadata is supplied by the host or `PyneSettings`; batch `session.*` flags are series, while incremental `ctx.session.*` flags are current-bar scalars | `tests/test_metadata_runtime.py`, `tests/test_incremental.py` | `docs/api/settings.md` |
| Runtime state | `var()`, `pyne.var()`, `set_each()` | Supported | Full Pine `:=` recursive assignment is represented through explicit state cells | `tests/test_state_runtime.py` | `docs/concepts/state_semantics.md` |
| Core TA | `ta.sma`, `ta.ema`, `ta.rsi`, `ta.macd`, `ta.bb`, `ta.atr` | Supported | Numerical parity is best-effort unless covered by tests | `tests/test_ta_runtime.py` | `docs/api/ta.md` |
| Expanded TA | `ta.alma`, `ta.hma`, `ta.swma`, `ta.dmi`, `ta.sar`, percentiles | Supported | Some edge behavior may differ from TradingView until goldens exist | `tests/test_ta_runtime.py` | `docs/api/ta.md` |
| Plot output | `plot`, `hline`, `fill`, `marker`, `bgcolor`, `barcolor` | Supported | Output is a host-renderable JSON schema | `tests/test_plot_runtime.py` | `docs/api/plot.md` |
| Drawing objects | `line.new`, `label.new`, `box.new`, `table.new`, setters, `delete()` | Supported | Output is final snapshot; richer incremental object event streams are planned | `tests/test_plot_runtime.py` | `docs/concepts/drawing_objects.md` |
| Alerts/signals | `alertcondition`, `emit_signal` | Supported | Emits structured events; does not register TradingView alerts | `tests/test_plot_runtime.py` | `docs/api/plot.md` |
| Multi-context data | `request.security(symbol, timeframe, lambda ctx: ctx.ta.sma(ctx.close, 20))`; tuple thunks such as `lambda ctx: (ctx.open, ctx.close)` | Partial | Requires host provider; direct Python expression capture is impossible, so computed expressions use callable thunks | `tests/test_request_security.py` | `docs/api/request.md` |
| Strategy events | `strategy(...)`, `strategy.entry_when`, `strategy.order_when`, `strategy.cancel`, `strategy.cancel_all`, `strategy.close_all`, `strategy.exit(qty=...)`, `strategy.oca.cancel`, `strategy.oca.reduce` | Partial | Deterministic replay layer only; no broker simulation, margin, or intrabar path | `tests/test_strategy_runtime.py` | `docs/api/strategy.md` |
| Strategy reporting | `strategy.equity`, `strategy.netprofit`, `strategy.openprofit`, `strategy.grossprofit`, `strategy.grossloss`; `strategy.closedtrades.profit(0)`, `strategy.opentrades.entry_price(0)`; output `summary`, `closedtrades`, `opentrades` | Partial | Trade ledgers track entry lots, but position replay is still deterministic net-position based rather than a full broker emulator | `tests/test_strategy_runtime.py` | `docs/api/strategy.md` |
| Strategy risk | `strategy.risk.allow_entry_in(strategy.direction.long)`, `strategy.risk.max_drawdown(20, strategy.percent_of_equity)`, `strategy.risk.max_intraday_loss(5, strategy.cash)` | Partial | Risk rules are deterministic replay logic; drawdown locks globally, intraday loss resets at `session.isfirstbar`, and neither models broker liquidation or margin | `tests/test_strategy_runtime.py` | `docs/api/strategy.md` |
| Public package API | `pn.run`, `pn.PyneRuntime`, `pn.PyneSettings` | Supported | Pre-1.0 minor versions may still add APIs | `tests/test_api.py` | `docs/api/public_api.md` |
| CLI | `pyne run`, `pyne schema`, `pyne validate` | Supported | CLI executes Pyne Python scripts, not Pine source files | `tests/test_cli.py`, `tests/test_cli_contracts.py` | `docs/reference/cli.md` |

## Planned Gaps

- Richer incremental drawing object event streams.
- More formal fill models, margin, and intrabar path modeling.
- A larger golden-test suite against known Pine outputs.
