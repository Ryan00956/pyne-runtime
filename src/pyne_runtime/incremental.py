"""Incremental Pyne runtime primitives.

This module supports stateful user scripts that define ``on_bar`` and process
one bar at a time. Batch Pyne remains implemented by ``runtime.py``.
"""
from __future__ import annotations

import ast
import copy
import inspect
import math
import re
import threading
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .barstate import PyneIncrementalBarState
from .cache import pyne as pyne_cache_namespace
from .color import color as color_singleton
from .math_ext import pyne_math
from .metadata import SessionInfo, SymbolInfo, TimeframeInfo, normalize_session_info
from .security import (
    PyneSecurityError,
    PyneSecurityPolicy,
    build_builtins,
    execution_timeout,
    validate_script_security,
)
from .settings import PyneSettings

SAFE_MAX_WINDOW_SIZE = 10_000
SAFE_MAX_TOTAL_WINDOW_ITEMS = 50_000
SAFE_MAX_STATE_KEYS = 100


@dataclass
class IncrementalPyneResult:
    ok: bool = True
    error: str | None = None
    code: str | None = None
    line: int | None = None
    column: int | None = None
    hint: str | None = None
    lines: list[dict[str, Any]] = field(default_factory=list)
    output: dict[str, Any] = field(default_factory=dict)
    param_schema: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class IncrementalBar:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_confirmed: bool = True
    bar_index: int = -1
    last_bar_index: int = -1
    is_first: bool = False
    is_last: bool = False
    is_history: bool = False
    is_realtime: bool = False
    is_new: bool = False
    is_last_confirmed_history: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, item: dict[str, Any], *, is_confirmed: bool = True) -> "IncrementalBar":
        return cls(
            time=int(item.get("time", 0)),
            open=float(item.get("open", 0)),
            high=float(item.get("high", 0)),
            low=float(item.get("low", 0)),
            close=float(item.get("close", 0)),
            volume=float(item.get("volume", 0)),
            is_confirmed=is_confirmed,
            raw=dict(item),
        )


class StateCell:
    """Mutable state value exposed to incremental scripts."""

    def __init__(self, value: Any) -> None:
        self.value = value


class Window:
    """Fixed-size rolling window exposed to incremental scripts."""

    def __init__(self, size: int) -> None:
        self.size = max(int(size), 1)
        self._values: deque[Any] = deque(maxlen=self.size)

    def append(self, value: Any) -> None:
        self._values.append(value)

    @property
    def full(self) -> bool:
        return len(self._values) >= self.size

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self):
        return iter(self._values)

    def __getitem__(self, index: int) -> Any:
        return list(self._values)[index]

    def values(self) -> list[Any]:
        return list(self._values)


@dataclass
class IncrementalLimits:
    enabled: bool = False
    max_window_size: int = SAFE_MAX_WINDOW_SIZE
    max_total_window_items: int = SAFE_MAX_TOTAL_WINDOW_ITEMS
    max_state_keys: int = SAFE_MAX_STATE_KEYS

    @classmethod
    def for_policy(cls, policy: PyneSecurityPolicy) -> "IncrementalLimits":
        return cls(enabled=policy.mode == "safe")


class _LimitTracker:
    def __init__(self, limits: IncrementalLimits) -> None:
        self.limits = limits
        self.total_window_items = 0

    def reserve_window(self, size: int, *, label: str) -> None:
        if not self.limits.enabled:
            return
        normalized = max(int(size), 1)
        if normalized > self.limits.max_window_size:
            raise PyneSecurityError(
                f"Incremental window '{label}' size {normalized} exceeds safe-mode limit "
                f"{self.limits.max_window_size}"
            )
        next_total = self.total_window_items + normalized
        if next_total > self.limits.max_total_window_items:
            raise PyneSecurityError(
                f"Incremental windows need {next_total} items, exceeding safe-mode total "
                f"limit {self.limits.max_total_window_items}"
            )
        self.total_window_items = next_total


class _StepSMA:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.window: deque[float] = deque()
        self.sum = 0.0

    def update(self, value: Any) -> float | None:
        if value is None:
            return None
        number = float(value)
        self.window.append(number)
        self.sum += number
        if len(self.window) > self.period:
            self.sum -= self.window.popleft()
        if len(self.window) < self.period:
            return None
        return self.sum / self.period


class _StepEMA:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.alpha = 2.0 / (self.period + 1)
        self.count = 0
        self.seed_sum = 0.0
        self.ema: float | None = None

    def update(self, value: Any) -> float | None:
        if value is None:
            return self.ema
        number = float(value)
        if self.ema is None:
            self.count += 1
            self.seed_sum += number
            if self.count < self.period:
                return None
            self.ema = self.seed_sum / self.period
            return self.ema
        self.ema = self.alpha * number + (1 - self.alpha) * self.ema
        return self.ema


class _StepBOLL:
    def __init__(self, period: int, multiplier: float = 2.0) -> None:
        self.period = max(int(period), 1)
        self.multiplier = float(multiplier)
        self.window: deque[float] = deque()
        self.sum = 0.0
        self.sumsq = 0.0

    def update(self, value: Any) -> tuple[float | None, float | None, float | None]:
        if value is None:
            return None, None, None
        number = float(value)
        self.window.append(number)
        self.sum += number
        self.sumsq += number * number
        if len(self.window) > self.period:
            removed = self.window.popleft()
            self.sum -= removed
            self.sumsq -= removed * removed
        if len(self.window) < self.period:
            return None, None, None
        mid = self.sum / self.period
        variance = max(self.sumsq / self.period - mid * mid, 0.0)
        std = math.sqrt(variance)
        return mid + self.multiplier * std, mid, mid - self.multiplier * std


class _StepMACD:
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        self.fast = _StepEMA(max(int(fast), 1))
        self.slow = _StepEMA(max(int(slow), 1))
        self.signal = _StepEMA(max(int(signal), 1))

    def update(self, value: Any) -> tuple[float | None, float | None, float | None]:
        fast_value = self.fast.update(value)
        slow_value = self.slow.update(value)
        if fast_value is None or slow_value is None:
            return None, None, None
        dif = fast_value - slow_value
        dea = self.signal.update(dif)
        hist = dif - dea if dea is not None else None
        return dif, dea, hist


class _StepRSI:
    def __init__(self, period: int = 14) -> None:
        self.period = max(int(period), 1)
        self.prev: float | None = None
        self.count = 0
        self.gain_sum = 0.0
        self.loss_sum = 0.0
        self.avg_gain: float | None = None
        self.avg_loss: float | None = None

    def update(self, value: Any) -> float | None:
        if value is None:
            return None
        current = float(value)
        if self.prev is None:
            self.prev = current
            return None
        delta = current - self.prev
        self.prev = current
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        if self.avg_gain is None or self.avg_loss is None:
            self.count += 1
            self.gain_sum += gain
            self.loss_sum += loss
            if self.count < self.period:
                return None
            self.avg_gain = self.gain_sum / self.period
            self.avg_loss = self.loss_sum / self.period
        else:
            self.avg_gain = (self.avg_gain * (self.period - 1) + gain) / self.period
            self.avg_loss = (self.avg_loss * (self.period - 1) + loss) / self.period
        return _rsi_from_avgs(self.avg_gain, self.avg_loss)


