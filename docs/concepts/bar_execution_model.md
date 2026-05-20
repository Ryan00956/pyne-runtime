# Bar Execution Model

Pyne batch scripts expose a Pine-like bar clock as series values.

```python
plot(bar_index, "Bar Index")
plot(last_bar_index, "Last Bar Index")
plot(time[1], "Previous Time")
plot(time_close, "Bar Close Time")
```

Available clock values:

- `time`: chart bar timestamps as a series.
- `time_close`: chart bar close timestamps as a series.
- `bar_index`: zero-based bar index as a series.
- `last_bar_index`: the last available bar index as a series.
- `bar_count`: scalar number of input bars.

`time` follows the same history-reference rule as price series:

```python
time[1]  # previous bar timestamp
```

If input bars include `time_close`, Pyne preserves it. Otherwise batch mode infers
`time_close` from the next bar's `time`; the final bar is `na` because there is
no next bar from which to infer a close timestamp.

## `barstate`

The `barstate` namespace exposes batch-runtime flags as boolean series:

```python
marker(barstate.isfirst, text="First")
marker(barstate.islast, text="Last")
marker(barstate.isconfirmed, text="Confirmed")
```

Batch-mode fields:

- `barstate.isfirst`: true only on the first bar.
- `barstate.islast`: true only on the final input bar.
- `barstate.ishistory`: true for all batch bars.
- `barstate.isrealtime`: false for all batch bars.
- `barstate.isnew`: true for all batch bars.
- `barstate.isconfirmed`: true for all batch bars.
- `barstate.islastconfirmedhistory`: true on the final input bar.

These are represented as series, so they can be combined with other conditions:

```python
signal = barstate.isconfirmed & (close > close[1])
marker(signal, text="Confirmed Up")
```

Current scope:

- The batch runtime exposes deterministic historical barstate flags.
- Incremental callbacks expose scalar `ctx.bar_index`, `ctx.last_bar_index`, and `ctx.barstate` values for the bar currently being processed.
- Host-specific realtime state is supplied through the runtime/session layer, not inferred by indicators.

## Incremental Callbacks

Incremental scripts process one bar at a time with callback context values:

```python
def on_bar(ctx, bar):
    ctx.marker(ctx.barstate.isconfirmed, text="Confirmed")
    ctx.plot("Index", ctx.bar_index)
    ctx.plot("Bar Index", bar.bar_index)

def on_preview(ctx, bar):
    ctx.marker(ctx.barstate.isrealtime and not ctx.barstate.isconfirmed, text="Preview")
```

During `seed(ohlcv)`, bars are treated as historical:

- `ctx.bar_index` and `bar.bar_index` advance from zero.
- `ctx.last_bar_index` and `bar.last_bar_index` point to the final seeded bar.
- `ctx.barstate.ishistory`, `ctx.barstate.isnew`, and `ctx.barstate.isconfirmed` are true.
- `ctx.barstate.islastconfirmedhistory` is true only on the final seeded bar.

During `on_bar_updated(item)`, the bar is a realtime preview:

- `ctx.barstate.isrealtime` is true.
- `ctx.barstate.isconfirmed` and `ctx.barstate.ishistory` are false.
- `ctx.barstate.isnew` is true only for the first preview update seen for that bar time.
- Preview callbacks run on a cloned context, so state, TA helpers, windows, and output from the preview do not mutate the persistent session.

During `on_bar_closed(item)`, the realtime bar is confirmed and committed:

- `ctx.barstate.isrealtime` and `ctx.barstate.isconfirmed` are true.
- `ctx.barstate.ishistory` and `ctx.barstate.islastconfirmedhistory` are false because this is a live confirmation event, not seeded history.
- `ctx.barstate.isnew` is false if a preview for the same bar time was already seen; it is true when the closed bar is the first event for that bar.
- Persistent state advances only after this confirmed callback succeeds.

## Incremental Strategy State

