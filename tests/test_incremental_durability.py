from __future__ import annotations

from typing import Any

import pyne_runtime as pn
import pytest

from pyne_runtime.security import PyneSecurityError


SCRIPT = """
indicator("Durable", mode="incremental", overlay=True)
values = cache("values", lambda: [])

def init(ctx):
    ctx.ta.sma("ma", period=2)

def on_bar(ctx, bar):
    cache("values", lambda: []).append(bar.close)
    count = ctx.state("count", 0)
    count.value += 1
    average = ctx.ta.sma("ma").update(bar.close)
    ctx.plot("Cache size", len(values))
    ctx.plot("Count", count.value)
    ctx.plot("MA", average)
"""


def _bar(time: int, close: float) -> dict[str, Any]:
    return {
        "time": time,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 10,
    }


def _bars(*values: float) -> list[dict[str, Any]]:
    return [_bar(index + 1, value) for index, value in enumerate(values)]


def test_incremental_snapshot_restore_matches_uninterrupted_execution() -> None:
    original = pn.PyneIncrementalSession(script=SCRIPT, retention_bars=4)
    original.seed(_bars(1, 2, 3))
    snapshot = original.snapshot_state()
    restored = pn.PyneIncrementalSession.from_snapshot(snapshot, script=SCRIPT)

    for item in (_bar(4, 4), _bar(5, 5)):
        expected_delta = original.on_bar_closed(item)
        restored_delta = restored.on_bar_closed(item)
        assert restored_delta == expected_delta

    assert restored.snapshot_result() == original.snapshot_result()
    assert restored.snapshot_result().meta["bar_index"] == 4
    cache_line = next(
        line for line in restored.snapshot_result().lines if line["name"] == "Cache size"
    )
    assert [point["value"] for point in cache_line["data"]] == [2.0, 3.0, 4.0, 5.0]


def test_incremental_snapshot_excludes_uncommitted_preview() -> None:
    session = pn.PyneIncrementalSession(script=SCRIPT)
    session.seed(_bars(1, 2))
    session.on_bar_updated(_bar(3, 99))

    restored = pn.PyneIncrementalSession.from_snapshot(session.snapshot_state(), script=SCRIPT)
    committed = restored.snapshot_result()

    assert committed.meta["bar_index"] == 1
    assert all(
        point["time"] <= 2
        for line in committed.lines
        for point in line["data"]
    )
    restored.on_bar_closed(_bar(3, 3))


def test_incremental_snapshot_rejects_mismatched_script_and_policy() -> None:
    session = pn.PyneIncrementalSession(script=SCRIPT, params={"length": 2}, retention_bars=3)
    session.seed(_bars(1))
    snapshot = session.snapshot_state()

    with pytest.raises(ValueError, match="script does not match"):
        pn.PyneIncrementalSession.from_snapshot(
            snapshot,
            script=SCRIPT + "\n# changed",
        )
    mismatched = pn.PyneIncrementalSession(
        script=SCRIPT,
        params={"length": 2},
        retention_bars=2,
    )
    with pytest.raises(ValueError, match="retention policy"):
        mismatched.restore_state(snapshot)


def test_incremental_snapshot_fails_closed_for_closure_state() -> None:
    script = """
indicator("Closure", mode="incremental")
def make_handler():
    values = []
    def handler(ctx, bar):
        values.append(bar.close)
        ctx.plot("Count", len(values))
    return handler
on_bar = make_handler()
"""
    session = pn.PyneIncrementalSession(script=script)
    session.seed(_bars(1))

    with pytest.raises(PyneSecurityError, match="cannot safely restore closure"):
        session.snapshot_state()


def test_incremental_retention_rolls_runtime_managed_history() -> None:
    session = pn.PyneIncrementalSession(script=SCRIPT, retention_bars=2)
    seeded = session.seed(_bars(1, 2, 3))

    assert {
        point["time"] for line in seeded.lines for point in line["data"]
    } == {2, 3}

    session.on_bar_closed(_bar(4, 4))
    rolled = session.snapshot_result()
    assert {
        point["time"] for line in rolled.lines for point in line["data"]
    } == {3, 4}
    assert rolled.meta["bar_index"] == 3