class _StepATR:
    def __init__(self, period: int = 14) -> None:
        self.period = max(int(period), 1)
        self.prev_close: float | None = None
        self.count = 0
        self.tr_sum = 0.0
        self.atr: float | None = None

    def update(self, bar_or_high: Any, low: Any = None, close: Any = None) -> float | None:
        if low is None and close is None:
            high = float(getattr(bar_or_high, "high"))
            low = float(getattr(bar_or_high, "low"))
            close = float(getattr(bar_or_high, "close"))
        else:
            high = float(bar_or_high)
            low = float(low)
            close = float(close)

        if self.prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - self.prev_close), abs(low - self.prev_close))
        self.prev_close = close

        if self.atr is None:
            self.count += 1
            self.tr_sum += tr
            if self.count < self.period:
                return None
            self.atr = self.tr_sum / self.period
        else:
            self.atr = (self.atr * (self.period - 1) + tr) / self.period
        return self.atr


class _StepMonotonic:
    def __init__(self, period: int, *, highest: bool) -> None:
        self.period = max(int(period), 1)
        self.highest = highest
        self.index = -1
        self.window: deque[tuple[int, float]] = deque()

    def update(self, value: Any) -> float | None:
        if value is None:
            return None
        self.index += 1
        number = float(value)
        expiry = self.index - self.period
        while self.window and self.window[0][0] <= expiry:
            self.window.popleft()
        if self.highest:
            while self.window and self.window[-1][1] <= number:
                self.window.pop()
        else:
            while self.window and self.window[-1][1] >= number:
                self.window.pop()
        self.window.append((self.index, number))
        if self.index + 1 < self.period:
            return None
        return self.window[0][1]


class IncrementalTaNamespace:
    """Stateful TA helper namespace available as ``ctx.ta``."""

    def __init__(self, limits: _LimitTracker | None = None) -> None:
        self._helpers: dict[str, Any] = {}
        self._limits = limits or _LimitTracker(IncrementalLimits(enabled=False))

    def sma(self, name: str, period: int | None = None) -> _StepSMA:
        key = f"sma:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.sma('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepSMA(period)
        return self._helpers[key]

    def ema(self, name: str, period: int | None = None) -> _StepEMA:
        key = f"ema:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.ema('{name}') has not been initialized")
            self._helpers[key] = _StepEMA(period)
        return self._helpers[key]

    def boll(self, name: str, period: int | None = None, multiplier: float = 2.0) -> _StepBOLL:
        key = f"boll:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.boll('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepBOLL(period, multiplier)
        return self._helpers[key]

    def macd(
        self,
        name: str,
        fast: int | None = None,
        slow: int = 26,
        signal: int = 9,
    ) -> _StepMACD:
        key = f"macd:{name}"
        if key not in self._helpers:
            if fast is None:
                raise ValueError(f"ctx.ta.macd('{name}') has not been initialized")
            self._helpers[key] = _StepMACD(fast, slow, signal)
        return self._helpers[key]

    def rsi(self, name: str, period: int | None = None) -> _StepRSI:
        key = f"rsi:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.rsi('{name}') has not been initialized")
            self._helpers[key] = _StepRSI(period)
        return self._helpers[key]

    def atr(self, name: str, period: int | None = None) -> _StepATR:
        key = f"atr:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.atr('{name}') has not been initialized")
            self._helpers[key] = _StepATR(period)
        return self._helpers[key]

    def highest(self, name: str, period: int | None = None) -> _StepMonotonic:
        key = f"highest:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.highest('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepMonotonic(period, highest=True)
        return self._helpers[key]

    def lowest(self, name: str, period: int | None = None) -> _StepMonotonic:
        key = f"lowest:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.lowest('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepMonotonic(period, highest=False)
        return self._helpers[key]


