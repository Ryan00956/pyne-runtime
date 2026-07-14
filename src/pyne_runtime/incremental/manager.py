"""Shared incremental session manager."""
from __future__ import annotations

import copy
import math
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

from .bar import IncrementalBar
from .result import IncrementalPyneResult
from .session import PyneIncrementalSession


@dataclass
class SharedPyneIncrementalSession:
    key: str
    session: PyneIncrementalSession
    ref_count: int = 0
    seeded: bool = False
    lock: threading.RLock = field(default_factory=threading.RLock)
    last_event_key: tuple[Any, ...] | None = None
    last_event_result: IncrementalPyneResult | None = None


class PyneIncrementalSessionManager:
    """Reference-counted in-process session cache for incremental Pyne."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, SharedPyneIncrementalSession] = {}

    def acquire(
        self,
        key: str,
        factory: Callable[[], PyneIncrementalSession],
    ) -> SharedPyneIncrementalSession:
        with self._lock:
            shared = self._sessions.get(key)
            if shared is None:
                shared = SharedPyneIncrementalSession(key=key, session=factory(), ref_count=0)
                self._sessions[key] = shared
            shared.ref_count += 1
            return shared

    def release(self, key: str) -> None:
        with self._lock:
            shared = self._sessions.get(key)
            if shared is None:
                return
            shared.ref_count -= 1
            if shared.ref_count <= 0:
                self._sessions.pop(key, None)

    def seed_or_snapshot(
        self,
        shared: SharedPyneIncrementalSession,
        ohlcv: list[dict[str, Any]],
        *,
        start_s: int | None = None,
        end_s: int | None = None,
    ) -> IncrementalPyneResult:
        with shared.lock:
            if not shared.seeded:
                result = shared.session.seed(ohlcv, start_s=start_s, end_s=end_s)
                shared.seeded = True
                return copy.deepcopy(result)
            return copy.deepcopy(shared.session.snapshot_result(start_s=start_s, end_s=end_s))

    def process_bar(
        self,
        shared: SharedPyneIncrementalSession,
        bar: dict[str, Any],
        *,
        preview: bool,
    ) -> IncrementalPyneResult:
        normalized_bar = IncrementalBar.from_dict(bar, is_confirmed=not preview).raw
        event_key = ("preview" if preview else "closed", _freeze_event_value(normalized_bar))
        with shared.lock:
            if shared.last_event_key == event_key and shared.last_event_result is not None:
                return copy.deepcopy(shared.last_event_result)
            result = (
                shared.session.on_bar_updated(bar)
                if preview
                else shared.session.on_bar_closed(bar)
            )
            shared.last_event_key = event_key
            shared.last_event_result = copy.deepcopy(result)
            return result

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "sessions": len(self._sessions),
                "keys": {
                    key: {"refCount": shared.ref_count, "seeded": shared.seeded}
                    for key, shared in self._sessions.items()
                },
            }


def _freeze_event_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        items = [
            (_freeze_event_value(key), _freeze_event_value(item))
            for key, item in value.items()
        ]
        return ("mapping", tuple(sorted(items, key=repr)))
    if isinstance(value, (list, tuple)):
        return ("sequence", tuple(_freeze_event_value(item) for item in value))
    if isinstance(value, (set, frozenset)):
        items = (_freeze_event_value(item) for item in value)
        return ("set", tuple(sorted(items, key=repr)))
    if isinstance(value, float):
        if math.isnan(value):
            return ("float", "nan")
        if math.isinf(value):
            return ("float", "inf" if value > 0 else "-inf")
        return ("float", value)
    if isinstance(value, (str, int, bool, bytes, type(None))):
        return (type(value).__name__, value)
    return (type(value).__qualname__, repr(value))
