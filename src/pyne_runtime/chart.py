"""Pine-like chart coordinate objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ChartPoint:
    """Mutable coordinate object used by Pine-like drawing APIs."""

    time: Any
    index: Any
    price: Any


class ChartPointNamespace:
    """Construct ``chart.point`` values for batch or incremental execution."""

    def __init__(
        self,
        *,
        current_time: Any | Callable[[], Any],
        current_index: Any | Callable[[], Any],
    ) -> None:
        self._current_time = current_time
        self._current_index = current_index

    def new(self, time: Any, index: Any, price: Any) -> ChartPoint:
        return ChartPoint(time=time, index=index, price=price)

    def now(self, price: Any) -> ChartPoint:
        return ChartPoint(
            time=_resolve_current(self._current_time),
            index=_resolve_current(self._current_index),
            price=price,
        )

    def from_index(self, index: Any, price: Any) -> ChartPoint:
        return ChartPoint(time=None, index=index, price=price)

    def from_time(self, time: Any, price: Any) -> ChartPoint:
        return ChartPoint(time=time, index=None, price=price)

    def copy(self, point: ChartPoint) -> ChartPoint:
        point = require_chart_point(point)
        return ChartPoint(time=point.time, index=point.index, price=point.price)


class ChartNamespace:
    """Pine-like ``chart`` namespace with runtime-owned point constructors."""

    def __init__(
        self,
        *,
        current_time: Any | Callable[[], Any],
        current_index: Any | Callable[[], Any],
    ) -> None:
        self.point = ChartPointNamespace(
            current_time=current_time,
            current_index=current_index,
        )


def require_chart_point(value: Any) -> ChartPoint:
    if not isinstance(value, ChartPoint):
        raise TypeError("drawing point must be a chart.point value")
    return value


def chart_point_coordinates(point: ChartPoint, xloc: str) -> tuple[Any, Any]:
    """Return the x/y coordinate selected by a drawing's ``xloc``."""
    point = require_chart_point(point)
    x = point.time if str(xloc) == "bar_time" else point.index
    return x, point.price


def _resolve_current(value: Any | Callable[[], Any]) -> Any:
    return value() if callable(value) else value
