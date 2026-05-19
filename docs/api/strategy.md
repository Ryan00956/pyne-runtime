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
)

fast = ta.ema(close, 12)
slow = ta.ema(close, 26)

strategy.entry_when(ta.cross(fast, slow), "Long", strategy.long, qty=1)
strategy.close_when(ta.cross(slow, fast), "Long")
strategy.exit("Long Exit", from_entry="Long", stop=close * 0.95, limit=close * 1.05)

plot(strategy.position_size, "Position")
```

## Direction Constants

- `strategy.long`
- `strategy.short`

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
- buy fills use `price + slippage * mintick`.
- sell fills use `price - slippage * mintick`.

Commission uses Pine-like constants:

- `strategy.commission.percent`: `commission_value` is a percent of traded notional.
- `strategy.commission.cash_per_order`: `commission_value` is charged once per filled order.
- `strategy.commission.cash_per_contract`: `commission_value` is charged per filled unit.

## Entry

```python
strategy.entry_when(condition, id, direction=strategy.long, qty=1, price=None, comment="")
strategy.entry(id, direction=strategy.long, qty=1, when=True, price=None, comment="")
```

`condition` / `when` may be a scalar bool or a `PyneSeries` bool expression.
When `price` is omitted, Pyne uses `close` for the event price.

Entries use lightweight target/replay semantics:

- a long entry adds positive quantity
- a short entry adds negative quantity
- same-direction duplicate entries are limited by `strategy.configure(pyramiding=...)`
- a later opposite-direction entry can reverse or replace the target position

## Close

```python
strategy.close_when(condition, id="", price=None, comment="")
strategy.close(id="", when=True, price=None, comment="")
```

`close_when()` emits close events only when there is an open position at that
bar in the replayed event timeline.

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

When `qty` is provided, the exit reduces the current position by up to that
quantity and leaves the remaining position open with the previous average entry
price. When `qty` is omitted, the exit closes the full current position.

## Position Series

```python
plot(strategy.position_size, "Position")
plot(strategy.position_avg_price, "Average Price")
```

Position values are replayed from the emitted event ledger in chronological
order. This gives batch output a Pine-like bar-by-bar mental model while staying
Python-friendly.

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
    }
  }
}
```

Known limits:

- no intrabar path model
- Python `if` cannot branch directly on series conditions; use
  `entry_when()` and `close_when()`
