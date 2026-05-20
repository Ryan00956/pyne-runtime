from __future__ import annotations

import pyne_runtime as pn


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 1, "open": 1, "high": 2, "low": 1, "close": 1.0, "volume": 100},
        {"time": 2, "open": 1, "high": 2, "low": 1, "close": 2.0, "volume": 100},
        {"time": 3, "open": 1, "high": 2, "low": 1, "close": 3.0, "volume": 100},
    ]


def test_incremental_runtime_seeds_history() -> None:
    script = """
indicator("Incremental MA", mode="incremental", overlay=True)

def init(ctx):
    ctx.ta.sma("ma", period=2)

def on_bar(ctx, bar):
    value = ctx.ta.sma("ma").update(bar.close)
    ctx.plot("MA", value, color=color.orange)
"""

    result = pn.run(script, _bars(), executor_mode="inline")

    assert result.ok
    assert len(result.lines) == 1
    assert len(result.lines[0]["data"]) == 2


def _line_values(result: object, line_id: str) -> list[float]:
    line = next(item for item in result.lines if item["id"] == line_id)
    return [point["value"] for point in line["data"]]


def _line_values_by_name(result: object, name: str) -> list[float]:
    line = next(item for item in result.lines if item["name"] == name)
    return [point["value"] for point in line["data"]]


def _marker_times(result: object, marker_id: str) -> list[int]:
    for marker in result.output.get("markers", []):
        if marker["id"] == marker_id:
            return [point["time"] for point in marker["data"]]
    return []


def _assert_strategy_matches_batch(incremental: object, batch: object) -> None:
    assert _line_values(incremental, "position") == _line_values_by_name(batch, "Position")
    assert _line_values(incremental, "equity") == _line_values_by_name(batch, "Equity")
    assert _line_values(incremental, "net_profit") == _line_values_by_name(batch, "Net Profit")
    assert incremental.output["strategy"]["position"] == batch.output["strategy"]["position"]
    for key in ("initial_capital", "equity", "netprofit", "openprofit", "grossprofit", "grossloss", "commission"):
        assert incremental.output["strategy"]["summary"][key] == batch.output["strategy"]["summary"][key]
    assert incremental.output["strategy"]["orders"] == batch.output["strategy"]["orders"]
    assert incremental.output["strategy"]["closedtrades"] == batch.output["strategy"]["closedtrades"]
    assert incremental.output["strategy"]["opentrades"] == batch.output["strategy"]["opentrades"]


def test_incremental_seed_exposes_bar_clock_and_barstate() -> None:
    script = """
indicator("Incremental Clock", mode="incremental", overlay=True)

def on_bar(ctx, bar):
    ctx.plot("Index", ctx.bar_index)
    ctx.plot("BarIndex", bar.bar_index)
    ctx.plot("Last", ctx.last_bar_index)
    ctx.marker(ctx.barstate.isfirst, text="First")
    ctx.marker(ctx.barstate.islast, text="Last")
    ctx.marker(ctx.barstate.ishistory, text="History")
    ctx.marker(ctx.barstate.isconfirmed, text="Confirmed")
    ctx.marker(ctx.barstate.islastconfirmedhistory, text="LCH")
"""

    result = pn.run(script, _bars(), executor_mode="inline")

    assert result.ok
    assert _line_values(result, "index") == [0.0, 1.0, 2.0]
    assert _line_values(result, "barindex") == [0.0, 1.0, 2.0]
    assert _line_values(result, "last") == [2.0, 2.0, 2.0]
    assert _marker_times(result, "first") == [1]
    assert _marker_times(result, "last") == [3]
    assert _marker_times(result, "history") == [1, 2, 3]
    assert _marker_times(result, "confirmed") == [1, 2, 3]
    assert _marker_times(result, "lch") == [3]
    assert result.meta["bar_index"] == 2
    assert result.meta["last_bar_index"] == 2
    assert result.meta["barstate"]["islastconfirmedhistory"] is True


def test_incremental_context_exposes_current_session_flags() -> None:
    script = """
indicator("Incremental Session", mode="incremental", overlay=True)

def on_bar(ctx, bar):
    ctx.plot("Market", 1 if ctx.session.ismarket else 0)
    ctx.marker(ctx.session.isfirstbar, text="First Session")
    ctx.marker(ctx.session.islastbar, text="Last Session")
"""
    bars = [
        {**_bars()[0], "session_ismarket": True, "session_isfirstbar": True},
        {**_bars()[1], "session_ismarket": False},
        {**_bars()[2], "session": {"ismarket": True, "islastbar": True}},
    ]

    result = pn.run(script, bars, executor_mode="inline")

    assert result.ok
    assert _line_values(result, "market") == [1.0, 0.0, 1.0]
    assert _marker_times(result, "first_session") == [1]
    assert _marker_times(result, "last_session") == [3]