class IncrementalStrategyNamespace:
    """Pine-like strategy helper for one-bar-at-a-time callbacks."""

    long = "long"
    short = "short"
    oca = type("IncrementalStrategyOca", (), {
        "none": "none",
        "cancel": "cancel",
        "reduce": "reduce",
    })
    same_bar = type("IncrementalStrategySameBarPriority", (), {
        "stop_first": "stop_first",
        "limit_first": "limit_first",
    })
    intrabar = type("IncrementalStrategyIntrabarPath", (), {
        "same_bar_priority": "same_bar_priority",
        "open_high_low_close": "open_high_low_close",
        "open_low_high_close": "open_low_high_close",
    })

    def __init__(self, context: "IncrementalContext") -> None:
        self._context = context
        self._initial_capital = 100000.0
        self._currency = ""
        self._orders: list[dict[str, Any]] = []
        self._pending_orders: list[dict[str, Any]] = []
        self._open_trades: list[dict[str, Any]] = []
        self._closed_trades: list[dict[str, Any]] = []
        self._grossprofit = 0.0
        self._grossloss = 0.0
        self._commission = 0.0
        self._event_seq = 0
        self._touched = False
        self._mintick = max(float(getattr(context.syminfo, "mintick", 0.0)), 0.0)
        self._backtest_fill_limits_assumption = 0
        self._same_bar_fill_priority = self.same_bar.stop_first
        self._intrabar_path = self.intrabar.same_bar_priority
        self._margin_long = 100.0
        self._margin_short = 100.0

    def configure(self, **kwargs: Any) -> None:
        if "initial_capital" in kwargs:
            self._initial_capital = float(kwargs["initial_capital"])
        if "currency" in kwargs:
            self._currency = str(kwargs["currency"] or "")
        if "mintick" in kwargs or "min_tick" in kwargs:
            self._mintick = max(float(kwargs.get("mintick", kwargs.get("min_tick", 0.0))), 0.0)
        if "backtest_fill_limits_assumption" in kwargs:
            self._backtest_fill_limits_assumption = max(int(kwargs["backtest_fill_limits_assumption"]), 0)
        if "same_bar_fill_priority" in kwargs:
            self._same_bar_fill_priority = _normalize_same_bar_fill_priority(
                str(kwargs["same_bar_fill_priority"])
            )
        if "intrabar_path" in kwargs:
            self._intrabar_path = _normalize_intrabar_path(str(kwargs["intrabar_path"]))
        if "margin_long" in kwargs:
            self._margin_long = max(float(kwargs["margin_long"]), 0.0)
        if "margin_short" in kwargs:
            self._margin_short = max(float(kwargs["margin_short"]), 0.0)

    @property
    def touched(self) -> bool:
        return self._touched

    @property
    def position_size(self) -> float:
        return _round8(sum(_signed_trade_qty(trade) for trade in self._open_trades))

    @property
    def position_avg_price(self) -> float | None:
        size = abs(self.position_size)
        if size <= 0:
            return None
        weighted = sum(abs(float(trade["qty"])) * float(trade["entry_price"]) for trade in self._open_trades)
        return _round8(weighted / size)

    @property
    def grossprofit(self) -> float:
        return _round8(self._grossprofit)

    @property
    def grossloss(self) -> float:
        return _round8(self._grossloss)

    @property
    def netprofit(self) -> float:
        return _round8(self._grossprofit + self._grossloss - self._commission)

    @property
    def openprofit(self) -> float:
        return _round8(sum(_trade_open_profit(trade, self._current_price()) for trade in self._open_trades))

    @property
    def equity(self) -> float:
        return _round8(self._initial_capital + self.netprofit + self.openprofit)

    def begin_bar(self) -> None:
        if not self._pending_orders:
            return
        still_pending = []
        for order in self._pending_orders:
            if not self._try_fill_pending_order(order):
                still_pending.append(order)
        self._pending_orders = still_pending

    def entry(
        self,
        id: str,
        direction: str = long,
        *,
        qty: float = 1.0,
        price: float | None = None,
        limit: float | None = None,
        stop: float | None = None,
        oca_name: str = "",
        oca_type: str | None = None,
        when: bool = True,
        comment: str = "",
    ) -> None:
        self._submit_position_order(
            "entry",
            id,
            direction,
            qty=qty,
            price=price,
            limit=limit,
            stop=stop,
            oca_name=oca_name,
            oca_type=oca_type,
            when=when,
            comment=comment,
        )

    def order(
        self,
        id: str,
        direction: str = long,
        *,
        qty: float = 1.0,
        price: float | None = None,
        limit: float | None = None,
        stop: float | None = None,
        oca_name: str = "",
        oca_type: str | None = None,
        when: bool = True,
        comment: str = "",
    ) -> None:
        self._submit_position_order(
            "order",
            id,
            direction,
            qty=qty,
            price=price,
            limit=limit,
            stop=stop,
            oca_name=oca_name,
            oca_type=oca_type,
            when=when,
            comment=comment,
        )

    def _submit_position_order(
        self,
        order_type: str,
        id: str,
        direction: str,
        *,
        qty: float,
        price: float | None,
        limit: float | None,
        stop: float | None,
        oca_name: str,
        oca_type: str | None,
        when: bool,
        comment: str,
    ) -> None:
        if not when:
            return
        qty_abs = abs(float(qty))
        if qty_abs <= 0:
            return
        side = self._normalize_direction(direction)
        base_price = self._price_or_current(price)
        order = {
            "time": self._current_time(),
            "id": str(id),
            "type": order_type,
            "side": side,
            "qty": _round8(qty_abs),
            "price": _round8(base_price),
            "position_after": self.position_size,
            "comment": comment,
            "_seq": self._next_seq(),
            "_base_price": float(base_price),
            "_limit": _optional_float(limit),
            "_stop": _optional_float(stop),
            "_submit_time": self._current_time(),
            "_requested_fill_qty": qty_abs,
            "_oca_name": str(oca_name or ""),
            "_oca_type": _normalize_oca_type(oca_type),
        }
        self._orders.append(order)
        self._touched = True
        if limit is not None or stop is not None:
            order["_pending_submission"] = True
            order["_active"] = False
            if not self._try_fill_pending_order(order):
                self._pending_orders.append(order)
            return
        self._fill_entry_order(order, fill_price=base_price, reason=None)

    def _fill_entry_order(self, order: dict[str, Any], *, fill_price: float, reason: str | None) -> None:
        side = self._normalize_direction(str(order.get("side", self.long)))
        qty_abs = abs(float(order.get("qty", 0.0)))
        signed_qty = qty_abs if side == self.long else -qty_abs
        if self.position_size and (self.position_size > 0) != (signed_qty > 0):
            self._close_lots(id="", exit_id=str(order.get("id", "")), target_qty=abs(self.position_size), fill_price=fill_price)
        self._open_trades.append({
            "entry_id": str(order.get("id", "")),
            "entry_time": self._current_time(),
            "side": side,
            "qty": _round8(qty_abs),
            "entry_price": _round8(fill_price),
        })
        order["time"] = self._current_time()
        order["price"] = _round8(fill_price)
        order["position_after"] = self.position_size
        order["_active"] = True
        order["_filled_qty"] = qty_abs
        if order.get("_oca_name"):
            order["oca_name"] = order.get("_oca_name")
            order["oca_type"] = order.get("_oca_type") or self.oca.none
        if reason is not None:
            order["reason"] = reason
        self._apply_oca_after_fill(order)

    def _try_fill_pending_order(self, order: dict[str, Any]) -> bool:
        if order.get("_active"):
            return True
        if order.get("_canceled"):
            return True
        bar = self._context.current_bar
        if bar is None:
            return False
        trigger = _pending_trigger(
            side=self._normalize_direction(str(order.get("side", self.long))),
            high=float(bar.high),
            low=float(bar.low),
            limit=order.get("_limit"),
            stop=order.get("_stop"),
            tick_verify=self._limit_fill_verification_amount(),
            same_bar_fill_priority=self._same_bar_fill_priority,
            intrabar_path=self._intrabar_path,
        )
        if trigger is None:
            return False
        reason, fill_price = trigger
        self._fill_entry_order(order, fill_price=fill_price, reason=reason)
        return True

    def close(
        self,
        id: str = "",
        *,
        qty: float | None = None,
        qty_percent: float | None = None,
        price: float | None = None,
        when: bool = True,
        comment: str = "",
    ) -> None:
        if not when or not self._open_trades:
            return
        fill_price = self._price_or_current(price)
        target_qty = self._requested_close_qty(qty=qty, qty_percent=qty_percent)
        if target_qty <= 0:
            return
        closed_qty = self._close_lots(id=str(id), exit_id=str(id), target_qty=target_qty, fill_price=fill_price)
        if abs(closed_qty) <= 0:
            return
        self._touched = True
        self._orders.append({
            "time": self._current_time(),
            "id": str(id),
            "type": "close",
            "side": "flat",
            "qty": _round8(abs(closed_qty)),
            "price": _round8(fill_price),
            "position_after": self.position_size,
            "comment": comment,
            "_seq": self._next_seq(),
        })

    def close_all(self, *, price: float | None = None, when: bool = True, comment: str = "") -> None:
        if not when or not self._open_trades:
            return
        self.close("", qty=abs(self.position_size), price=price, when=True, comment=comment)
        if self._orders:
            self._orders[-1]["type"] = "close_all"

    def exit(
        self,
        id: str,
        *,
        from_entry: str = "",
        qty: float | None = None,
        qty_percent: float | None = None,
        stop: float | None = None,
        limit: float | None = None,
        when: bool = True,
        comment: str = "",
    ) -> None:
        if not when or not self._open_trades or (stop is None and limit is None):
            return
        current_position = self.position_size
        if current_position == 0:
            return
        bar = self._context.current_bar
        if bar is None:
            return
        trigger = _exit_trigger(
            current_position=current_position,
            high=float(bar.high),
            low=float(bar.low),
            stop=_optional_float(stop),
            limit=_optional_float(limit),
            tick_verify=self._limit_fill_verification_amount(),
            same_bar_fill_priority=self._same_bar_fill_priority,
            intrabar_path=self._intrabar_path,
        )
        if trigger is None:
            return
        reason, event_price = trigger
        target_qty = self._target_open_qty(str(from_entry))
        requested_qty = _requested_exit_qty(target_qty=target_qty, qty=qty, qty_percent=qty_percent)
        fill_qty = min(target_qty, abs(current_position), requested_qty)
        if fill_qty <= 0:
            return
        closed_qty = self._close_lots(
            id=str(from_entry),
            exit_id=str(id),
            target_qty=fill_qty,
            fill_price=event_price,
        )
        if abs(closed_qty) <= 0:
            return
        self._touched = True
        self._orders.append({
            "time": self._current_time(),
            "id": str(id),
            "from_entry": str(from_entry),
            "type": "exit",
            "side": "flat",
            "qty": _round8(abs(closed_qty)),
            "price": _round8(event_price),
            "position_after": self.position_size,
            "reason": reason,
            "comment": comment,
            "_base_price": float(event_price),
            "_target_qty": _round8(target_qty),
            "_requested_fill_qty": _round8(requested_qty),
            "_filled_qty": _round8(abs(closed_qty)),
            "_requested_qty": _optional_float(qty),
            "_qty_percent": _optional_float(qty_percent),
            "_seq": self._next_seq(),
            "_submit_time": self._current_time(),
        })

    def cancel(self, id: str, *, when: bool = True, comment: str = "") -> None:
        if not when:
            return
        canceled = self._cancel_pending(lambda order: str(order.get("id", "")) == str(id), canceled_by=str(id))
        if canceled <= 0:
            return
        self._touched = True
        self._orders.append({
            "time": self._current_time(),
            "id": str(id),
            "type": "cancel",
            "side": "flat",
            "qty": 0.0,
            "price": None,
            "position_after": self.position_size,
            "comment": comment,
            "canceled": canceled,
            "_seq": self._next_seq(),
            "_submit_time": self._current_time(),
        })

    def cancel_all(self, *, when: bool = True, comment: str = "") -> None:
        if not when:
            return
        canceled = self._cancel_pending(lambda order: True, canceled_by="cancel_all")
        if canceled <= 0:
            return
        self._touched = True
        self._orders.append({
            "time": self._current_time(),
            "id": "cancel_all",
            "type": "cancel_all",
            "side": "flat",
            "qty": 0.0,
            "price": None,
            "position_after": self.position_size,
            "comment": comment,
            "canceled": canceled,
            "_seq": self._next_seq(),
            "_submit_time": self._current_time(),
        })

    def to_report(self) -> dict[str, Any]:
        final_size = self.position_size
        final_avg = self.position_avg_price
        return {
            "orders": [
                {key: value for key, value in order.items() if not str(key).startswith("_")}
                for order in sorted(self._orders, key=lambda item: (item.get("time", 0), item.get("_seq", 0)))
                if order.get("_active", True)
            ],
            "position": {
                "size": final_size,
                "side": "long" if final_size > 0 else "short" if final_size < 0 else "flat",
                "avg_price": final_avg,
            },
            "summary": {
                "initial_capital": _round8(self._initial_capital),
                "currency": self._currency,
                "equity": self.equity,
                "netprofit": self.netprofit,
                "openprofit": self.openprofit,
                "grossprofit": self.grossprofit,
                "grossloss": self.grossloss,
                "commission": _round8(self._commission),
                "backtest_fill_limits_assumption": self._backtest_fill_limits_assumption,
                "same_bar_fill_priority": self._same_bar_fill_priority,
                "intrabar_path": self._intrabar_path,
                "margin_long": _round8(self._margin_long),
                "margin_short": _round8(self._margin_short),
            },
            "risk": {
                "locked": False,
                "max_drawdown": None,
                "max_drawdown_type": "percent_of_equity",
                "max_intraday_loss": None,
                "max_intraday_loss_type": "percent_of_equity",
                "max_position_size": None,
                "max_intraday_filled_orders": None,
            },
            "closedtrades": list(self._closed_trades),
            "opentrades": [
                {**trade, "profit": _round8(_trade_open_profit(trade, self._current_price()))}
                for trade in self._open_trades
            ],
            "lifecycle": _incremental_strategy_lifecycle_events(self._orders),
        }

    def _requested_close_qty(self, *, qty: float | None, qty_percent: float | None) -> float:
        position_qty = abs(self.position_size)
        if qty is not None:
            return min(position_qty, abs(float(qty)))
        if qty_percent is not None:
            return min(position_qty, position_qty * max(float(qty_percent), 0.0) / 100.0)
        return position_qty

    def _target_open_qty(self, from_entry: str) -> float:
        return _round8(sum(
            abs(float(trade.get("qty", 0.0)))
            for trade in self._open_trades
            if not from_entry or str(trade.get("entry_id", "")) == from_entry
        ))

    def _cancel_pending(self, predicate: Callable[[dict[str, Any]], bool], *, canceled_by: str) -> int:
        canceled = 0
        still_pending = []
        for order in self._pending_orders:
            if predicate(order):
                order["_canceled"] = True
                order["_canceled_time"] = self._current_time()
                order["_canceled_by"] = canceled_by
                canceled += 1
            else:
                still_pending.append(order)
        self._pending_orders = still_pending
        return canceled

    def _apply_oca_after_fill(self, filled_order: dict[str, Any]) -> None:
        oca_name = str(filled_order.get("_oca_name") or "")
        oca_type = str(filled_order.get("_oca_type") or self.oca.none)
        if not oca_name or oca_type == self.oca.none:
            return
        filled_qty = abs(float(filled_order.get("qty", 0.0)))
        for order in self._pending_orders:
            if order is filled_order:
                continue
            if order.get("_oca_name") != oca_name or order.get("_oca_type") != oca_type:
                continue
            if oca_type == self.oca.cancel:
                order["_canceled"] = True
                order["_canceled_time"] = self._current_time()
                order["_canceled_by"] = filled_order.get("id")
            elif oca_type == self.oca.reduce:
                remaining = max(float(order.get("qty", 0.0)) - filled_qty, 0.0)
                order["qty"] = _round8(remaining)
                if remaining <= 0:
                    order["_canceled"] = True
                    order["_canceled_time"] = self._current_time()
                    order["_canceled_by"] = filled_order.get("id")

    def _close_lots(self, *, id: str, exit_id: str, target_qty: float, fill_price: float) -> float:
        remaining = abs(float(target_qty))
        closed_signed_qty = 0.0
        kept: list[dict[str, Any]] = []
        for trade in self._open_trades:
            matches_id = not id or str(trade.get("entry_id", "")) == id
            if not matches_id or remaining <= 0:
                kept.append(trade)
                continue
            trade_qty = abs(float(trade["qty"]))
            closing_qty = min(trade_qty, remaining)
            remaining -= closing_qty
            side = str(trade["side"])
            profit = _realized_profit(side=side, qty=closing_qty, entry_price=float(trade["entry_price"]), exit_price=fill_price)
            if profit >= 0:
                self._grossprofit += profit
            else:
                self._grossloss += profit
            self._closed_trades.append({
                "entry_id": trade.get("entry_id", ""),
                "exit_id": exit_id,
                "side": side,
                "qty": _round8(closing_qty),
                "entry_price": trade.get("entry_price"),
                "exit_price": _round8(fill_price),
                "entry_time": trade.get("entry_time"),
                "exit_time": self._current_time(),
                "profit": _round8(profit),
                "net_profit": _round8(profit),
                "commission": 0.0,
            })
            closed_signed_qty += closing_qty if side == self.long else -closing_qty
            leftover_qty = trade_qty - closing_qty
            if leftover_qty > 1e-9:
                kept.append({**trade, "qty": _round8(leftover_qty)})
        self._open_trades = kept
        return _round8(closed_signed_qty)

    def _normalize_direction(self, direction: str) -> str:
        normalized = str(direction or "").lower()
        if normalized in {self.short, "strategy.short", "-1"}:
            return self.short
        return self.long

    def _price_or_current(self, price: float | None) -> float:
        return float(self._current_price() if price is None else price)

    def _current_price(self) -> float:
        if self._context.current_bar is None:
            return math.nan
        return float(self._context.current_bar.close)

    def _current_time(self) -> int:
        if self._context.current_bar is None:
            return 0
        return int(self._context.current_bar.time)

    def _next_seq(self) -> int:
        self._event_seq += 1
        return self._event_seq

    def _limit_fill_verification_amount(self) -> float:
        return self._backtest_fill_limits_assumption * self._mintick


