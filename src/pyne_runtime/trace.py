"""Bounded execution trace contract for runtime and script diagnostics."""
from __future__ import annotations

import copy
import math
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Callable


PYNE_TRACE_SCHEMA_VERSION = 2
_DEFAULT_REDACTED_FIELDS = frozenset(
    {"api_key", "apikey", "authorization", "cookie", "password", "secret", "token"}
)


class PyneTraceRecorder:
    """Collect bounded JSON-like events and optional hierarchical timing spans."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        max_events: int = 1_000,
        timings_enabled: bool = True,
        slow_span_ms: float = 10.0,
        redacted_fields: tuple[str, ...] | list[str] | set[str] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.max_events = max(int(max_events), 1)
        self.timings_enabled = bool(timings_enabled)
        self.slow_span_ms = max(float(slow_span_ms), 0.0)
        self.redacted_fields = frozenset(
            str(item).strip().lower()
            for item in (redacted_fields or _DEFAULT_REDACTED_FIELDS)
            if str(item).strip()
        )
        self._events: list[dict[str, Any]] = []
        self._dropped = 0
        self._next_span_id = 0
        self._span_stack: list[str] = []
        self._span_metrics: dict[str, dict[str, float | int]] = {}
        self._slow_spans: list[dict[str, Any]] = []
        self._clock = clock or time.perf_counter

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
        if self._span_stack and "spanId" not in details:
            payload["spanId"] = self._span_stack[-1]
        for key, value in details.items():
            name = str(key)
            payload[name] = _trace_value(
                value,
                key=name,
                redacted_fields=self.redacted_fields,
            )
        self._events.append(payload)

    @contextmanager
    def span(
        self,
        name: str,
        /,
        *,
        category: str = "runtime",
        **details: Any,
    ) -> Iterator[str | None]:
        """Record a bounded parent-aware timing span when tracing is enabled."""
        if not self.enabled:
            yield None
            return
        span_id = f"s{self._next_span_id}"
        self._next_span_id += 1
        parent_id = self._span_stack[-1] if self._span_stack else None
        self._span_stack.append(span_id)
        started = self._clock() if self.timings_enabled else 0.0
        self.emit(
            "span.start",
            spanId=span_id,
            parentSpanId=parent_id,
            name=name,
            category=category,
            **details,
        )
        status = "ok"
        error_type: str | None = None
        try:
            yield span_id
        except BaseException as exc:
            status = "error"
            error_type = type(exc).__qualname__
            raise
        finally:
            duration_ms = (
                max((self._clock() - started) * 1_000.0, 0.0)
                if self.timings_enabled
                else None
            )
            if self._span_stack and self._span_stack[-1] == span_id:
                self._span_stack.pop()
            elif span_id in self._span_stack:
                self._span_stack.remove(span_id)
            self._record_span_metric(
                name=str(name),
                category=str(category),
                span_id=span_id,
                parent_id=parent_id,
                duration_ms=duration_ms,
                status=status,
            )
            self.emit(
                "span.complete",
                spanId=span_id,
                parentSpanId=parent_id,
                name=name,
                category=category,
                status=status,
                durationMs=None if duration_ms is None else round(duration_ms, 6),
                errorType=error_type,
            )

    @property
    def events(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._events)

    def snapshot(self) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        timings = [
            {
                "name": name,
                "category": str(metric["category"]),
                "count": int(metric["count"]),
                "errorCount": int(metric["errorCount"]),
                "totalDurationMs": round(float(metric["totalDurationMs"]), 6),
                "maxDurationMs": round(float(metric["maxDurationMs"]), 6),
            }
            for name, metric in sorted(self._span_metrics.items())
        ]
        return {
            "schemaVersion": PYNE_TRACE_SCHEMA_VERSION,
            "maxEvents": self.max_events,
            "droppedEvents": self._dropped,
            "redaction": {
                "enabled": bool(self.redacted_fields),
                "fieldCount": len(self.redacted_fields),
            },
            "timings": {
                "enabled": self.timings_enabled,
                "spans": timings,
                "slowSpanThresholdMs": self.slow_span_ms,
                "slowSpans": copy.deepcopy(self._slow_spans),
            },
            "events": self.events,
        }

    def _record_span_metric(
        self,
        *,
        name: str,
        category: str,
        span_id: str,
        parent_id: str | None,
        duration_ms: float | None,
        status: str,
    ) -> None:
        if duration_ms is None:
            return
        metric = self._span_metrics.setdefault(
            name,
            {
                "category": category,
                "count": 0,
                "errorCount": 0,
                "totalDurationMs": 0.0,
                "maxDurationMs": 0.0,
            },
        )
        metric["count"] = int(metric["count"]) + 1
        metric["errorCount"] = int(metric["errorCount"]) + (status == "error")
        metric["totalDurationMs"] = float(metric["totalDurationMs"]) + duration_ms
        metric["maxDurationMs"] = max(float(metric["maxDurationMs"]), duration_ms)
        if duration_ms >= self.slow_span_ms and len(self._slow_spans) < 32:
            self._slow_spans.append(
                {
                    "spanId": span_id,
                    "parentSpanId": parent_id,
                    "name": name,
                    "category": category,
                    "status": status,
                    "durationMs": round(duration_ms, 6),
                }
            )


def _trace_value(
    value: Any,
    *,
    key: str = "",
    depth: int = 0,
    redacted_fields: frozenset[str] = _DEFAULT_REDACTED_FIELDS,
) -> Any:
    if _is_redacted_key(key, redacted_fields):
        return "[REDACTED]"
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
            str(item_key): _trace_value(
                item,
                key=str(item_key),
                depth=depth + 1,
                redacted_fields=redacted_fields,
            )
            for item_key, item in items[:32]
        }
        if len(items) > 32:
            result["__truncatedItems"] = len(items) - 32
        return result
    if isinstance(value, (list, tuple)):
        values = list(value)
        result = [
            _trace_value(
                item,
                depth=depth + 1,
                redacted_fields=redacted_fields,
            )
            for item in values[:32]
        ]
        if len(values) > 32:
            result.append({"truncatedItems": len(values) - 32})
        return result
    return {"type": type(value).__qualname__}


def _is_redacted_key(key: str, redacted_fields: frozenset[str]) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    compact = normalized.replace("_", "")
    return any(
        field in normalized or field.replace("_", "") in compact
        for field in redacted_fields
    )
