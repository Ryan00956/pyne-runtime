# Strategy API

`strategy` is the Pine-like namespace for deterministic strategy events.

The current implementation is an event and position semantics layer. It is not
a broker simulator and does not model order books, slippage, commission, margin,
or partial fills.

```python
indicator("Trend Strategy", overlay=True)

fast = ta.ema(close, 12)
slow = ta.ema(close, 26)

strategy.entry_when(ta.cross(fast, slow), "Long", strategy.long, qty=1)
strategy.close_when(ta.cross(slow, fast), "Long")

plot(strategy.position_size, "Position")
```

## Direction Constants

- `strategy.long`
- `strategy.short`

## Entry

```python
strategy.entry_when(condition, id, direction=strategy.long, qty=1, price=None, comment="")
strategy.entry(id, direction=strategy.long, qty=1, when=True, price=None, comment="")
```

`condition` / `when` may be a scalar bool or a `PyneSeries` bool expression.
When `price` is omitted, Pyne uses `close` for the event price.

The first implementation uses target-position semantics:

- a long entry sets the position size to `qty`
- a short entry sets the position size to `-qty`
- a later entry can reverse or replace the target position

## Close

```python
strategy.close_when(condition, id="", price=None, comment="")
strategy.close(id="", when=True, price=None, comment="")
```

`close_when()` emits close events only when there is an open position at that
bar in the replayed event timeline.

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

- no commission or slippage model
- no pyramiding setting yet
- no `strategy.exit()` stop/limit bracket model yet
- Python `if` cannot branch directly on series conditions; use
  `entry_when()` and `close_when()`
