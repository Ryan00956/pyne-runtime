from __future__ import annotations

import pytest

from pyne_runtime.incremental import IncrementalLimits, PyneIncrementalSessionManager
from pyne_runtime.incremental.limits import _LimitTracker
from pyne_runtime.security import PyneSecurityError


class DummySession:
    def __init__(self) -> None:
        self.seed_calls = 0
        self.snapshot_calls = 0
        self.closed_calls = 0
        self.preview_calls = 0

    def seed(self, ohlcv, *, start_s=None, end_s=None):
        self.seed_calls += 1
        return {"kind": "seed", "bars": len(ohlcv), "start_s": start_s, "end_s": end_s}

    def snapshot_result(self, *, start_s=None, end_s=None):
        self.snapshot_calls += 1
        return {"kind": "snapshot", "start_s": start_s, "end_s": end_s}

    def on_bar_closed(self, bar):
        self.closed_calls += 1
        return {"kind": "closed", "time": bar["time"], "calls": self.closed_calls}

    def on_bar_updated(self, bar):
        self.preview_calls += 1
        return {"kind": "preview", "time": bar["time"], "calls": self.preview_calls}


def test_incremental_session_manager_reference_counts_and_releases() -> None:
    manager = PyneIncrementalSessionManager()
    created: list[DummySession] = []

    def factory() -> DummySession:
        session = DummySession()
        created.append(session)
        return session

    first = manager.acquire("chart-a", factory)
    second = manager.acquire("chart-a", factory)

    assert first is second
    assert first.ref_count == 2
    assert len(created) == 1
    assert manager.snapshot()["keys"]["chart-a"]["refCount"] == 2

    manager.release("chart-a")
    assert manager.snapshot()["keys"]["chart-a"]["refCount"] == 1

    manager.release("chart-a")
    assert manager.snapshot()["sessions"] == 0


def test_incremental_session_manager_seeds_once_then_snapshots() -> None:
    manager = PyneIncrementalSessionManager()
    shared = manager.acquire("chart-a", DummySession)
    session = shared.session

    seeded = manager.seed_or_snapshot(shared, [{"time": 1}], start_s=1, end_s=2)
    snapshot = manager.seed_or_snapshot(shared, [{"time": 2}], start_s=3, end_s=4)

    assert seeded == {"kind": "seed", "bars": 1, "start_s": 1, "end_s": 2}
    assert snapshot == {"kind": "snapshot", "start_s": 3, "end_s": 4}
    assert session.seed_calls == 1
    assert session.snapshot_calls == 1
    assert manager.snapshot()["keys"]["chart-a"]["seeded"] is True


def test_incremental_session_manager_dedupes_repeated_bar_events() -> None:
    manager = PyneIncrementalSessionManager()
    shared = manager.acquire("chart-a", DummySession)
    session = shared.session
    bar = {"time": 1, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100}

    first = manager.process_bar(shared, bar, preview=False)
    second = manager.process_bar(shared, dict(bar), preview=False)
    preview = manager.process_bar(shared, dict(bar), preview=True)

    assert first == second
    assert first is not second
    assert preview["kind"] == "preview"
    assert session.closed_calls == 1
    assert session.preview_calls == 1


def test_incremental_session_manager_dedupe_includes_all_bar_metadata() -> None:
    manager = PyneIncrementalSessionManager()
    shared = manager.acquire("chart-a", DummySession)
    session = shared.session
    base = {"time": 1, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100}

    first = manager.process_bar(shared, base, preview=False)
    with_close = manager.process_bar(shared, {**base, "time_close": 2}, preview=False)
    with_session = manager.process_bar(
        shared,
        {**base, "time_close": 2, "session": {"isfirstbar": True}},
        preview=False,
    )
    with_raw = manager.process_bar(
        shared,
        {
            **base,
            "time_close": 2,
            "session": {"isfirstbar": True},
            "provider": {"flags": ["live", "adjusted"]},
        },
        preview=False,
    )
    duplicate = manager.process_bar(
        shared,
        {
            "provider": {"flags": ["live", "adjusted"]},
            "session": {"isfirstbar": "true"},
            "time_close": "2",
            "time": 1.0,
            "open": 1.0,
            "high": 2.0,
            "low": 1.0,
            "close": 1.5,
            "volume": 100.0,
        },
        preview=False,
    )

    assert [first["calls"], with_close["calls"], with_session["calls"], with_raw["calls"]] == [
        1,
        2,
        3,
        4,
    ]
    assert duplicate == with_raw
    assert duplicate is not with_raw
    assert session.closed_calls == 4


def test_incremental_limits_reject_oversized_windows() -> None:
    tracker = _LimitTracker(
        IncrementalLimits(
            enabled=True,
            max_window_size=2,
            max_total_window_items=3,
        )
    )

    tracker.reserve_window(2, label="fast")

    with pytest.raises(PyneSecurityError, match="exceeds safe-mode limit"):
        tracker.reserve_window(3, label="slow")

    with pytest.raises(PyneSecurityError, match="exceeding safe-mode total"):
        tracker.reserve_window(2, label="extra")
