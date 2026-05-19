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


def test_strategy_order_reduces_and_reverses_net_position() -> None:
    result = pn.run(
        """
indicator("Order", overlay=True)
strategy.order_when(bar_index == 0, "Buy", strategy.long, qty=2, price=close)
strategy.order_when(bar_index == 1, "Sell Some", strategy.short, qty=1, price=close)
strategy.order_when(bar_index == 2, "Reverse", strategy.short, qty=3, price=close)
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
            "id": "Buy",
            "type": "order",
            "side": "long",
            "qty": 2.0,
            "price": 1.5,
            "position_after": 2.0,
            "comment": "",
        },
        {
            "time": 2,
            "id": "Sell Some",
            "type": "order",
            "side": "short",
            "qty": 1.0,
            "price": 1.0,
            "position_after": 1.0,
            "comment": "",
        },
        {
            "time": 3,
            "id": "Reverse",
            "type": "order",
            "side": "short",
            "qty": 3.0,
            "price": 2.8,
            "position_after": -2.0,
            "comment": "",
        },
    ]
    assert result.values("Position") == [2.0, 1.0, -2.0, -2.0]
    assert result.values("Average") == [1.5, 1.5, 2.8, 2.8]


def test_strategy_risk_allow_entry_in_blocks_disallowed_entry_direction() -> None:
    result = pn.run(
        """
indicator("Risk Direction", overlay=True)
strategy.risk.allow_entry_in(strategy.direction.long)
strategy.entry_when(bar_index == 0, "Short", strategy.short, qty=1, price=close)
strategy.entry_when(bar_index == 1, "Long", strategy.long, qty=1, price=close)
plot(strategy.position_size, "Position")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["orders"] == [
        {
            "time": 2,
            "id": "Long",
            "type": "entry",
            "side": "long",
            "qty": 1.0,
            "price": 1.0,
            "position_after": 1.0,
            "comment": "",
        },
    ]
    assert result.values("Position") == [0.0, 1.0, 1.0, 1.0]


def test_strategy_risk_allow_entry_in_does_not_block_order_namespace() -> None:
    result = pn.run(
        """
indicator("Risk Order", overlay=True)
strategy.risk.allow_entry_in(strategy.risk.none)
strategy.entry_when(bar_index == 0, "Long Entry", strategy.long, qty=1, price=close)
strategy.order_when(bar_index == 1, "Long Order", strategy.long, qty=1, price=close)
plot(strategy.position_size, "Position")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["orders"] == [
        {
            "time": 2,
            "id": "Long Order",
            "type": "order",
            "side": "long",
            "qty": 1.0,
            "price": 1.0,
            "position_after": 1.0,
            "comment": "",
        },
    ]
    assert result.values("Position") == [0.0, 1.0, 1.0, 1.0]


def test_strategy_order_alias_accepts_when_keyword_and_costs() -> None:
    result = pn.run(
        """
indicator("Order Alias", overlay=True)
strategy.configure(
    slippage=1,
    mintick=0.1,
    commission_type=strategy.commission.cash_per_contract,
    commission_value=0.5,
)
strategy.order("Buy", strategy.long, qty=2, when=bar_index == 0, price=close)
plot(strategy.position_size, "Position")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["orders"] == [
        {
            "time": 1,
            "id": "Buy",
            "type": "order",
            "side": "long",
            "qty": 2.0,
            "price": 1.6,
            "position_after": 2.0,
            "comment": "",
            "commission": 1.0,
        },
    ]
    assert result.values("Position") == [2.0, 2.0, 2.0, 2.0]


def test_strategy_entry_stop_order_fills_on_later_bar() -> None:
    result = pn.run(
        """
indicator("Pending Stop", overlay=True)
strategy.entry("Breakout", strategy.long, qty=1, when=bar_index == 0, stop=2.5)
plot(strategy.position_size, "Position")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["orders"] == [
        {
            "time": 3,
            "id": "Breakout",
            "type": "entry",
            "side": "long",
            "qty": 1.0,
            "price": 2.5,
            "position_after": 1.0,
            "comment": "",
            "reason": "stop",
        },
    ]
    assert result.values("Position") == [0.0, 0.0, 1.0, 1.0]


def test_strategy_cancel_prevents_pending_entry_fill() -> None:
    result = pn.run(
        """
indicator("Cancel", overlay=True)
strategy.entry("Breakout", strategy.long, qty=1, when=bar_index == 0, stop=2.5)
strategy.cancel("Breakout", when=bar_index == 1, comment="No trade")
plot(strategy.position_size, "Position")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["orders"] == [
        {
            "time": 2,
            "id": "Breakout",
            "type": "cancel",
            "side": "flat",
            "qty": 0.0,
            "price": None,
            "position_after": 0.0,
            "comment": "No trade",
            "canceled": 1,
        },
    ]
    assert result.values("Position") == [0.0, 0.0, 0.0, 0.0]


def test_strategy_cancel_all_clears_multiple_pending_orders() -> None:
    result = pn.run(
        """
indicator("Cancel All", overlay=True)
strategy.entry("Breakout", strategy.long, qty=1, when=bar_index == 0, stop=2.5)
strategy.order("Fade", strategy.short, qty=1, when=bar_index == 0, limit=2.7)
strategy.cancel_all(when=bar_index == 1, comment="Flat")
plot(strategy.position_size, "Position")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["orders"] == [
        {
            "time": 2,
            "id": "cancel_all",
            "type": "cancel_all",
            "side": "flat",
            "qty": 0.0,
            "price": None,
            "position_after": 0.0,
            "comment": "Flat",
            "canceled": 2,
        },
    ]
    assert result.values("Position") == [0.0, 0.0, 0.0, 0.0]


def test_strategy_oca_cancel_fills_first_pending_order_and_cancels_siblings() -> None:
    result = pn.run(
        """
indicator("OCA", overlay=True)
strategy.entry(
    "Breakout",
    strategy.long,
    qty=1,
    when=bar_index == 0,
    stop=2.5,
    oca_name="bracket",
    oca_type=strategy.oca.cancel,
)
strategy.order(
    "Fade",
    strategy.short,
    qty=1,
    when=bar_index == 0,
    limit=2.7,
    oca_name="bracket",
    oca_type=strategy.oca.cancel,
)
plot(strategy.position_size, "Position")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["orders"] == [
        {
            "time": 3,
            "id": "Breakout",
            "type": "entry",
            "side": "long",
            "qty": 1.0,
            "price": 2.5,
            "position_after": 1.0,
            "comment": "",
            "reason": "stop",
            "oca_name": "bracket",
            "oca_type": "cancel",
        },
    ]
    assert result.values("Position") == [0.0, 0.0, 1.0, 1.0]


def test_strategy_oca_reduce_decreases_sibling_pending_quantity() -> None:
    result = pn.run(
        """
indicator("OCA Reduce", overlay=True)
strategy.entry(
    "First",
    strategy.long,
    qty=1,
    when=bar_index == 0,
    stop=2.5,
    oca_name="scale",
    oca_type=strategy.oca.reduce,
)
strategy.order(
    "Second",
    strategy.long,
    qty=2,
    when=bar_index == 0,
    stop=3.1,
    oca_name="scale",
    oca_type=strategy.oca.reduce,
)
plot(strategy.position_size, "Position")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["orders"] == [
        {
            "time": 3,
            "id": "First",
            "type": "entry",
            "side": "long",
            "qty": 1.0,
            "price": 2.5,
            "position_after": 1.0,
            "comment": "",
            "reason": "stop",
            "oca_name": "scale",
            "oca_type": "reduce",
        },
        {
            "time": 4,
            "id": "Second",
            "type": "order",
            "side": "long",
            "qty": 1.0,
            "price": 3.1,
            "position_after": 2.0,
            "comment": "",
            "reason": "stop",
            "oca_name": "scale",
            "oca_type": "reduce",
        },
    ]
    assert result.values("Position") == [0.0, 0.0, 1.0, 2.0]


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


def test_strategy_close_all_closes_any_open_position() -> None:
    result = pn.run(
        """
indicator("Close All", overlay=True)
strategy.entry_when(bar_index == 0, "Short", strategy.short, qty=2, price=close)
strategy.close_all(when=bar_index == 2, price=close, comment="Risk off")
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
            "time": 3,
            "id": "close_all",
            "type": "close_all",
            "side": "flat",
            "qty": 2.0,
            "price": 2.8,
            "position_after": 0.0,
            "comment": "Risk off",
        },
    ]
    assert result.values("Position") == [-2.0, -2.0, 0.0, 0.0]


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


def test_strategy_reporting_exposes_equity_profit_and_closed_trades() -> None:
    result = pn.run(
        """
strategy(
    "Report",
    overlay=True,
    initial_capital=1000,
    currency="USD",
    commission_type=strategy.commission.cash_per_order,
    commission_value=1,
)
strategy.entry_when(bar_index == 0, "Long", strategy.long, qty=2, price=close)
strategy.close_when(bar_index == 2, "Long", price=close)
plot(strategy.equity, "Equity")
plot(strategy.netprofit, "Net Profit")
plot(strategy.openprofit, "Open Profit")
plot(strategy.grossprofit, "Gross Profit")
plot(strategy.grossloss, "Gross Loss")
""",
        [
            {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
            {"time": 2, "open": 10, "high": 13, "low": 10, "close": 12, "volume": 100},
            {"time": 3, "open": 12, "high": 12, "low": 10, "close": 11, "volume": 100},
        ],
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Equity") == [999.0, 1003.0, 1000.0]
    assert result.values("Net Profit") == [-1.0, -1.0, 0.0]
    assert result.values("Open Profit") == [0.0, 4.0, 0.0]
    assert result.values("Gross Profit") == [0.0, 0.0, 2.0]
    assert result.values("Gross Loss") == [0.0, 0.0, 0.0]
    assert result.output["strategy"]["summary"] == {
        "initial_capital": 1000.0,
        "currency": "USD",
        "equity": 1000.0,
        "netprofit": 0.0,
        "openprofit": 0.0,
        "grossprofit": 2.0,
        "grossloss": 0.0,
        "commission": 2.0,
    }
    assert result.output["strategy"]["closedtrades"] == [
        {
            "entry_time": 1,
            "exit_time": 3,
            "entry_id": "Long",
            "exit_id": "Long",
            "side": "long",
            "qty": 2.0,
            "entry_price": 10.0,
            "exit_price": 11.0,
            "profit": 2.0,
            "commission": 1.0,
            "net_profit": 1.0,
        }
    ]
    assert result.output["strategy"]["opentrades"] == []


def test_strategy_reporting_exposes_open_trades() -> None:
    result = pn.run(
        """
strategy("Open Report", overlay=True, initial_capital=1000)
strategy.entry_when(bar_index == 0, "Long", strategy.long, qty=2, price=close)
plot(strategy.equity, "Equity")
plot(strategy.openprofit, "Open Profit")
""",
        [
            {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
            {"time": 2, "open": 10, "high": 12, "low": 10, "close": 10.5, "volume": 100},
        ],
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Equity") == [1000.0, 1001.0]
    assert result.values("Open Profit") == [0.0, 1.0]
    assert result.output["strategy"]["opentrades"] == [
        {
            "entry_time": 1,
            "entry_id": "Long",
            "side": "long",
            "qty": 2.0,
            "entry_price": 10.0,
            "profit": 1.0,
        }
    ]


def test_strategy_trade_ledger_tracks_entry_id_partial_exit() -> None:
    result = pn.run(
        """
strategy("Lots", overlay=True, initial_capital=1000, pyramiding=2)
strategy.entry_when(bar_index == 0, "A", strategy.long, qty=1, price=close)
strategy.entry_when(bar_index == 1, "B", strategy.long, qty=2, price=close)
strategy.exit("B Exit", from_entry="B", qty=1, limit=12, when=bar_index == 2)
""",
        [
            {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
            {"time": 2, "open": 11, "high": 12, "low": 10, "close": 11, "volume": 100},
            {"time": 3, "open": 12, "high": 13, "low": 11, "close": 12, "volume": 100},
            {"time": 4, "open": 13, "high": 14, "low": 12, "close": 13, "volume": 100},
        ],
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["closedtrades"] == [
        {
            "entry_time": 2,
            "exit_time": 3,
            "entry_id": "B",
            "exit_id": "B Exit",
            "side": "long",
            "qty": 1.0,
            "entry_price": 11.0,
            "exit_price": 12.0,
            "profit": 1.0,
            "commission": 0.0,
            "net_profit": 1.0,
        }
    ]
    assert result.output["strategy"]["opentrades"] == [
        {
            "entry_time": 1,
            "entry_id": "A",
            "side": "long",
            "qty": 1.0,
            "entry_price": 10.0,
            "profit": 3.0,
        },
        {
            "entry_time": 2,
            "entry_id": "B",
            "side": "long",
            "qty": 1.0,
            "entry_price": 11.0,
            "profit": 2.0,
        },
    ]


def test_strategy_trade_ledger_splits_close_all_by_entry_lot() -> None:
    result = pn.run(
        """
strategy("Close Lots", overlay=True, initial_capital=1000, pyramiding=2)
strategy.entry_when(bar_index == 0, "A", strategy.long, qty=1, price=close)
strategy.entry_when(bar_index == 1, "B", strategy.long, qty=2, price=close)
strategy.close_all(when=bar_index == 2, price=close)
""",
        [
            {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
            {"time": 2, "open": 11, "high": 12, "low": 10, "close": 11, "volume": 100},
            {"time": 3, "open": 12, "high": 13, "low": 11, "close": 12, "volume": 100},
        ],
        executor_mode="inline",
    )

    assert result.ok
    assert result.output["strategy"]["closedtrades"] == [
        {
            "entry_time": 1,
            "exit_time": 3,
            "entry_id": "A",
            "exit_id": "close_all",
            "side": "long",
            "qty": 1.0,
            "entry_price": 10.0,
            "exit_price": 12.0,
            "profit": 2.0,
            "commission": 0.0,
            "net_profit": 2.0,
        },
        {
            "entry_time": 2,
            "exit_time": 3,
            "entry_id": "B",
            "exit_id": "close_all",
            "side": "long",
            "qty": 2.0,
            "entry_price": 11.0,
            "exit_price": 12.0,
            "profit": 2.0,
            "commission": 0.0,
            "net_profit": 2.0,
        },
    ]
    assert result.output["strategy"]["opentrades"] == []


def test_strategy_close_id_closes_matching_entry_lot_only() -> None:
    result = pn.run(
        """
strategy("Close By Id", overlay=True, initial_capital=1000, pyramiding=2)
strategy.entry_when(bar_index == 0, "A", strategy.long, qty=1, price=close)
strategy.entry_when(bar_index == 1, "B", strategy.long, qty=2, price=close)
strategy.close("A", when=bar_index == 2, price=close)
plot(strategy.position_size, "Position")
""",
        [
            {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
            {"time": 2, "open": 11, "high": 12, "low": 10, "close": 11, "volume": 100},
            {"time": 3, "open": 12, "high": 13, "low": 11, "close": 12, "volume": 100},
            {"time": 4, "open": 13, "high": 14, "low": 12, "close": 13, "volume": 100},
        ],
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Position") == [1.0, 3.0, 2.0, 2.0]
    assert result.output["strategy"]["orders"] == [
        {
            "time": 1,
            "id": "A",
            "type": "entry",
            "side": "long",
            "qty": 1.0,
            "price": 10.0,
            "position_after": 1.0,
            "comment": "",
        },
        {
            "time": 2,
            "id": "B",
            "type": "entry",
            "side": "long",
            "qty": 2.0,
            "price": 11.0,
            "position_after": 3.0,
            "comment": "",
        },
        {
            "time": 3,
            "id": "A",
            "type": "close",
            "side": "flat",
            "qty": 1.0,
            "price": 12.0,
            "position_after": 2.0,
            "comment": "",
        },
    ]
    assert result.output["strategy"]["closedtrades"] == [
        {
            "entry_time": 1,
            "exit_time": 3,
            "entry_id": "A",
            "exit_id": "A",
            "side": "long",
            "qty": 1.0,
            "entry_price": 10.0,
            "exit_price": 12.0,
            "profit": 2.0,
            "commission": 0.0,
            "net_profit": 2.0,
        }
    ]
    assert result.output["strategy"]["opentrades"] == [
        {
            "entry_time": 2,
            "entry_id": "B",
            "side": "long",
            "qty": 2.0,
            "entry_price": 11.0,
            "profit": 4.0,
        }
    ]


def test_strategy_exit_from_entry_without_qty_closes_matching_lot_only() -> None:
    result = pn.run(
        """
strategy("Exit By Entry", overlay=True, initial_capital=1000, pyramiding=2)
strategy.entry_when(bar_index == 0, "A", strategy.long, qty=1, price=close)
strategy.entry_when(bar_index == 1, "B", strategy.long, qty=2, price=close)
strategy.exit("Exit B", from_entry="B", limit=12, when=bar_index == 2)
plot(strategy.position_size, "Position")
""",
        [
            {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
            {"time": 2, "open": 11, "high": 12, "low": 10, "close": 11, "volume": 100},
            {"time": 3, "open": 12, "high": 13, "low": 11, "close": 12, "volume": 100},
        ],
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Position") == [1.0, 3.0, 1.0]
    assert result.output["strategy"]["closedtrades"] == [
        {
            "entry_time": 2,
            "exit_time": 3,
            "entry_id": "B",
            "exit_id": "Exit B",
            "side": "long",
            "qty": 2.0,
            "entry_price": 11.0,
            "exit_price": 12.0,
            "profit": 2.0,
            "commission": 0.0,
            "net_profit": 2.0,
        }
    ]


def test_strategy_trade_namespaces_expose_count_series_and_fields() -> None:
    result = pn.run(
        """
strategy("Trade Namespace", overlay=True, initial_capital=1000, pyramiding=2)
strategy.entry_when(bar_index == 0, "A", strategy.long, qty=1, price=close)
strategy.entry_when(bar_index == 1, "B", strategy.long, qty=2, price=close)
strategy.close("A", when=bar_index == 2, price=close)
plot(strategy.closedtrades, "Closed Count")
plot(strategy.opentrades, "Open Count")
plot(strategy.closedtrades.profit(0), "First Closed Profit")
plot(strategy.opentrades.entry_price(0), "First Open Entry")
plot(1 if strategy.closedtrades.entry_id(0) == "A" else 0, "Closed Id Match")
plot(1 if strategy.opentrades.entry_id(0) == "B" else 0, "Open Id Match")
""",
        [
            {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
            {"time": 2, "open": 11, "high": 12, "low": 10, "close": 11, "volume": 100},
            {"time": 3, "open": 12, "high": 13, "low": 11, "close": 12, "volume": 100},
            {"time": 4, "open": 13, "high": 14, "low": 12, "close": 13, "volume": 100},
        ],
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Closed Count") == [0.0, 0.0, 1.0, 1.0]
    assert result.values("Open Count") == [1.0, 2.0, 1.0, 1.0]
    assert result.values("First Closed Profit") == [2.0, 2.0, 2.0, 2.0]
    assert result.values("First Open Entry") == [11.0, 11.0, 11.0, 11.0]
    assert result.values("Closed Id Match") == [1.0, 1.0, 1.0, 1.0]
    assert result.values("Open Id Match") == [1.0, 1.0, 1.0, 1.0]