Incremental callbacks also expose a scalar `ctx.strategy` namespace for Pine-like
strategy state that must evolve one committed bar at a time:

```python
def init(ctx):
    ctx.strategy.configure(initial_capital=1000)

def on_bar(ctx, bar):
    ctx.strategy.entry("A", ctx.strategy.long, qty=2, price=bar.close, when=ctx.bar_index == 0)
    ctx.strategy.close("A", qty=1, price=bar.close, when=ctx.bar_index == 2)
    ctx.plot("Position", ctx.strategy.position_size)
    ctx.plot("Equity", ctx.strategy.equity)
```

Current incremental strategy scope:

- `ctx.strategy.entry()` fills a market-like entry on the current callback bar.
- `ctx.strategy.entry(..., limit=...)` and `ctx.strategy.entry(..., stop=...)` create Pine-like pending entries that fill when the current or later callback bar touches the trigger price.
- `ctx.strategy.order()` supports the same market-like and pending entry surface for lower-level order-style submissions.
- `ctx.strategy.configure(slippage=..., commission_type=..., commission_value=...)` applies Pine-like slippage and commission accounting to market-like, pending, close, and exit fills.
- `ctx.strategy.configure(margin_long=..., margin_short=...)` applies the same deterministic margin gating as batch strategy: immediate fills that exceed available equity are rejected, while pending fills that touch price but exceed margin remain pending.
- `ctx.strategy.configure(backtest_fill_limits_assumption=...)`, `ctx.strategy.same_bar.*`, and `ctx.strategy.intrabar.*` control pending stop/limit fill policy.
- `ctx.strategy.cancel(id)` and `ctx.strategy.cancel_all()` cancel matching pending entries and report the same public cancel orders and lifecycle statuses as batch strategy.
- `ctx.strategy.oca.cancel` and `ctx.strategy.oca.reduce` are supported for pending entry/order groups.
- `ctx.strategy.close()` and `ctx.strategy.close_all()` realize all or part of the current open lots.
- `ctx.strategy.exit()` supports stop/limit exits for open positions, including `from_entry`, `qty`, `qty_percent`, and the same deterministic stop/limit priority policy.
- `ctx.strategy.risk.allow_entry_in()`, `max_drawdown()`, `max_intraday_loss()`, `max_position_size()`, and `max_intraday_filled_orders()` apply the same deterministic entry gating, position-size capping, risk-lock, rejection lifecycle, and `session.isfirstbar` reset model as batch strategy for committed bars.
- Long and short positions, `qty`/`qty_percent` partial closes, and reverse entries update the same order/trade report shape as batch strategy for basic market-like fills.
- `ctx.strategy.position_size`, `position_avg_price`, `equity`, `netprofit`, `openprofit`, `grossprofit`, and `grossloss` expose scalar values for the current bar.
- `result.output["strategy"]` includes `orders`, `position`, `summary`, `closedtrades`, `opentrades`, and lifecycle fill events.

The first parity contract is basic entry/close ledger equivalence: a seeded
incremental run and an `on_bar_closed()` session snapshot must produce identical
strategy output, and simple entry/close scripts match batch strategy position,
equity, net profit, orders, and trade ledgers. This contract now includes long
entries, short entries, partial closes, reverse entries, filled pending
stop/limit entries, unfilled pending lifecycle reports, and explicit pending
cancel/cancel_all reports, plus OCA cancel/reduce pending groups, immediate
per-bar exit calls, core risk rules, and slippage/commission cost accounting.
Margin enforcement is covered for committed-bar market-like and pending fills.
Persistent exit order lifecycle remains a batch strategy feature until it is
promoted into the incremental strategy layer. Pending fill policy parity covers
limit verification, same-bar stop/limit priority, and deterministic intrabar
path selection. Exit parity currently covers immediate per-bar stop/limit exit
calls; persistent exit order lifecycle is still a separate batch-only behavior.