class IncrementalContext:
    """Per-session context exposed to incremental Pyne callbacks."""

    def __init__(
        self,
        *,
        params: dict[str, Any],
        meta: dict[str, Any] | None = None,
        limits: IncrementalLimits | None = None,
        syminfo: SymbolInfo | None = None,
        timeframe: TimeframeInfo | None = None,
        session: SessionInfo | None = None,
    ) -> None:
        self.params = params
        self.meta = meta or {}
        self._limits = limits or IncrementalLimits(enabled=False)
        self._limit_tracker = _LimitTracker(self._limits)
        self.ta = IncrementalTaNamespace(self._limit_tracker)
        self.syminfo = syminfo or SymbolInfo()
        self.timeframe = timeframe or TimeframeInfo()
        self._default_session = session or SessionInfo()
        self.session = self._default_session
        self.strategy = IncrementalStrategyNamespace(self)
        self._states: dict[str, StateCell] = {}
        self._windows: dict[str, Window] = {}
        self._series: dict[str, dict[str, Any]] = {}
        self._markers: dict[str, dict[str, Any]] = {}
        self.current_bar: IncrementalBar | None = None
        self.bar_index = -1
        self.last_bar_index = -1
        self.barstate = PyneIncrementalBarState()

    def clone_for_preview(self) -> "IncrementalContext":
        clone = copy.deepcopy(self)
        clone._series = {}
        clone._markers = {}
        clone.current_bar = None
        return clone

    def clear_outputs(self) -> None:
        self._series = {}
        self._markers = {}

    def begin_bar(
        self,
        bar: IncrementalBar,
        *,
        bar_index: int,
        last_bar_index: int,
        barstate: PyneIncrementalBarState,
    ) -> None:
        bar.bar_index = bar_index
        bar.last_bar_index = last_bar_index
        bar.is_first = barstate.isfirst
        bar.is_last = barstate.islast
        bar.is_history = barstate.ishistory
        bar.is_realtime = barstate.isrealtime
        bar.is_new = barstate.isnew
        bar.is_last_confirmed_history = barstate.islastconfirmedhistory
        self.current_bar = bar
        self.bar_index = bar_index
        self.last_bar_index = last_bar_index
        self.barstate = barstate
        self.session = _session_info_for_bar(bar, self._default_session)
        self.strategy.begin_bar()

    def state(self, name: str, default: Any = None) -> StateCell:
        key = str(name)
        if key not in self._states:
            if self._limits.enabled and len(self._states) >= self._limits.max_state_keys:
                raise PyneSecurityError(
                    f"Incremental state keys exceed safe-mode limit {self._limits.max_state_keys}"
                )
            self._states[key] = StateCell(copy.deepcopy(default))
        return self._states[key]

    def window(self, name: str, size: int) -> Window:
        key = str(name)
        if key not in self._windows:
            self._limit_tracker.reserve_window(size, label=f"window:{key}")
            self._windows[key] = Window(size)
        return self._windows[key]

    def plot(
        self,
        name_or_value: Any,
        value: Any = None,
        *,
        title: str | None = None,
        color: str = "#f59e0b",
        pane: str = "main",
        linewidth: int = 2,
        style: str = "solid",
        type: str = "line",
    ) -> None:
        if self.current_bar is None:
            return

        if isinstance(name_or_value, str):
            name = name_or_value
            point_value = value
        else:
            name = title or "plot"
            point_value = name_or_value

        if point_value is None:
            return
        try:
            number = float(point_value)
        except (TypeError, ValueError):
            return
        if math.isnan(number):
            return

        local_id = _slug(name)
        entry = self._series.setdefault(local_id, {
            "id": local_id,
            "title": title or name,
            "color": color,
            "linewidth": linewidth,
            "style": style,
            "type": type,
            "pane": pane,
            "data": [],
        })
        entry["data"].append({
            "time": self.current_bar.time,
            "value": round(number, 8),
        })

    def marker(
        self,
        condition: bool,
        *,
        text: str = "",
        shape: str = "circle",
        color: str = "#f59e0b",
        position: str = "above",
        pane: str = "main",
    ) -> None:
        if self.current_bar is None or not condition:
            return
        key = _slug(text or shape or "marker")
        entry = self._markers.setdefault(key, {
            "id": key,
            "shape": shape,
            "color": color,
            "text": text,
            "position": position,
            "pane": pane,
            "data": [],
        })
        entry["data"].append({
            "time": self.current_bar.time,
            "shape": shape,
            "color": color,
            "text": text,
            "position": position,
            "pane": pane,
        })

    def to_result(self, *, start_s: int | None = None, end_s: int | None = None) -> IncrementalPyneResult:
        lines = []
        for item in self._series.values():
            data = _filter_points(item.get("data") or [], start_s, end_s)
            if not data:
                continue
            line = {**item, "data": data}
            lines.append({
                "id": line["id"],
                "name": line.get("title", line["id"]),
                "color": line.get("color", "#f59e0b"),
                "type": line.get("type", "line"),
                "pane": line.get("pane", "main"),
                "lineWidth": line.get("linewidth", 2),
                "lineStyle": _style_to_int(line.get("style", "solid")),
                "data": data,
            })

        markers = []
        for item in self._markers.values():
            data = _filter_points(item.get("data") or [], start_s, end_s)
            if data:
                markers.append({**item, "data": data})

        output: dict[str, Any] = {}
        if lines:
            output["lines"] = [
                {
                    "id": line.get("id"),
                    "title": line.get("name"),
                    "color": line.get("color"),
                    "linewidth": line.get("lineWidth", 2),
                    "style": "solid",
                    "pane": line.get("pane", "main"),
                    "data": line.get("data") or [],
                }
                for line in lines
            ]
        if markers:
            output["markers"] = markers
        if self.strategy.touched:
            output["strategy"] = self.strategy.to_report()

        return IncrementalPyneResult(
            ok=True,
            lines=lines,
            output=output,
            meta={
                **self.meta,
                "mode": "incremental",
                "bar_index": self.bar_index,
                "last_bar_index": self.last_bar_index,
                "barstate": asdict(self.barstate),
            },
        )


