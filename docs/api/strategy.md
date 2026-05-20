# Strategy API

`strategy` is the Pine-like namespace for deterministic strategy events.

The current implementation is an event and position semantics layer. It is not
a broker simulator and does not model order books, margin, or intrabar path.

```python
strategy(
    "Trend Strategy",
    overlay=True,
    pyramiding=1,
    slippage=2,
    mintick=0.01,
    commission_type=strategy.commission.percent,
    commission_value=0.1,
    backtest_fill_limits_assumption=1,
    margin_long=100,
    margin_short=100,
)

fast = ta.ema(close, 12)
slow = ta.ema(close, 26)

strategy.entry_when(ta.cross(fast, slow), "Long", strategy.long, qty=1)
strategy.close_when(ta.cross(slow, fast), "Long")
strategy.exit("Long Exit", from_entry="Long", stop=close * 0.95, limit=close * 1.05)
strategy.cancel("Long", when=barstate.islast)
strategy.close_all(when=barstate.islast, comment="End")

plot(strategy.position_size, "Position")
plot(strategy.equity, "Equity")
```

## Direction Constants

- `strategy.long`
- `strategy.short`
- `strategy.direction.all`
- `strategy.direction.long`
- `strategy.direction.short`
- `strategy.direction.none`

## OCA Constants

- `strategy.oca.none`
- `strategy.oca.cancel`
- `strategy.oca.reduce`

The current replay model implements `strategy.oca.cancel` and
`strategy.oca.reduce` for pending `strategy.entry*` and `strategy.order*`
orders. In a reduce group, a filled order reduces sibling pending quantities by
the filled quantity; siblings reduced to zero are canceled.

## Configuration

Prefer the Pine-like declaration form:

```python
strategy(
    "My Strategy",
    overlay=True,
    pyramiding=1,
    slippage=2,
    mintick=0.01,
    commission_type=strategy.commission.percent,
    commission_value=0.1,
    backtest_fill_limits_assumption=1,
    margin_long=100,
    margin_short=100,
)
```

`strategy.configure(...)` is also available as a Python-friendly alias when a
script has already declared metadata through `indicator(...)` or does not need
declaration metadata.

`pyramiding` controls additional same-direction entries:

- `pyramiding=0` is the default and allows one open same-direction entry.
- `pyramiding=1` allows one additional same-direction entry.
- same-direction entries update `strategy.position_size` and weighted
  `strategy.position_avg_price`
- an opposite-direction entry reverses or replaces the current position

`slippage` follows Pine's tick-based model:

- `slippage` is a number of ticks, not a direct price or percent value.
- `mintick` / `min_tick` supplies the symbol's minimum price movement.
- When `mintick` / `min_tick` is omitted, Pyne uses `syminfo.mintick`.
- buy fills use `price + slippage * mintick`.
- sell fills use `price - slippage * mintick`.

Commission uses Pine-like constants:

- `strategy.commission.percent`: `commission_value` is a percent of traded notional.
- `strategy.commission.cash_per_order`: `commission_value` is charged once per filled order.
- `strategy.commission.cash_per_contract`: `commission_value` is charged per filled unit.

`backtest_fill_limits_assumption` follows Pine's limit-order verification
mental model:

- the value is a number of ticks
- the tick size is `mintick` / `min_tick`, or `syminfo.mintick` when omitted
- a long/buy limit fills only when bar `low <= limit - value * mintick`
- a short/sell limit fills only when bar `high >= limit + value * mintick`
- the filled price remains the requested limit price plus normal slippage rules

The default is `0`, which preserves the simpler touch-to-fill behavior.

Margin settings are accepted in the Pine-like declaration:

- `margin_long` is the percent margin required for long exposure.
- `margin_short` is the percent margin required for short exposure.
- both default to `100`, meaning no leverage
- lower values allow larger notional exposure for the same equity
- `syminfo.pointvalue` participates in the notional calculation

Pyne uses margin settings as deterministic entry/order admission rules. If the
resulting position would require more margin than the current replayed equity,
the new `strategy.entry*` or `strategy.order*` fill is skipped. Reducing,
closing, exiting, and canceling exposure remains allowed. Pyne does not model
broker margin calls, forced liquidation, interest, or cash settlement.

Capital reporting:

