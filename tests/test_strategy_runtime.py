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
        "avg_price": 1.0,
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


def test_strategy_configure_pyramiding_allows_same_direction_adds() -> None:
    result = pn.run(
        """
indicator("Pyramiding", overlay=True)
strategy.configure(pyramiding=1)
strategy.entry_when(close > open, "Long", strategy.long, qty=1, price=close)
plot(strategy.position_size, "Position")
plot(strategy.position_avg_price, "Average")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["orders"] == [
        {
            "time": 1,
            "id": "Long",
            "type": "entry",
            "side": "long",
            "qty": 1.0,
            "price": 1.5,
            "position_after": 1.0,
            "comment": "",
        },
        {
            "time": 3,
            "id": "Long",
            "type": "entry",
            "side": "long",
            "qty": 1.0,
            "price": 2.8,
            "position_after": 2.0,
            "comment": "",
        },
    ]
    assert result.values("Position") == [1.0, 1.0, 2.0, 2.0]
    assert result.values("Average") == [1.5, 1.5, 2.15, 2.15]


def test_strategy_configure_applies_pine_like_tick_slippage() -> None:
    result = pn.run(
        """
indicator("Slippage", overlay=True)
strategy.configure(slippage=2, mintick=0.1)
strategy.entry_when(bar_index == 0, "Long", strategy.long, qty=1, price=close)
strategy.close_when(bar_index == 1, "Long", price=close)
plot(strategy.position_avg_price, "Average")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["orders"] == [
        {
            "time": 1,
            "id": "Long",
            "type": "entry",
            "side": "long",
            "qty": 1.0,
            "price": 1.7,
            "position_after": 1.0,
            "comment": "",
        },
        {
            "time": 2,
            "id": "Long",
            "type": "close",
            "side": "flat",
            "qty": 1.0,
            "price": 0.8,
            "position_after": 0.0,
            "comment": "",
        },
    ]
    assert result.values("Average") == [1.7]


def test_strategy_configure_applies_percent_commission() -> None:
    result = pn.run(
        """
indicator("Commission", overlay=True)
strategy.configure(
    commission_type=strategy.commission.percent,
    commission_value=1,
)
strategy.entry_when(bar_index == 0, "Long", strategy.long, qty=2, price=close)
strategy.close_when(bar_index == 1, "Long", price=close)
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["orders"] == [
        {
            "time": 1,
            "id": "Long",
            "type": "entry",
            "side": "long",
            "qty": 2.0,
            "price": 1.5,
            "position_after": 2.0,
            "comment": "",
            "commission": 0.03,
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
            "commission": 0.02,
        },
    ]


def test_strategy_callable_declares_metadata_and_configures_replay() -> None:
    result = pn.run(
        """
strategy(
    "Declared Strategy",
    overlay=False,
    pyramiding=1,
    slippage=1,
    mintick=0.1,
    commission_type=strategy.commission.percent,
    commission_value=1,
)
strategy.entry_when(close > open, "Long", strategy.long, qty=1, price=close)
plot(strategy.position_size, "Position")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.meta == {
        "title": "Declared Strategy",
        "overlay": False,
        "script_type": "strategy",
        "pyramiding": 1,
        "slippage": 1,
        "mintick": 0.1,
        "commission_type": "percent",
        "commission_value": 1,
        "securityMode": "safe",
    }
    assert result.lines[0]["pane"] == "separate"
    assert result.output["strategy"]["orders"] == [
        {
            "time": 1,
            "id": "Long",
            "type": "entry",
            "side": "long",
            "qty": 1.0,
            "price": 1.6,
            "position_after": 1.0,
            "comment": "",
            "commission": 0.016,
        },
        {
            "time": 3,
            "id": "Long",
            "type": "entry",
            "side": "long",
            "qty": 1.0,
            "price": 2.9,
            "position_after": 2.0,
            "comment": "",
            "commission": 0.029,
        },
    ]


def test_strategy_exit_emits_limit_exit_for_long_position() -> None:
    result = pn.run(
        """
indicator("Limit Exit", overlay=True)
strategy.entry_when(bar_index == 0, "Long", strategy.long, qty=1, price=close)
strategy.exit("Take Profit", from_entry="Long", limit=2.7, stop=0.8)
plot(strategy.position_size, "Position")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["orders"] == [
        {
            "time": 1,
            "id": "Long",
            "type": "entry",
            "side": "long",
            "qty": 1.0,
            "price": 1.5,
            "position_after": 1.0,
            "comment": "",
        },
        {
            "time": 3,
            "id": "Take Profit",
            "from_entry": "Long",
            "type": "exit",
            "side": "flat",
            "qty": 1.0,
            "price": 2.7,
            "position_after": 0.0,
            "reason": "limit",
            "comment": "",
        },
    ]
    assert result.values("Position") == [1.0, 1.0, 0.0, 0.0]


def test_strategy_exit_qty_partially_reduces_long_position() -> None:
    result = pn.run(
        """
indicator("Partial Exit", overlay=True)
strategy.entry_when(bar_index == 0, "Long", strategy.long, qty=2, price=close)
strategy.exit("Take Some", from_entry="Long", qty=0.5, limit=2.7, when=bar_index == 2)
plot(strategy.position_size, "Position")
plot(strategy.position_avg_price, "Average")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["orders"] == [
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
            "time": 3,
            "id": "Take Some",
            "from_entry": "Long",
            "type": "exit",
            "side": "flat",
            "qty": 0.5,
            "price": 2.7,
            "position_after": 1.5,
            "reason": "limit",
            "comment": "",
        },
    ]
    assert result.values("Position") == [2.0, 2.0, 1.5, 1.5]
    assert result.values("Average") == [1.5, 1.5, 1.5, 1.5]


def test_strategy_exit_emits_stop_exit_for_short_position() -> None:
    result = pn.run(
        """
indicator("Short Stop", overlay=True)
strategy.entry_when(bar_index == 0, "Short", strategy.short, qty=2, price=close)
strategy.exit("Stop", from_entry="Short", stop=2.1)
plot(strategy.position_size, "Position")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["orders"] == [
        {
            "time": 1,
            "id": "Short",
            "type": "entry",
            "side": "short",
            "qty": 2.0,
            "price": 1.5,
            "position_after": -2.0,
            "comment": "",
        },
        {
            "time": 2,
            "id": "Stop",
            "from_entry": "Short",
            "type": "exit",
            "side": "flat",
            "qty": 2.0,
            "price": 2.1,
            "position_after": 0.0,
            "reason": "stop",
            "comment": "",
        },
    ]
    assert result.values("Position") == [-2.0, 0.0, 0.0, 0.0]


def test_strategy_exit_when_filters_exit_events() -> None:
    result = pn.run(
        """
indicator("Exit When", overlay=True)
strategy.entry_when(bar_index == 0, "Long", strategy.long, qty=1, price=close)
strategy.exit("Later Stop", from_entry="Long", stop=1.2, when=bar_index >= 2)
plot(strategy.position_size, "Position")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert len(result.output["strategy"]["orders"]) == 1
    assert result.values("Position") == [1.0, 1.0, 1.0, 1.0]