class PyneIncrementalSession:
    """Long-lived incremental Pyne execution session."""

    def __init__(
        self,
        *,
        script: str,
        params: dict[str, Any] | None = None,
        security_mode: str | None = None,
        policy: PyneSecurityPolicy | None = None,
        settings: PyneSettings | None = None,
    ) -> None:
        self.script = script
        self.params = params or {}
        self.settings = settings or PyneSettings.from_env()
        self.policy = policy or PyneSecurityPolicy.from_settings(self.settings, security_mode)
        self.security_mode = self.policy.mode
        self._limits = IncrementalLimits.for_policy(self.policy)
        self._globals: dict[str, Any] = {}
        self._meta: dict[str, Any] = {}
        self._init_func: Callable[..., Any] | None = None
        self._on_bar: Callable[..., Any] | None = None
        self._on_preview: Callable[..., Any] | None = None
        self._ctx: IncrementalContext | None = None
        self._prepared = False
        self.last_closed_time: int | None = None
        self._closed_count = 0
        self._active_preview_time: int | None = None

    def prepare(self) -> None:
        if self._prepared:
            return
        validate_script_security(self.script, self.policy)
        self._globals = self._build_namespace()
        with execution_timeout(self.policy.timeout_seconds):
            exec(self.script, self._globals)  # noqa: S102
        self._init_func = self._globals.get("init") if callable(self._globals.get("init")) else None
        self._on_bar = self._globals.get("on_bar") if callable(self._globals.get("on_bar")) else None
        self._on_preview = self._globals.get("on_preview") if callable(self._globals.get("on_preview")) else None
        if self._on_bar is None:
            raise PyneSecurityError("Incremental Pyne scripts must define on_bar(ctx, bar)")
        self._prepared = True

    def seed(
        self,
        ohlcv: list[dict[str, Any]],
        *,
        start_s: int | None = None,
        end_s: int | None = None,
    ) -> IncrementalPyneResult:
        self.prepare()
        self._ctx = IncrementalContext(
            params=self.params,
            meta=self._meta,
            limits=self._limits,
            syminfo=self.settings.syminfo,
            timeframe=self.settings.timeframe,
            session=self.settings.session,
        )
        self._call_optional(self._init_func, self._ctx)
        self._closed_count = 0
        self._active_preview_time = None
        last_bar_index = len(ohlcv) - 1
        for index, item in enumerate(ohlcv):
            bar = IncrementalBar.from_dict(item, is_confirmed=True)
            self._run_bar(
                self._ctx,
                bar,
                preview=False,
                bar_index=index,
                last_bar_index=last_bar_index,
                barstate=PyneIncrementalBarState(
                    isfirst=index == 0,
                    islast=index == last_bar_index,
                    ishistory=True,
                    isrealtime=False,
                    isnew=True,
                    isconfirmed=True,
                    islastconfirmedhistory=index == last_bar_index,
                ),
            )
            self.last_closed_time = bar.time
            self._closed_count = index + 1
        return self._ctx.to_result(start_s=start_s, end_s=end_s)

    def on_bar_closed(self, item: dict[str, Any]) -> IncrementalPyneResult:
        self.prepare()
        if self._ctx is None:
            self._ctx = IncrementalContext(
                params=self.params,
                meta=self._meta,
                limits=self._limits,
                syminfo=self.settings.syminfo,
                timeframe=self.settings.timeframe,
                session=self.settings.session,
            )
            self._call_optional(self._init_func, self._ctx)
        bar = IncrementalBar.from_dict(item, is_confirmed=True)
        bar_index = self._closed_count
        had_preview = self._active_preview_time == bar.time
        self._run_bar(
            self._ctx,
            bar,
            preview=False,
            bar_index=bar_index,
            last_bar_index=bar_index,
            barstate=PyneIncrementalBarState(
                isfirst=bar_index == 0,
                islast=True,
                ishistory=False,
                isrealtime=True,
                isnew=not had_preview,
                isconfirmed=True,
                islastconfirmedhistory=False,
            ),
        )
        self.last_closed_time = bar.time
        self._closed_count = bar_index + 1
        if had_preview:
            self._active_preview_time = None
        return self._ctx.to_result(start_s=bar.time, end_s=bar.time)

    def on_bar_updated(self, item: dict[str, Any]) -> IncrementalPyneResult:
        self.prepare()
        if self._ctx is None:
            self._ctx = IncrementalContext(
                params=self.params,
                meta=self._meta,
                limits=self._limits,
                syminfo=self.settings.syminfo,
                timeframe=self.settings.timeframe,
                session=self.settings.session,
            )
            self._call_optional(self._init_func, self._ctx)
        bar = IncrementalBar.from_dict(item, is_confirmed=False)
        preview_ctx = self._ctx.clone_for_preview()
        bar_index = self._closed_count
        is_new = self._active_preview_time != bar.time
        self._run_bar(
            preview_ctx,
            bar,
            preview=True,
            bar_index=bar_index,
            last_bar_index=bar_index,
            barstate=PyneIncrementalBarState(
                isfirst=bar_index == 0,
                islast=True,
                ishistory=False,
                isrealtime=True,
                isnew=is_new,
                isconfirmed=False,
                islastconfirmedhistory=False,
            ),
        )
        self._active_preview_time = bar.time
        return preview_ctx.to_result(start_s=bar.time, end_s=bar.time)

    def _run_bar(
        self,
        ctx: IncrementalContext,
        bar: IncrementalBar,
        *,
        preview: bool,
        bar_index: int,
        last_bar_index: int,
        barstate: PyneIncrementalBarState,
    ) -> None:
        ctx.begin_bar(bar, bar_index=bar_index, last_bar_index=last_bar_index, barstate=barstate)
        func = self._on_preview if preview and self._on_preview is not None else self._on_bar
        with execution_timeout(self.policy.timeout_seconds):
            self._call_required(func, ctx, bar)

    def _build_namespace(self) -> dict[str, Any]:
        def indicator(title: str = "", overlay: bool = True, **kwargs: Any) -> None:
            self._meta = {"title": title, "overlay": overlay, **kwargs}

        return {
            "indicator": indicator,
            "params": self.params,
            "syminfo": self.settings.syminfo,
            "timeframe": self.settings.timeframe,
            "session": self.settings.session,
            "true": True,
            "false": False,
            "color": color_singleton,
            "math": pyne_math,
            "pyne": pyne_cache_namespace,
            "cache": pyne_cache_namespace.cache,
            "cache_clear": pyne_cache_namespace.cache_clear,
            "cache_stats": pyne_cache_namespace.cache_stats,
            "__builtins__": build_builtins(self.policy),
        }

    def _call_optional(self, func: Callable[..., Any] | None, ctx: IncrementalContext) -> None:
        if func is None:
            return
        with execution_timeout(self.policy.timeout_seconds):
            self._call_by_arity(func, ctx)

    def _call_required(self, func: Callable[..., Any] | None, ctx: IncrementalContext, bar: IncrementalBar) -> None:
        if func is None:
            raise PyneSecurityError("Incremental Pyne scripts must define on_bar(ctx, bar)")
        self._call_by_arity(func, ctx, bar)

    def _call_by_arity(self, func: Callable[..., Any], ctx: IncrementalContext, bar: IncrementalBar | None = None) -> None:
        signature = inspect.signature(func)
        params = list(signature.parameters.values())
        has_varargs = any(item.kind == inspect.Parameter.VAR_POSITIONAL for item in params)
        if bar is None:
            if len(params) == 0 and not has_varargs:
                func()
            else:
                func(ctx)
            return
        if has_varargs or len(params) >= 2:
            func(ctx, bar)
        elif len(params) == 1:
            func(bar)
        else:
            func()

    def snapshot_result(
        self,
        *,
        start_s: int | None = None,
        end_s: int | None = None,
    ) -> IncrementalPyneResult:
        self.prepare()
        if self._ctx is None:
            self._ctx = IncrementalContext(
                params=self.params,
                meta=self._meta,
                limits=self._limits,
                syminfo=self.settings.syminfo,
                timeframe=self.settings.timeframe,
                session=self.settings.session,
            )
            self._call_optional(self._init_func, self._ctx)
        return self._ctx.to_result(start_s=start_s, end_s=end_s)


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
        event_key = (
            "preview" if preview else "closed",
            int(bar.get("time") or 0),
            float(bar.get("open", 0)),
            float(bar.get("high", 0)),
            float(bar.get("low", 0)),
            float(bar.get("close", 0)),
            float(bar.get("volume", 0)),
        )
        with shared.lock:
            if shared.last_event_key == event_key and shared.last_event_result is not None:
                return copy.deepcopy(shared.last_event_result)
            result = shared.session.on_bar_updated(bar) if preview else shared.session.on_bar_closed(bar)
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