def test_incremental_preview_barstate_does_not_persist() -> None:
    script = """
indicator("Preview", mode="incremental", overlay=True)

def on_bar(ctx, bar):
    seen = ctx.state("seen", 0)
    seen.value += 1
    ctx.plot("Seen", seen.value)
    ctx.marker(ctx.barstate.isconfirmed, text="Confirmed")

def on_preview(ctx, bar):
    seen = ctx.state("seen", 0)
    seen.value += 100
    ctx.plot("PreviewSeen", seen.value)
    ctx.plot("PreviewIndex", ctx.bar_index)
    ctx.marker(ctx.barstate.isrealtime, text="Realtime")
    ctx.marker(ctx.barstate.isnew, text="New")
    ctx.marker(not ctx.barstate.isconfirmed, text="Unconfirmed")
"""
    session = pn.PyneIncrementalSession(
        script=script,
        settings=pn.PyneSettings(executor_mode="inline"),
    )

    seed = session.seed(_bars()[:2])
    first_preview = session.on_bar_updated(
        {"time": 3, "open": 1, "high": 3, "low": 1, "close": 2.5, "volume": 100}
    )
    second_preview = session.on_bar_updated(
        {"time": 3, "open": 1, "high": 3, "low": 1, "close": 2.75, "volume": 100}
    )
    snapshot = session.snapshot_result()

    assert _line_values(seed, "seen") == [1.0, 2.0]
    assert _line_values(first_preview, "previewseen") == [102.0]
    assert _line_values(first_preview, "previewindex") == [2.0]
    assert _marker_times(first_preview, "realtime") == [3]
    assert _marker_times(first_preview, "new") == [3]
    assert _marker_times(first_preview, "unconfirmed") == [3]
    assert _line_values(second_preview, "previewseen") == [102.0]
    assert _marker_times(second_preview, "new") == []
    assert _line_values(snapshot, "seen") == [1.0, 2.0]
    assert snapshot.meta["bar_index"] == 1


def test_incremental_closed_bar_after_preview_is_confirmed_without_preview_state() -> None:
    script = """
indicator("Closed", mode="incremental", overlay=True)

def on_bar(ctx, bar):
    seen = ctx.state("seen", 0)
    seen.value += 1
    ctx.plot("Seen", seen.value)
    ctx.plot("BarIndex", bar.bar_index)
    ctx.marker(ctx.barstate.isconfirmed, text="Confirmed")
    ctx.marker(ctx.barstate.isrealtime, text="Realtime")
    ctx.marker(ctx.barstate.isnew, text="New")

def on_preview(ctx, bar):
    seen = ctx.state("seen", 0)
    seen.value += 100
    ctx.plot("PreviewSeen", seen.value)
"""
    session = pn.PyneIncrementalSession(
        script=script,
        settings=pn.PyneSettings(executor_mode="inline"),
    )

    session.seed(_bars()[:2])
    session.on_bar_updated({"time": 3, "open": 1, "high": 3, "low": 1, "close": 2.5, "volume": 100})
    closed = session.on_bar_closed({"time": 3, "open": 1, "high": 3, "low": 1, "close": 3.0, "volume": 100})
    snapshot = session.snapshot_result()

    assert _line_values(closed, "seen") == [3.0]
    assert _line_values(closed, "barindex") == [2.0]
    assert _marker_times(closed, "confirmed") == [3]
    assert _marker_times(closed, "realtime") == [3]
    assert _marker_times(closed, "new") == []
    assert _line_values(snapshot, "seen") == [1.0, 2.0, 3.0]
    assert snapshot.meta["bar_index"] == 2
    assert snapshot.meta["barstate"]["isconfirmed"] is True


def test_incremental_strategy_entry_close_matches_batch_series_and_report() -> None:
    batch_script = """
strategy("Batch Basic", overlay=True, initial_capital=1000)
strategy.entry_when(bar_index == 0, "A", strategy.long, qty=2, price=close)
strategy.close("A", when=bar_index == 2, qty=1, price=close)
plot(strategy.position_size, "Position")
plot(strategy.equity, "Equity")
plot(strategy.netprofit, "Net Profit")
"""
    incremental_script = """
indicator("Incremental Basic", mode="incremental", overlay=True)

def init(ctx):
    ctx.strategy.configure(initial_capital=1000)

def on_bar(ctx, bar):
    ctx.strategy.entry("A", ctx.strategy.long, qty=2, price=bar.close, when=ctx.bar_index == 0)
    ctx.strategy.close("A", qty=1, price=bar.close, when=ctx.bar_index == 2)
    ctx.plot("Position", ctx.strategy.position_size)
    ctx.plot("Equity", ctx.strategy.equity)
    ctx.plot("Net Profit", ctx.strategy.netprofit)
"""

    batch = pn.run(batch_script, _bars(), executor_mode="inline")
    incremental = pn.run(incremental_script, _bars(), executor_mode="inline")

    assert batch.ok
    assert incremental.ok
    _assert_strategy_matches_batch(incremental, batch)


