"""Pine-like strategy event helpers."""
from __future__ import annotations

from typing import Any

import numpy as np

from .context import PyneContext
from .plot import OutputCollector
from .series import PyneSeries
from .state import PyneVar
from .values import is_na_value


class StrategyModule:
    """Lightweight Pine-like ``strategy`` namespace.

    This module emits deterministic strategy events and maintains a simple
    position timeline. It is not a broker simulator.
    """

    long = "long"
    short = "short"

    def __init__(self, context: PyneContext, collector: OutputCollector) -> None:
        self._context = context
        self._collector = collector
        self._position_size = np.zeros(context.bar_count, dtype=np.float64)
        self._position_avg_price = np.full(context.bar_count, np.nan, dtype=np.float64)
        self._touched = False
        self._event_seq = 0

    @property
    def position_size(self) -> PyneSeries:
        return PyneSeries(self._position_size.copy(), name="strategy.position_size")

    @property
    def position_avg_price(self) -> PyneSeries:
        return PyneSeries(
            self._position_avg_price.copy(),
            name="strategy.position_avg_price",
        )

    def entry(
        self,
        id: str,
        direction: str = long,
        *,
        qty: float = 1.0,
        when: PyneSeries | np.ndarray | list | bool = True,
        price: PyneSeries | np.ndarray | list | float | None = None,
        comment: str = "",
    ) -> None:
        """Emit entry events when ``when`` is true."""
        self.entry_when(
            when,
            id=id,
            direction=direction,
            qty=qty,
            price=price,
            comment=comment,
        )

    def entry_when(
        self,
        condition: PyneSeries | np.ndarray | list | bool,
        id: str,
        direction: str = long,
        *,
        qty: float = 1.0,
        price: PyneSeries | np.ndarray | list | float | None = None,
        comment: str = "",
    ) -> None:
        flags = _condition_values(condition, self._context.bar_count)
        prices = _price_values(price, self._context.close, self._context.bar_count)
        side = _normalize_direction(direction)
        signed_qty = abs(float(qty)) if side == self.long else -abs(float(qty))

        for idx, flag in enumerate(flags):
            if not flag:
                continue
            event_price = prices[idx]
            self._collector.strategy_orders.append({
                "time": self._context.times[idx],
                "id": str(id),
                "type": "entry",
                "side": side,
                "qty": abs(float(qty)),
                "price": round(float(event_price), 8),
                "position_after": round(float(signed_qty), 8),
                "comment": comment,
                "_seq": self._next_event_seq(),
            })
            self._touched = True

        self._replay_position()
        self._sync_position_snapshot()

    def close(
        self,
        id: str = "",
        *,
        when: PyneSeries | np.ndarray | list | bool = True,
        price: PyneSeries | np.ndarray | list | float | None = None,
        comment: str = "",
    ) -> None:
        """Emit close events when ``when`` is true."""
        self.close_when(when, id=id, price=price, comment=comment)

    def close_when(
        self,
        condition: PyneSeries | np.ndarray | list | bool,
        id: str = "",
        *,
        price: PyneSeries | np.ndarray | list | float | None = None,
        comment: str = "",
    ) -> None:
        flags = _condition_values(condition, self._context.bar_count)
        prices = _price_values(price, self._context.close, self._context.bar_count)

        for idx, flag in enumerate(flags):
            if not flag:
                continue
            current_position = float(self._position_size[idx])
            if current_position == 0:
                continue
            event_price = prices[idx]
            self._collector.strategy_orders.append({
                "time": self._context.times[idx],
                "id": str(id),
                "type": "close",
                "side": "flat",
                "qty": abs(current_position),
                "price": round(float(event_price), 8),
                "position_after": 0.0,
                "comment": comment,
                "_seq": self._next_event_seq(),
            })
            self._touched = True
            self._replay_position()

        self._sync_position_snapshot()

    def exit(
        self,
        id: str,
        *,
        from_entry: str = "",
        qty: float | None = None,
        stop: PyneSeries | np.ndarray | list | float | None = None,
        limit: PyneSeries | np.ndarray | list | float | None = None,
        when: PyneSeries | np.ndarray | list | bool = True,
        comment: str = "",
    ) -> None:
        """Emit stop/limit exit events for an open position.

        This is a deterministic event layer, not an intrabar fill simulator.
        When stop and limit are both touched on the same bar, stop wins.
        """
        if stop is None and limit is None:
            return

        flags = _condition_values(when, self._context.bar_count)
        stops = _optional_price_values(stop, self._context.bar_count)
        limits = _optional_price_values(limit, self._context.bar_count)
        high_values = _price_values(self._context.high, self._context.high, self._context.bar_count)
        low_values = _price_values(self._context.low, self._context.low, self._context.bar_count)

        for idx, flag in enumerate(flags):
            if not flag:
                continue
            current_position = float(self._position_size[idx])
            if current_position == 0:
                continue
            trigger = _exit_trigger(
                current_position=current_position,
                high=high_values[idx],
                low=low_values[idx],
                stop=stops[idx],
                limit=limits[idx],
            )
            if trigger is None:
                continue

            reason, event_price = trigger
            self._collector.strategy_orders.append({
                "time": self._context.times[idx],
                "id": str(id),
                "from_entry": str(from_entry),
                "type": "exit",
                "side": "flat",
                "qty": abs(float(qty)) if qty is not None else abs(current_position),
                "price": round(float(event_price), 8),
                "position_after": 0.0,
                "reason": reason,
                "comment": comment,
                "_seq": self._next_event_seq(),
            })
            self._touched = True
            self._replay_position()

        self._sync_position_snapshot()

    def _replay_position(self) -> None:
        current_size = 0.0
        current_avg = np.nan
        orders_by_time: dict[int, list[dict[str, Any]]] = {}
        for order in sorted(
            self._collector.strategy_orders,
            key=lambda item: (item.get("time", 0), item.get("_seq", 0)),
        ):
            orders_by_time.setdefault(int(order.get("time", 0)), []).append(order)

        for idx, timestamp in enumerate(self._context.times):
            for order in orders_by_time.get(timestamp, []):
                if order.get("type") == "entry":
                    qty = float(order.get("qty", 0.0))
                    current_size = qty if order.get("side") == self.long else -qty
                    current_avg = float(order.get("price", np.nan))
                elif order.get("type") in {"close", "exit"} and current_size != 0:
                    current_size = 0.0
                    current_avg = np.nan
            self._position_size[idx] = current_size
            self._position_avg_price[idx] = current_avg

    def _sync_position_snapshot(self) -> None:
        if not self._touched:
            return
        final_size = float(self._position_size[-1]) if len(self._position_size) else 0.0
        final_avg = (
            float(self._position_avg_price[-1])
            if len(self._position_avg_price) and not is_na_value(self._position_avg_price[-1])
            else None
        )
        self._collector.strategy_position = {
            "size": round(final_size, 8),
            "side": "long" if final_size > 0 else "short" if final_size < 0 else "flat",
            "avg_price": round(final_avg, 8) if final_avg is not None else None,
        }

    def _next_event_seq(self) -> int:
        self._event_seq += 1
        return self._event_seq