def is_incremental_pyne_script(script: str) -> bool:
    tree = ast.parse(script)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {"on_bar", "on_preview"}:
            return True
        if isinstance(node, ast.Call) and _call_name(node.func) == "indicator":
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    if str(kw.value.value).lower() == "incremental":
                        return True
    return False


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value).strip()).strip("_").lower()
    return normalized or "plot"


def _filter_points(points: list[dict[str, Any]], start_s: int | None, end_s: int | None) -> list[dict[str, Any]]:
    if start_s is None and end_s is None:
        return list(points)
    filtered = []
    for point in points:
        try:
            ts = int(point.get("time"))
        except (TypeError, ValueError):
            continue
        if start_s is not None and ts < start_s:
            continue
        if end_s is not None and ts > end_s:
            continue
        filtered.append(point)
    return filtered


def _round8(value: float) -> float:
    return round(float(value), 8)


def _signed_trade_qty(trade: dict[str, Any]) -> float:
    qty = abs(float(trade.get("qty", 0.0)))
    return qty if trade.get("side") == IncrementalStrategyNamespace.long else -qty


def _realized_profit(*, side: str, qty: float, entry_price: float, exit_price: float) -> float:
    if side == IncrementalStrategyNamespace.long:
        return (float(exit_price) - float(entry_price)) * abs(float(qty))
    return (float(entry_price) - float(exit_price)) * abs(float(qty))