- `initial_capital` defaults to `100000`.
- `currency` defaults to `syminfo.currency` when available.
- `strategy.equity` is `initial_capital + strategy.netprofit + strategy.openprofit`.
- `strategy.netprofit` is realized gross profit/loss minus accumulated commission.
- `strategy.openprofit` marks the current net position to the current bar's `close`.
- `strategy.grossprofit` and `strategy.grossloss` track realized gross PnL before
  commission. `strategy.grossloss` is reported as a negative number.

## Risk Configuration

```python
strategy.risk.allow_entry_in(strategy.direction.long)
strategy.risk.max_drawdown(20, strategy.percent_of_equity)
strategy.risk.max_intraday_loss(5, strategy.cash)
strategy.risk.max_position_size(10)
```

`strategy.risk.allow_entry_in(...)` limits subsequent replay of
`strategy.entry*` events:

- `strategy.direction.all` / `strategy.risk.all`: allow long and short entries.
- `strategy.direction.long` / `strategy.risk.long`: allow long entries only.
- `strategy.direction.short` / `strategy.risk.short`: allow short entries only.
- `strategy.direction.none` / `strategy.risk.none`: block all entries.

This is a replay configuration for `strategy.entry*`. Lower-level
`strategy.order*` calls are not blocked by this setting because they represent
net-position order events rather than Pine-style entries.

`strategy.risk.max_drawdown(value, type=strategy.percent_of_equity)` locks the
strategy after equity falls far enough from the replayed equity peak:

- `strategy.percent_of_equity`: `value` is a percentage drawdown from peak equity.
- `strategy.cash`: `value` is an absolute cash drawdown from peak equity.

Once locked, future `strategy.entry*` and `strategy.order*` submissions and
pending fills are blocked. Close, exit, and cancel events remain available so a
script can flatten or clean up existing exposure. This is deterministic replay
logic, not a broker-side liquidation model.

`strategy.risk.max_intraday_loss(value, type=strategy.percent_of_equity)` uses
the same value types, but resets at the next `session.isfirstbar` boundary. Host
applications can mark daily or trading-session starts with per-bar
`session_isfirstbar` metadata. Without explicit metadata, Pyne's default batch
session marks only the first input bar as a session start.

`strategy.risk.max_position_size(contracts)` caps `strategy.entry*` fills so
the resulting long or short position does not exceed the configured absolute
size. If an entry would exceed the cap, Pyne reduces its fill quantity; if no
quantity remains after the cap is applied, the entry is skipped. Opposite
entries can replace the current position with a new capped position in the
opposite direction.

Like `allow_entry_in(...)`, this is an entry-level risk rule.
`strategy.order*` remains a lower-level net-position API and is not quantity
capped by `max_position_size(...)`.

## Entry

```python
strategy.entry_when(condition, id, direction=strategy.long, qty=1, price=None, limit=None, stop=None, oca_name="", oca_type=None, comment="")
strategy.entry(id, direction=strategy.long, qty=1, when=True, price=None, limit=None, stop=None, oca_name="", oca_type=None, comment="")
```

`condition` / `when` may be a scalar bool or a `PyneSeries` bool expression.
When `price` is omitted, Pyne uses `close` for the event price.

Entries use lightweight target/replay semantics:

- a long entry adds positive quantity
- a short entry adds negative quantity
- same-direction duplicate entries are limited by `strategy.configure(pyramiding=...)`
- a later opposite-direction entry can reverse or replace the target position
- `limit` and `stop` create lightweight pending orders that fill when later bar
  high/low values touch the trigger price
- pending orders with the same `oca_name` and `oca_type=strategy.oca.cancel`
  cancel their siblings when the first order fills

## Order

```python
strategy.order_when(condition, id, direction=strategy.long, qty=1, price=None, limit=None, stop=None, oca_name="", oca_type=None, comment="")
strategy.order(id, direction=strategy.long, qty=1, when=True, price=None, limit=None, stop=None, oca_name="", oca_type=None, comment="")
```

`strategy.order*` is a lower-level net-position order. Unlike
`strategy.entry*`, it is not limited by `pyramiding`:

- same-direction orders add to the current position
- opposite-direction orders reduce the current position
- if an opposite-direction order is larger than the current position, it reverses the position
- slippage and commission settings apply to filled order prices
- `limit` and `stop` create pending orders using the same high/low trigger scan
  as `strategy.entry*`

## Cancel

```python
strategy.cancel(id, when=True, comment="")
strategy.cancel_all(when=True, comment="")
```

`cancel()` cancels pending entry/order events with the matching id.
`cancel_all()` cancels every pending entry/order event. Cancel events are emitted
only when at least one pending order is actually canceled.

## Close