def test_incremental_strategy_short_partial_close_matches_batch_report() -> None:
    bars = [
        *_bars(),
        {"time": 4, "open": 1, "high": 4, "low": 1, "close": 4.0, "volume": 100},
    ]
    batch_script = """
strategy("Short Partial", overlay=True, initial_capital=1000)
strategy.entry_when(bar_index == 0, "S", strategy.short, qty=3, price=close)
strategy.close("S", when=bar_index == 2, qty_percent=50, price=close)
plot(strategy.position_size, "Position")
plot(strategy.equity, "Equity")
plot(strategy.netprofit, "Net Profit")
"""
    incremental_script = """
indicator("Incremental Short Partial", mode="incremental", overlay=True)

def init(ctx):
    ctx.strategy.configure(initial_capital=1000)

def on_bar(ctx, bar):
    ctx.strategy.entry("S", ctx.strategy.short, qty=3, price=bar.close, when=ctx.bar_index == 0)
    ctx.strategy.close("S", qty_percent=50, price=bar.close, when=ctx.bar_index == 2)
    ctx.plot("Position", ctx.strategy.position_size)
    ctx.plot("Equity", ctx.strategy.equity)
    ctx.plot("Net Profit", ctx.strategy.netprofit)
"""

    batch = pn.run(batch_script, bars, executor_mode="inline")
    incremental = pn.run(incremental_script, bars, executor_mode="inline")

    assert batch.ok
    assert incremental.ok
    _assert_strategy_matches_batch(incremental, batch)


def test_incremental_strategy_reverse_entry_matches_batch_report() -> None:
    bars = [
        *_bars(),
        {"time": 4, "open": 1, "high": 4, "low": 1, "close": 4.0, "volume": 100},
    ]
    batch_script = """
strategy("Reverse", overlay=True, initial_capital=1000)
strategy.entry_when(bar_index == 0, "L", strategy.long, qty=2, price=close)
strategy.entry_when(bar_index == 2, "S", strategy.short, qty=3, price=close)
plot(strategy.position_size, "Position")
plot(strategy.equity, "Equity")
plot(strategy.netprofit, "Net Profit")
"""
    incremental_script = """
indicator("Incremental Reverse", mode="incremental", overlay=True)

def init(ctx):
    ctx.strategy.configure(initial_capital=1000)

def on_bar(ctx, bar):
    ctx.strategy.entry("L", ctx.strategy.long, qty=2, price=bar.close, when=ctx.bar_index == 0)
    ctx.strategy.entry("S", ctx.strategy.short, qty=3, price=bar.close, when=ctx.bar_index == 2)
    ctx.plot("Position", ctx.strategy.position_size)
    ctx.plot("Equity", ctx.strategy.equity)
    ctx.plot("Net Profit", ctx.strategy.netprofit)
"""

    batch = pn.run(batch_script, bars, executor_mode="inline")
    incremental = pn.run(incremental_script, bars, executor_mode="inline")

    assert batch.ok
    assert incremental.ok
    _assert_strategy_matches_batch(incremental, batch)


def test_incremental_strategy_seed_matches_closed_bar_session_snapshot() -> None:
    script = """
indicator("Incremental Strategy Replay", mode="incremental", overlay=True)

def init(ctx):
    ctx.strategy.configure(initial_capital=1000)

def on_bar(ctx, bar):
    ctx.strategy.entry("A", ctx.strategy.long, qty=2, price=bar.close, when=ctx.bar_index == 0)
    ctx.strategy.close("A", qty=1, price=bar.close, when=ctx.bar_index == 2)
    ctx.plot("Position", ctx.strategy.position_size)
    ctx.plot("Equity", ctx.strategy.equity)
    ctx.plot("Net Profit", ctx.strategy.netprofit)
"""

    seeded = pn.run(script, _bars(), executor_mode="inline")
    session = pn.PyneIncrementalSession(
        script=script,
        settings=pn.PyneSettings(executor_mode="inline"),
    )
    for bar in _bars():
        session.on_bar_closed(bar)
    snapshot = session.snapshot_result()

    assert seeded.ok
    assert _line_values(snapshot, "position") == _line_values(seeded, "position")
    assert _line_values(snapshot, "equity") == _line_values(seeded, "equity")
    assert _line_values(snapshot, "net_profit") == _line_values(seeded, "net_profit")
    assert snapshot.output["strategy"] == seeded.output["strategy"]

