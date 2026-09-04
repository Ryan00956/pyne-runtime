from __future__ import annotations

import pyne_runtime as pn
import pytest


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 10, "open": 1, "high": 3, "low": 0.5, "close": 2, "volume": 10},
        {"time": 20, "open": 2, "high": 4, "low": 1.5, "close": 3, "volume": 20},
    ]


def test_incremental_parity_framework_accepts_semantically_equal_candles() -> None:
    report = pn.run_incremental_parity(
        batch_script="""
indicator("Candles", overlay=True)
plotcandle(open, high, low, close, "Synthetic", color=color.green)
""",
        incremental_script="""
indicator("Candles", mode="incremental", overlay=True)
def on_bar(ctx, bar):
    ctx.plotcandle(bar.open, bar.high, bar.low, bar.close, "Synthetic", color=color.green)
""",
        bars=_bars(),
    )

    assert report.ok
    assert report.differences == ()
    report.assert_ok()


def test_incremental_parity_framework_reports_stable_difference_paths() -> None:
    report = pn.run_incremental_parity(
        batch_script='indicator("Line"); plot(close, "Close")',
        incremental_script="""
indicator("Line", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("Close", bar.close + 1)
""",
        bars=_bars(),
        normalizer=lambda result: result.values("Close"),
    )

    assert not report.ok
    assert report.differences[0].path == "$[0]"
    with pytest.raises(AssertionError, match="Batch/incremental parity failed"):
        report.assert_ok()


def test_incremental_parity_framework_preserves_execution_failures() -> None:
    report = pn.run_incremental_parity(
        batch_script='indicator("Good"); plot(close, "Close")',
        incremental_script='indicator("Bad", mode="incremental")',
        bars=_bars(),
    )

    assert not report.ok
    assert not report.incremental_result.ok
    with pytest.raises(AssertionError, match="Incremental execution failed"):
        report.assert_ok()


def test_incremental_parity_framework_compares_full_strategy_lifecycle() -> None:
    report = pn.run_incremental_parity(
        batch_script="""
strategy("Order Reduce", overlay=True, initial_capital=1000)
strategy.entry_when(bar_index == 0, "Long", strategy.long, qty=5, price=close)
strategy.order_when(bar_index == 1, "Reduce", strategy.short, qty=2, price=close)
plot(strategy.position_size, "Position")
plot(strategy.equity, "Equity")
plot(strategy.netprofit, "Net Profit")
""",
        incremental_script="""
indicator("Incremental Order Reduce", mode="incremental", overlay=True)
def init(ctx):
    ctx.strategy.configure(initial_capital=1000)
def on_bar(ctx, bar):
    ctx.strategy.entry("Long", ctx.strategy.long, qty=5, price=bar.close, when=ctx.bar_index == 0)
    ctx.strategy.order("Reduce", ctx.strategy.short, qty=2, price=bar.close, when=ctx.bar_index == 1)
    ctx.plot("Position", ctx.strategy.position_size)
    ctx.plot("Equity", ctx.strategy.equity)
    ctx.plot("Net Profit", ctx.strategy.netprofit)
""",
        bars=[
            {"time": 1, "open": 1, "high": 2, "low": 1, "close": 1.0, "volume": 100},
            {"time": 2, "open": 1, "high": 2, "low": 1, "close": 2.0, "volume": 100},
            {"time": 3, "open": 1, "high": 3, "low": 1, "close": 3.0, "volume": 100},
        ],
    )

    report.assert_ok()