def _trade_open_profit(trade: dict[str, Any], close_price: float) -> float:
    return _realized_profit(
        side=str(trade.get("side", IncrementalStrategyNamespace.long)),
        qty=float(trade.get("qty", 0.0)),
        entry_price=float(trade.get("entry_price", 0.0)),
        exit_price=float(close_price),
    )


def _requested_exit_qty(*, target_qty: float, qty: float | None, qty_percent: float | None) -> float:
    target = max(float(target_qty), 0.0)
    if qty is not None:
        return max(float(qty), 0.0)
    if qty_percent is not None:
        return target * max(float(qty_percent), 0.0) / 100.0
    return target


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _pending_trigger(
    *,
    side: str,
    high: float,
    low: float,
    limit: float | None,
    stop: float | None,
    tick_verify: float = 0.0,
    same_bar_fill_priority: str = "stop_first",
    intrabar_path: str = "same_bar_priority",
) -> tuple[str, float] | None:
    if side == IncrementalStrategyNamespace.long:
        stop_hit = stop is not None and high >= stop
        limit_hit = limit is not None and low <= limit - tick_verify
        if stop_hit and limit_hit:
            return _same_bar_trigger(
                stop=stop,
                limit=limit,
                stop_path="high",
                limit_path="low",
                same_bar_fill_priority=same_bar_fill_priority,
                intrabar_path=intrabar_path,
            )
        if stop_hit:
            return "stop", float(stop)
        if limit_hit:
            return "limit", float(limit)
        return None
    stop_hit = stop is not None and low <= stop
    limit_hit = limit is not None and high >= limit + tick_verify
    if stop_hit and limit_hit:
        return _same_bar_trigger(
            stop=stop,
            limit=limit,
            stop_path="low",
            limit_path="high",
            same_bar_fill_priority=same_bar_fill_priority,
            intrabar_path=intrabar_path,
        )
    if stop_hit:
        return "stop", float(stop)
    if limit_hit:
        return "limit", float(limit)
    return None


def _exit_trigger(
    *,
    current_position: float,
    high: float,
    low: float,
    stop: float | None,
    limit: float | None,
    tick_verify: float = 0.0,
    same_bar_fill_priority: str = "stop_first",
    intrabar_path: str = "same_bar_priority",
) -> tuple[str, float] | None:
    if current_position > 0:
        stop_hit = stop is not None and low <= stop
        limit_hit = limit is not None and high >= limit + tick_verify
        if stop_hit and limit_hit:
            return _same_bar_trigger(
                stop=stop,
                limit=limit,
                stop_path="low",
                limit_path="high",
                same_bar_fill_priority=same_bar_fill_priority,
                intrabar_path=intrabar_path,
            )
        if stop_hit:
            return "stop", float(stop)
        if limit_hit:
            return "limit", float(limit)
        return None
    stop_hit = stop is not None and high >= stop
    limit_hit = limit is not None and low <= limit - tick_verify
    if stop_hit and limit_hit:
        return _same_bar_trigger(
            stop=stop,
            limit=limit,
            stop_path="high",
            limit_path="low",
            same_bar_fill_priority=same_bar_fill_priority,
            intrabar_path=intrabar_path,
        )
    if stop_hit:
        return "stop", float(stop)
    if limit_hit:
        return "limit", float(limit)
    return None


