"""Bounded execution trace contract for runtime and script diagnostics."""
from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from typing import Any


PYNE_TRACE_SCHEMA_VERSION = 1


class PyneTraceRecorder:
    """Collect bounded JSON-like events under a strict item budget."""

    def __init__(self, *, enabled: bool = False, max_events: int = 1_000) -> None:
        self.enabled = bool(enabled)
        self.max_events = max(int(max_events), 1)
        self._events: list[dict[str, Any]] = []
        self._dropped = 0

    def emit(self, event: str, /, **details: Any) -> None:
        if not self.enabled:
            return
        if len(self._events) >= self.max_events:
            self._dropped += 1
            return
        payload: dict[str, Any] = {
            "sequence": len(self._events),
            "event": str(event),
        }
        for key, value in details.items():
            payload[str(key)] = _trace_value(value)
        self._events.append(payload)

    @property
    def events(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._events)

    def snapshot(self) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        return {
            "schemaVersion": PYNE_TRACE_SCHEMA_VERSION,
            "maxEvents": self.max_events,
            "droppedEvents": self._dropped,
            "events": self.events,
        }


def _trace_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return {"type": type(value).__qualname__, "truncated": True}
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "na"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return value
    if isinstance(value, Mapping):
        items = list(value.items())
        result = {
            str(key): _trace_value(item, depth=depth + 1)
            for key, item in items[:32]
        }
        if len(items) > 32:
            result["__truncatedItems"] = len(items) - 32
        return result
    if isinstance(value, (list, tuple)):
        values = list(value)
        result = [_trace_value(item, depth=depth + 1) for item in values[:32]]
        if len(values) > 32:
            result.append({"truncatedItems": len(values) - 32})
        return result
    return {"type": type(value).__qualname__, "repr": repr(value)[:160]}
