from __future__ import annotations

import pyne_runtime as pn


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
        {"time": 2, "open": 2, "high": 3, "low": 1.5, "close": 2.5, "volume": 20},
    ]


def _settings(*, max_events: int = 100) -> pn.PyneSettings:
    return pn.PyneSettings(
        executor_mode="inline",
        trace_enabled=True,
        trace_max_events=max_events,
        timeframe="1S",
    )


def test_batch_trace_records_lifecycle_output_and_custom_events() -> None:
    result = pn.run(
        """
indicator("Trace")
trace.emit("decision", accepted=True, score=1.5)
plot(close, "Close")
""",
        _bars(),
        settings=_settings(),
    )

    assert result.ok, result.error
    trace = result.meta["trace"]
    assert trace["schemaVersion"] == pn.PYNE_TRACE_SCHEMA_VERSION
    assert trace["droppedEvents"] == 0
    events = trace["events"]
    assert events[0]["event"] == "execution.start"
    assert next(item for item in events if item["event"] == "decision")["accepted"] is True
    assert events[-1]["event"] == "execution.complete"
    assert events[-1]["status"] == "ok"


def test_trace_is_absent_by_default_and_survives_process_transport() -> None:
    ordinary = pn.run("plot(close, 'Close')", _bars(), executor_mode="inline")
    process = pn.run(
        "trace.emit('child'); plot(close, 'Close')",
        _bars(),
        settings=pn.PyneSettings(
            executor_mode="process",
            trace_enabled=True,
            trace_max_events=10,
        ),
    )

    assert "trace" not in ordinary.meta
    assert process.ok, process.error
    assert any(item["event"] == "child" for item in process.meta["trace"]["events"])


def test_trace_budget_is_strict_and_reports_dropped_events() -> None:
    result = pn.run(
        """
trace.emit("one")
trace.emit("two")
trace.emit("three")
plot(close, "Close")
""",
        _bars(),
        settings=_settings(max_events=3),
    )

    assert result.ok, result.error
    trace = result.meta["trace"]
    assert len(trace["events"]) == 3
    assert trace["droppedEvents"] == 2
    assert [item["event"] for item in trace["events"]] == ["execution.start", "one", "two"]


def test_failed_execution_still_returns_bounded_trace() -> None:
    result = pn.run("missing_function()", _bars(), settings=_settings())

    assert not result.ok
    assert result.code == "PYNE_RUNTIME_ERROR"
    events = result.meta["trace"]["events"]
    assert events[0]["event"] == "execution.start"
    assert events[-1]["event"] == "execution.complete"
    assert events[-1]["status"] == "error"


def test_incremental_preview_trace_is_isolated_from_committed_session() -> None:
    script = """
indicator("Incremental Trace", mode="incremental")
def on_bar(ctx, bar):
    ctx.trace.emit("decision", time=bar.time, preview=bar.is_realtime and not bar.is_confirmed)
    trace.emit("global.decision", time=bar.time)
    total = ctx.state("total", 0.0)
    total.value += bar.close
    ctx.plot("Total", total.value)
"""
    session = pn.PyneIncrementalSession(script=script, settings=_settings())
    session.seed([_bars()[0]])

    preview = session.on_bar_updated(_bars()[1])
    committed_before = session.snapshot_result()
    committed = session.on_bar_closed(_bars()[1])

    preview_times = [
        item.get("time")
        for item in preview.meta["trace"]["events"]
        if item["event"] == "decision"
    ]
    committed_before_times = [
        item.get("time")
        for item in committed_before.meta["trace"]["events"]
        if item["event"] == "decision"
    ]
    committed_times = [
        item.get("time")
        for item in committed.meta["trace"]["events"]
        if item["event"] == "decision"
    ]

    assert preview_times == [1, 2]
    assert committed_before_times == [1]
    assert committed_times == [1, 2]
    assert any(
        item["event"] == "state.change" and item["name"] == "total"
        for item in committed.meta["trace"]["events"]
    )


def test_process_local_restore_keeps_session_and_context_trace_unified() -> None:
    script = """
indicator("Restored Trace", mode="incremental")
def on_bar(ctx, bar):
    ctx.trace.emit("decision", time=bar.time)
"""
    settings = _settings()
    original = pn.PyneIncrementalSession(script=script, settings=settings)
    original.seed([_bars()[0]])

    restored = pn.PyneIncrementalSession.from_snapshot(
        original.snapshot_state(),
        script=script,
        settings=settings,
    )
    result = restored.on_bar_closed(_bars()[1])

    assert restored.trace is restored._ctx.trace
    assert [
        item["time"]
        for item in result.meta["trace"]["events"]
        if item["event"] == "decision"
    ] == [1, 2]