```python
strategy.close_when(condition, id="", price=None, comment="")
strategy.close(id="", when=True, price=None, comment="")
strategy.close_all(when=True, price=None, comment="")
```

`close_when()` emits close events only when there is an open position at that
bar in the replayed event timeline. When `id` is provided, replay closes the
matching entry-id lot quantity instead of blindly closing the whole net
position.

`close_all()` emits a close-all event that closes any open long or short
position at matching bars.

## Exit

```python
strategy.exit(id, from_entry="", qty=None, stop=None, limit=None, when=True, comment="")
```

`strategy.exit()` emits stop/limit bracket exit events while a position is open.
The current implementation scans each bar's `high` and `low` values:

- Long stop triggers when `low <= stop`.
- Long limit triggers when `high >= limit`.
- Short stop triggers when `high >= stop`.
- Short limit triggers when `low <= limit`.

When stop and limit are both touched on the same bar, stop wins. This is a
deterministic event model, not an intrabar broker simulator.

When `from_entry` is provided, the exit targets matching entry-id lots. When
`qty` is provided, the exit reduces that matched quantity by up to `qty` and
leaves the remaining position open with the previous average entry price. When
`qty` is omitted, the exit closes the full matched entry lot quantity.

## Position Series

```python
plot(strategy.position_size, "Position")
plot(strategy.position_avg_price, "Average Price")
plot(strategy.equity, "Equity")
plot(strategy.netprofit, "Net Profit")
plot(strategy.openprofit, "Open Profit")
plot(strategy.closedtrades, "Closed Trade Count")
plot(strategy.opentrades, "Open Trade Count")
```

Position values are replayed from the emitted event ledger in chronological
order. This gives batch output a Pine-like bar-by-bar mental model while staying
Python-friendly.

## Trade Namespace Access

`strategy.closedtrades` and `strategy.opentrades` behave as count series when
plotted. They also expose field accessors for the latest replayed entry-lot
ledger:

```python
plot(strategy.closedtrades, "Closed Trades")
plot(strategy.opentrades, "Open Trades")
plot(strategy.closedtrades.profit(0), "First Closed Profit")
plot(strategy.opentrades.entry_price(-1), "Latest Open Entry")
```

Supported accessors:

- `size(trade_num)` / `qty(trade_num)`
- `profit(trade_num)`
- `net_profit(trade_num)`
- `commission(trade_num)`
- `entry_price(trade_num)`
- `exit_price(trade_num)`
- `entry_time(trade_num)`
- `exit_time(trade_num)`
- `entry_id(trade_num)`
- `exit_id(trade_num)`
- `side(trade_num)`

Negative indexes count from the end of the current ledger. Missing trades return
`na` for numeric fields and an empty string for string fields.

## Output

Strategy output is serialized under `output["strategy"]`:

```json
{
  "strategy": {
    "orders": [
      {
        "time": 1710000000,
        "id": "Long",
        "type": "entry",
        "side": "long",
        "qty": 1.0,
        "price": 123.45,
        "position_after": 1.0,
        "commission": 0.12,
        "comment": ""
      },
      {
        "time": 1710000600,
        "id": "Long Exit",
        "from_entry": "Long",
        "type": "exit",
        "side": "flat",
        "qty": 1.0,
        "price": 130.0,
        "position_after": 0.0,
        "reason": "limit",
        "comment": ""
      }
    ],
    "position": {
      "size": 1.0,
      "side": "long",
      "avg_price": 123.45
    },
    "summary": {
      "initial_capital": 100000.0,
      "currency": "USD",
      "equity": 100250.0,
      "netprofit": 125.0,
      "openprofit": 125.0,
      "grossprofit": 250.0,
      "grossloss": 0.0,
      "commission": 0.0,
      "backtest_fill_limits_assumption": 0,
      "margin_long": 100.0,
      "margin_short": 100.0
    },
    "closedtrades": [],
    "opentrades": [
      {
        "entry_time": 1710000000,
        "entry_id": "Long",
        "side": "long",
        "qty": 1.0,
        "entry_price": 123.45,
        "profit": 125.0
      }
    ]
  }
}
```

`closedtrades` and `opentrades` are entry-lot ledgers. Same-direction entries
create separate lots, `strategy.exit(..., from_entry="...")` closes matching
lots first, and broad closes such as `strategy.close_all()` close lots FIFO.
The position series remains a deterministic net-position replay.

Known limits:

- no intrabar path model
- Python `if` cannot branch directly on series conditions; use
  `entry_when()` and `close_when()`