def _condition_values(value: Any, length: int) -> list[bool]:
    values = _values(value, length)
    return [False if is_na_value(item) else bool(item) for item in values]


def _price_values(value: Any, fallback: PyneSeries, length: int) -> list[float]:
    values = _values(fallback if value is None else value, length)
    return [np.nan if is_na_value(item) else float(item) for item in values]


def _optional_price_values(value: Any, length: int) -> list[float | None]:
    if value is None:
        return [None] * length
    values = _values(value, length)
    return [None if is_na_value(item) else float(item) for item in values]


def _exit_trigger(
    *,
    current_position: float,
    high: float,
    low: float,
    stop: float | None,
    limit: float | None,
) -> tuple[str, float] | None:
    if current_position > 0:
        if stop is not None and low <= stop:
            return "stop", stop
        if limit is not None and high >= limit:
            return "limit", limit
        return None
    if stop is not None and high >= stop:
        return "stop", stop
    if limit is not None and low <= limit:
        return "limit", limit
    return None


def _values(value: Any, length: int) -> list[Any]:
    if isinstance(value, PyneVar):
        value = value.get()
    if isinstance(value, PyneSeries):
        return value.to_numpy().tolist()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, list):
        if len(value) == length:
            return value
        if len(value) == 1:
            return value * length
        raise ValueError("strategy series inputs must match the OHLCV length")
    return [value] * length


def _normalize_direction(direction: str) -> str:
    normalized = str(direction or StrategyModule.long).lower()
    if normalized in {"short", "-1", "sell"}:
        return StrategyModule.short
    return StrategyModule.long