def _same_bar_trigger(
    *,
    stop: float | None,
    limit: float | None,
    stop_path: str,
    limit_path: str,
    same_bar_fill_priority: str,
    intrabar_path: str,
) -> tuple[str, float]:
    if intrabar_path == IncrementalStrategyNamespace.intrabar.open_high_low_close:
        if stop_path == "high" and limit_path == "low":
            return "stop", float(stop)
        if limit_path == "high" and stop_path == "low":
            return "limit", float(limit)
    if intrabar_path == IncrementalStrategyNamespace.intrabar.open_low_high_close:
        if stop_path == "low" and limit_path == "high":
            return "stop", float(stop)
        if limit_path == "low" and stop_path == "high":
            return "limit", float(limit)
    if same_bar_fill_priority == IncrementalStrategyNamespace.same_bar.limit_first:
        return "limit", float(limit)
    return "stop", float(stop)


def _normalize_same_bar_fill_priority(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "stop": IncrementalStrategyNamespace.same_bar.stop_first,
        "stop_first": IncrementalStrategyNamespace.same_bar.stop_first,
        "stop-first": IncrementalStrategyNamespace.same_bar.stop_first,
        "limit": IncrementalStrategyNamespace.same_bar.limit_first,
        "limit_first": IncrementalStrategyNamespace.same_bar.limit_first,
        "limit-first": IncrementalStrategyNamespace.same_bar.limit_first,
    }
    if normalized in aliases:
        return aliases[normalized]
    raise ValueError("same_bar_fill_priority must be stop_first or limit_first")


def _normalize_intrabar_path(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "same_bar_priority": IncrementalStrategyNamespace.intrabar.same_bar_priority,
        "same-bar-priority": IncrementalStrategyNamespace.intrabar.same_bar_priority,
        "open_high_low_close": IncrementalStrategyNamespace.intrabar.open_high_low_close,
        "open-high-low-close": IncrementalStrategyNamespace.intrabar.open_high_low_close,
        "ohlc": IncrementalStrategyNamespace.intrabar.open_high_low_close,
        "open_low_high_close": IncrementalStrategyNamespace.intrabar.open_low_high_close,
        "open-low-high-close": IncrementalStrategyNamespace.intrabar.open_low_high_close,
        "olhc": IncrementalStrategyNamespace.intrabar.open_low_high_close,
    }
    if normalized in aliases:
        return aliases[normalized]
    raise ValueError("intrabar_path must be same_bar_priority, open_high_low_close, or open_low_high_close")


def _normalize_oca_type(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "": IncrementalStrategyNamespace.oca.none,
        "none": IncrementalStrategyNamespace.oca.none,
        "strategy.oca.none": IncrementalStrategyNamespace.oca.none,
        "cancel": IncrementalStrategyNamespace.oca.cancel,
        "strategy.oca.cancel": IncrementalStrategyNamespace.oca.cancel,
        "reduce": IncrementalStrategyNamespace.oca.reduce,
        "strategy.oca.reduce": IncrementalStrategyNamespace.oca.reduce,
    }
    if normalized in aliases:
        return aliases[normalized]
    raise ValueError("oca_type must be strategy.oca.none, strategy.oca.cancel, or strategy.oca.reduce")


def _incremental_strategy_lifecycle_events(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for order in sorted(orders, key=lambda item: (item.get("_submit_time", item.get("time", 0)), item.get("_seq", 0))):
        order_type = str(order.get("type", ""))
        pending = bool(order.get("_pending_submission"))
        active = bool(order.get("_active", True))
        canceled = bool(order.get("_canceled")) or order_type in {"cancel", "cancel_all"}
        if canceled:
            status = "canceled"
            phase = "pending_canceled" if pending else "cancel"
        elif active:
            status = "filled"
            phase = (
                "pending_fill"
                if pending
                else "exit_fill"
                if order_type == "exit"
                else "close_fill"
                if order_type == "close"
                else "close_all_fill"
                if order_type == "close_all"
                else "market_fill"
            )
        elif pending:
            status = "pending"
            phase = "pending"
        else:
            status = "submitted"
            phase = order_type
        event: dict[str, Any] = {
            "id": order.get("id"),
            "from_entry": order.get("from_entry"),
            "type": order_type,
            "status": status,
            "phase": phase,
            "submitted_time": order.get("_submit_time", order.get("time")),
            "filled_time": order.get("time") if active and not canceled else None,
            "canceled_time": order.get("_canceled_time", order.get("time")) if canceled else None,
            "rejected_time": None,
            "side": order.get("side"),
            "qty": order.get("qty"),
            "price": order.get("price"),
            "position_after": order.get("position_after"),
        }
        if order.get("reason") is not None:
            event["reason"] = order.get("reason")
        if order.get("comment") is not None:
            event["comment"] = order.get("comment")
        if order.get("oca_name") is not None:
            event["oca_name"] = order.get("oca_name")
        if order.get("oca_type") is not None:
            event["oca_type"] = order.get("oca_type")
        if order.get("_limit") is not None:
            event["limit"] = order.get("_limit")
        if order.get("_stop") is not None:
            event["stop"] = order.get("_stop")
        if order.get("_requested_fill_qty") is not None and active:
            event["requested_qty"] = _round8(float(order.get("_requested_fill_qty", 0.0)))
        if order.get("_filled_qty") is not None and active:
            event["filled_qty"] = _round8(float(order.get("_filled_qty", 0.0)))
        if order.get("_target_qty") is not None:
            event["target_qty"] = _round8(float(order.get("_target_qty", 0.0)))
        if order.get("_qty_percent") is not None:
            event["qty_percent"] = _round8(float(order.get("_qty_percent", 0.0)))
        if order.get("_canceled_by") is not None:
            event["canceled_by"] = order.get("_canceled_by")
        if order.get("canceled") is not None:
            event["canceled"] = order.get("canceled")
        returnable = {
            key: value
            for key, value in event.items()
            if value is not None or key in {"price", "filled_time", "canceled_time", "rejected_time"}
        }
        events.append(returnable)
    return events


def _session_info_for_bar(bar: IncrementalBar, default: SessionInfo) -> SessionInfo:
    raw = dict(bar.raw or {})
    nested = raw.get("session")
    if isinstance(nested, dict):
        raw.update(nested)
    return normalize_session_info({
        "ismarket": _first_present(raw, ("session_ismarket", "ismarket", "is_market"), default.ismarket),
        "isfirstbar": _first_present(
            raw,
            ("session_isfirstbar", "isfirstbar", "is_firstbar", "session_is_first_bar"),
            default.isfirstbar or bar.is_first,
        ),
        "islastbar": _first_present(
            raw,
            ("session_islastbar", "islastbar", "is_lastbar", "session_is_last_bar"),
            default.islastbar or bar.is_last,
        ),
    })


def _first_present(raw: dict[str, Any], names: tuple[str, ...], default: bool) -> bool:
    for name in names:
        if name in raw:
            return bool(raw[name])
    return bool(default)


def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 0.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _style_to_int(style: Any) -> int:
    if isinstance(style, int):
        return style
    normalized = str(style or "solid").lower()
    if normalized in {"dashed", "dash"}:
        return 1
    if normalized in {"dotted", "dot"}:
        return 2
    return 0
