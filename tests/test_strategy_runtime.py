from __future__ import annotations

import pyne_runtime as pn


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 1, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100},
        {"time": 2, "open": 2, "high": 2.2, "low": 1, "close": 1.0, "volume": 120},
        {"time": 3, "open": 2, "high": 3, "low": 1.8, "close": 2.8, "volume": 140},
        {"time": 4, "open": 3, "high": 3.2, "low": 2, "close": 2.4, "volume": 160},
    ]


def test_strategy_entry_and_close_events_are_collected() -> None:
    result = pn.run(
        """
indicator("Strategy", overlay=True)
strategy.entry_when(close > open, "Long", strategy.long, qty=2, price=close)
strategy.close_when(close < open, "Long", price=close)
plot(strategy.position_size, "Position")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    strategy_output = result.output["strategy"]
    assert strategy_output["position"] == {
        "size": 0.0,
        "side": "flat",
        "avg_price": None,
    }
    assert strategy_output["orders"] == [
        {
            "time": 1,
            "id": "Long",
            "type": "entry",
            "side": "long",
            "qty": 2.0,
            "price": 1.5,
            "position_after": 2.0,
            "comment": "",
        },
        {
            "time": 2,
            "id": "Long",
            "type": "close",
            "side": "flat",
            "qty": 2.0,
            "price": 1.0,
            "position_after": 0.0,
            "comment": "",
        },
        {
            "time": 3,
            "id": "Long",
            "type": "entry",
            "side": "long",
            "qty": 2.0,
            "price": 2.8,
            "position_after": 2.0,
            "comment": "",
        },
        {
            "time": 4,
            "id": "Long",
            "type": "close",
            "side": "flat",
            "qty": 2.0,
            "price": 2.4,
            "position_after": 0.0,
            "comment": "",
        },
    ]
    assert result.values("Position") == [2.0, 0.0, 2.0, 0.0]


def test_strategy_entry_accepts_when_keyword_and_short_direction() -> None:
    result = pn.run(
        """
indicator("Short", overlay=True)
strategy.entry("Short", strategy.short, qty=1.5, when=close < open)
plot(strategy.position_size, "Position")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["position"] == {
        "size": -1.5,
        "side": "short",
        "avg_price": 2.4,
    }
    assert result.values("Position") == [0.0, -1.5, -1.5, -1.5]


def test_strategy_unused_does_not_emit_strategy_output() -> None:
    result = pn.run(
        """
indicator("No Strategy", overlay=True)
plot(close, "Close")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert "strategy" not in result.output
