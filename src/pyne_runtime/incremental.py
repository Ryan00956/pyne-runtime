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
from types import SimpleNamespace
from typing import Any, Callable

from .barstate import PyneIncrementalBarState
from .cache import pyne as pyne_cache_namespace
from .color import color as color_singleton
from .math_ext import PyneMath
from .metadata import SessionInfo, SymbolInfo, TimeframeInfo, normalize_session_info
from .security import (
    PyneSecurityError,
    PyneSecurityPolicy,
    build_builtins,
    execution_timeout,
    validate_script_security,
)
from .settings import PyneSettings
from .plot import ObjectRef

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


class IncrementalStrategyDirection:
    all = "all"
    both = "all"
    long = "long"
    short = "short"
    none = "none"


class IncrementalStrategyCommission:
    percent = "percent"
    cash_per_order = "cash_per_order"
    cash_per_contract = "cash_per_contract"


class IncrementalStrategyRiskMode:
    percent_of_equity = "percent_of_equity"
    cash = "cash"


class IncrementalStrategyRiskNamespace:
    all = IncrementalStrategyDirection.all
    both = IncrementalStrategyDirection.both
    long = IncrementalStrategyDirection.long
    short = IncrementalStrategyDirection.short
    none = IncrementalStrategyDirection.none
    percent_of_equity = IncrementalStrategyRiskMode.percent_of_equity
    cash = IncrementalStrategyRiskMode.cash

    def __init__(self, strategy: "IncrementalStrategyNamespace") -> None:
        self._strategy = strategy

    def allow_entry_in(self, direction: str = IncrementalStrategyDirection.all) -> None:
        self._strategy._allow_entry_in = _normalize_allowed_entry_direction(direction)

    def max_drawdown(
        self,
        value: float,
        type: str = IncrementalStrategyRiskMode.percent_of_equity,
    ) -> None:
        self._strategy._max_drawdown_value = max(float(value), 0.0)
        self._strategy._max_drawdown_type = _normalize_risk_mode(type)

    def max_intraday_loss(
        self,
        value: float,
        type: str = IncrementalStrategyRiskMode.percent_of_equity,
    ) -> None:
        self._strategy._max_intraday_loss_value = max(float(value), 0.0)
        self._strategy._max_intraday_loss_type = _normalize_risk_mode(type)

    def max_position_size(self, contracts: float) -> None:
        self._strategy._max_position_size = max(float(contracts), 0.0)

    def max_intraday_filled_orders(self, count: int) -> None:
        self._strategy._max_intraday_filled_orders = max(int(count), 0)


class IncrementalStrategyTradesNamespace:
    """Scalar trade-ledger accessor namespace for incremental callbacks."""

    def __init__(self, strategy: "IncrementalStrategyNamespace", kind: str) -> None:
        self._strategy = strategy
        self._kind = kind

    @property
    def count(self) -> int:
        return len(self._trades())

    def __int__(self) -> int:
        return self.count

    def __float__(self) -> float:
        return float(self.count)

    def __bool__(self) -> bool:
        return self.count > 0

    def size(self, trade_num: int = -1) -> float:
        return self.qty(trade_num)

    def qty(self, trade_num: int = -1) -> float:
        return _trade_float(self._trade(trade_num), "qty")

    def profit(self, trade_num: int = -1) -> float:
        trade = self._trade(trade_num)
        if self._kind == "opentrades" and trade:
            return _round8(_trade_open_profit(trade, self._strategy._current_price()))
        return _trade_float(trade, "profit")

    def net_profit(self, trade_num: int = -1) -> float:
        trade = self._trade(trade_num)
        if self._kind == "opentrades" and trade:
            profit = _trade_open_profit(trade, self._strategy._current_price())
            return _round8(profit - float(trade.get("commission", 0.0)))
        return _trade_float(trade, "net_profit")

    def commission(self, trade_num: int = -1) -> float:
        return _trade_float(self._trade(trade_num), "commission")

    def entry_price(self, trade_num: int = -1) -> float:
        return _trade_float(self._trade(trade_num), "entry_price")

    def exit_price(self, trade_num: int = -1) -> float:
        return _trade_float(self._trade(trade_num), "exit_price")

    def entry_time(self, trade_num: int = -1) -> float:
        return _trade_float(self._trade(trade_num), "entry_time")

    def exit_time(self, trade_num: int = -1) -> float:
        return _trade_float(self._trade(trade_num), "exit_time")

    def entry_id(self, trade_num: int = -1) -> str:
        return str(self._trade(trade_num).get("entry_id", ""))

    def exit_id(self, trade_num: int = -1) -> str:
        return str(self._trade(trade_num).get("exit_id", ""))

    def side(self, trade_num: int = -1) -> str:
        return str(self._trade(trade_num).get("side", ""))

    def _trades(self) -> list[dict[str, Any]]:
        return self._strategy._closed_trades if self._kind == "closedtrades" else self._strategy._open_trades

    def _trade(self, trade_num: int) -> dict[str, Any]:
        trades = self._trades()
        if not trades:
            return {}
        index = int(trade_num)
        if index < 0:
            index = len(trades) + index
        if index < 0 or index >= len(trades):
            return {}
        return trades[index]


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
    commission = IncrementalStrategyCommission
    direction = IncrementalStrategyDirection
    percent_of_equity = IncrementalStrategyRiskMode.percent_of_equity
    cash = IncrementalStrategyRiskMode.cash
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
        self._pending_exit_orders: list[dict[str, Any]] = []
        self._open_trades: list[dict[str, Any]] = []
        self._closed_trades: list[dict[str, Any]] = []
        self._closedtrades_namespace = IncrementalStrategyTradesNamespace(self, "closedtrades")
        self._opentrades_namespace = IncrementalStrategyTradesNamespace(self, "opentrades")
        self._grossprofit = 0.0
        self._grossloss = 0.0
        self._commission = 0.0
        self._commission_type: str | None = None
        self._commission_value = 0.0
        self._slippage_ticks = 0
        self._event_seq = 0
        self._touched = False
        self._pyramiding = 0
        self._same_direction_entry_count = 0
        self._allow_entry_in = IncrementalStrategyDirection.all
        self._max_drawdown_value: float | None = None
        self._max_drawdown_type = IncrementalStrategyRiskMode.percent_of_equity
        self._max_intraday_loss_value: float | None = None
        self._max_intraday_loss_type = IncrementalStrategyRiskMode.percent_of_equity
        self._max_position_size: float | None = None
        self._max_intraday_filled_orders: int | None = None
        self._risk_locked = False
        self._drawdown_locked = False
        self._intraday_locked = False
        self._filled_orders_locked = False
        self._peak_equity = self._initial_capital
        self._intraday_peak_equity = self._initial_capital
        self._intraday_filled_orders = 0
        self.risk = IncrementalStrategyRiskNamespace(self)
        self._mintick = max(float(getattr(context.syminfo, "mintick", 0.0)), 0.0)
        self._backtest_fill_limits_assumption = 0
        self._same_bar_fill_priority = self.same_bar.stop_first
        self._intrabar_path = self.intrabar.same_bar_priority
        self._margin_long = 100.0
        self._margin_short = 100.0

    def configure(self, **kwargs: Any) -> None:
        if "pyramiding" in kwargs:
            self._pyramiding = max(int(kwargs["pyramiding"]), 0)
        if "initial_capital" in kwargs:
            self._initial_capital = float(kwargs["initial_capital"])
            self._peak_equity = max(self._peak_equity, self._initial_capital)
            self._intraday_peak_equity = max(self._intraday_peak_equity, self._initial_capital)
        if "currency" in kwargs:
            self._currency = str(kwargs["currency"] or "")
        if "slippage" in kwargs:
            self._slippage_ticks = max(int(kwargs["slippage"]), 0)
        if "commission_type" in kwargs:
            self._commission_type = _normalize_commission_type(str(kwargs["commission_type"]))
        if "commission_value" in kwargs:
            self._commission_value = max(float(kwargs["commission_value"]), 0.0)
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

    @property
    def closedtrades(self) -> IncrementalStrategyTradesNamespace:
        return self._closedtrades_namespace

    @property
    def opentrades(self) -> IncrementalStrategyTradesNamespace:
        return self._opentrades_namespace

    def begin_bar(self) -> None:
        if getattr(self._context.session, "isfirstbar", False):
            self._intraday_locked = False
            self._intraday_filled_orders = 0
            self._filled_orders_locked = _intraday_filled_orders_hit(
                filled_orders=self._intraday_filled_orders,
                threshold=self._max_intraday_filled_orders,
            )
            self._intraday_peak_equity = self.equity
            self._sync_risk_locked()
        if self._pending_orders:
            still_pending = []
            for order in self._pending_orders:
                if not self._try_fill_pending_order(order):
                    still_pending.append(order)
            self._pending_orders = still_pending
        still_pending_exits = []
        for order in self._pending_exit_orders:
            if not self._try_fill_pending_exit_order(order):
                still_pending_exits.append(order)
        self._pending_exit_orders = still_pending_exits

    def end_bar(self) -> None:
        equity = self.equity
        self._peak_equity = max(self._peak_equity, equity)
        self._intraday_peak_equity = max(self._intraday_peak_equity, equity)
        if self._max_drawdown_value is not None and _max_drawdown_hit(
            equity=equity,
            peak_equity=self._peak_equity,
            threshold=self._max_drawdown_value,
            risk_type=self._max_drawdown_type,
        ):
            self._drawdown_locked = True
        if self._max_intraday_loss_value is not None and _max_drawdown_hit(
            equity=equity,
            peak_equity=self._intraday_peak_equity,
            threshold=self._max_intraday_loss_value,
            risk_type=self._max_intraday_loss_type,
        ):
            self._intraday_locked = True
        self._sync_risk_locked()

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
        if self._risk_locked:
            self._reject_order(order, reason="risk_locked")
            return
        if limit is not None or stop is not None:
            order["_pending_submission"] = True
            order["_active"] = False
            if not self._try_fill_pending_order(order):
                self._pending_orders.append(order)
            return
        if order_type == "entry":
            rejection_reason = _entry_rejection_reason(
                side=side,
                previous_size=self.position_size,
                same_direction_entry_count=self._same_direction_entry_count,
                pyramiding=self._pyramiding,
                allow_entry_in=self._allow_entry_in,
            )
            if rejection_reason is not None:
                self._reject_order(order, reason=rejection_reason)
                return
            requested_qty = qty_abs
            qty_abs = _entry_qty_for_max_position_size(
                side=side,
                previous_size=self.position_size,
                requested_qty=requested_qty,
                max_position_size=self._max_position_size,
            )
            order["_requested_fill_qty"] = _round8(requested_qty)
            if qty_abs <= 0:
                self._reject_order(order, reason="max_position_size")
                return
            order["qty"] = _round8(qty_abs)
            order["_requested_fill_qty"] = _round8(requested_qty)
        next_size = self._position_after_fill(
            order_type=order_type,
            side=side,
            qty=qty_abs,
            previous_size=self.position_size,
        )
        if not self._margin_allows_position(
            previous_size=self.position_size,
            next_size=next_size,
            price=self._fill_price(base_price, "buy" if side == self.long else "sell"),
            equity=self.equity,
        ):
            self._reject_order(order, reason="margin")
            return
        self._fill_entry_order(order, fill_price=base_price, reason=None)

    def _fill_entry_order(self, order: dict[str, Any], *, fill_price: float, reason: str | None) -> None:
        side = self._normalize_direction(str(order.get("side", self.long)))
        fill_side = "buy" if side == self.long else "sell"
        fill_price = self._fill_price(fill_price, fill_side)
        previous_size = self.position_size
        qty_abs = abs(float(order.get("qty", 0.0)))
        signed_qty = qty_abs if side == self.long else -qty_abs
        if order.get("type") == "entry":
            next_size = signed_qty if previous_size == 0 or (previous_size > 0) != (signed_qty > 0) else previous_size + signed_qty
            transaction_qty = abs(next_size - previous_size)
            close_qty = abs(previous_size) if previous_size and (previous_size > 0) != (signed_qty > 0) else 0.0
            open_qty = qty_abs
        else:
            next_size = previous_size + signed_qty
            transaction_qty = qty_abs
            close_qty = (
                min(abs(previous_size), qty_abs)
                if previous_size and (previous_size > 0) != (signed_qty > 0)
                else 0.0
            )
            open_qty = max(qty_abs - close_qty, 0.0)
        commission_qty = transaction_qty if order.get("type") == "entry" else qty_abs
        commission = self._apply_commission(order, qty=commission_qty, price=fill_price)
        used_commission = 0.0
        if close_qty > 0:
            _, used_commission = self._close_lots(
                id="",
                exit_id=str(order.get("id", "")),
                target_qty=close_qty,
                fill_price=fill_price,
                order_commission=commission,
                order_fill_qty=transaction_qty,
            )
        remaining_commission = max(commission - used_commission, 0.0)
        if open_qty > 0 and next_size != 0:
            open_side = self.long if next_size > 0 else self.short
            open_trade = {
                "entry_id": str(order.get("id", "")),
                "entry_time": self._current_time(),
                "side": open_side,
                "qty": _round8(open_qty),
                "entry_price": _round8(fill_price),
            }
            if remaining_commission > 0:
                open_trade["commission"] = _round8(remaining_commission)
            self._open_trades.append(open_trade)
        order["time"] = self._current_time()
        order["price"] = _round8(fill_price)
        order["position_after"] = self.position_size
        order["_active"] = True
        order["_filled_qty"] = qty_abs
        if order.get("type") == "entry" and abs(transaction_qty - qty_abs) > 1e-9:
            order["_transaction_qty"] = _round8(transaction_qty)
        if order.get("_oca_name"):
            order["oca_name"] = order.get("_oca_name")
            order["oca_type"] = order.get("_oca_type") or self.oca.none
        if reason is not None:
            order["reason"] = reason
        self._apply_oca_after_fill(order)
        next_size = self.position_size
        if order.get("type") == "entry":
            if previous_size == 0 or (previous_size > 0) != (next_size > 0):
                self._same_direction_entry_count = 1
            else:
                self._same_direction_entry_count += 1
        elif order.get("type") == "order":
            if next_size == 0:
                self._same_direction_entry_count = 0
            elif previous_size == 0 or (previous_size > 0) != (next_size > 0):
                self._same_direction_entry_count = 1
        if order.get("type") in {"entry", "order"}:
            self._intraday_filled_orders += 1
            if _intraday_filled_orders_hit(
                filled_orders=self._intraday_filled_orders,
                threshold=self._max_intraday_filled_orders,
            ):
                self._filled_orders_locked = True
                self._sync_risk_locked()

    def _try_fill_pending_order(self, order: dict[str, Any]) -> bool:
        if order.get("_active"):
            return True
        if order.get("_canceled"):
            return True
        if self._risk_locked and order.get("type") in {"entry", "order"}:
            return False
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
        order["reason"] = reason
        if order.get("type") == "entry":
            side = self._normalize_direction(str(order.get("side", self.long)))
            rejection_reason = _entry_rejection_reason(
                side=side,
                previous_size=self.position_size,
                same_direction_entry_count=self._same_direction_entry_count,
                pyramiding=self._pyramiding,
                allow_entry_in=self._allow_entry_in,
            )
            if rejection_reason is not None:
                self._reject_order(order, reason=rejection_reason)
                return True
            requested_qty = float(order.get("_requested_fill_qty", order.get("qty", 0.0)))
            qty_abs = _entry_qty_for_max_position_size(
                side=side,
                previous_size=self.position_size,
                requested_qty=requested_qty,
                max_position_size=self._max_position_size,
            )
            order["_requested_fill_qty"] = _round8(requested_qty)
            if qty_abs <= 0:
                self._reject_order(order, reason="max_position_size")
                return True
            order["qty"] = _round8(qty_abs)
        else:
            side = self._normalize_direction(str(order.get("side", self.long)))
            qty_abs = abs(float(order.get("qty", 0.0)))
        next_size = self._position_after_fill(
            order_type=str(order.get("type", "")),
            side=side,
            qty=qty_abs,
            previous_size=self.position_size,
        )
        fill_side = "buy" if side == self.long else "sell"
        margin_fill_price = self._fill_price(fill_price, fill_side)
        if not self._margin_allows_position(
            previous_size=self.position_size,
            next_size=next_size,
            price=margin_fill_price,
            equity=self.equity,
        ):
            return False
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
        base_price = self._price_or_current(price)
        target_qty = self._target_open_qty(str(id))
        requested_qty = _requested_exit_qty(target_qty=target_qty, qty=qty, qty_percent=qty_percent)
        fill_qty = min(target_qty, abs(self.position_size), requested_qty)
        if fill_qty <= 0:
            return
        fill_side = "sell" if self.position_size > 0 else "buy"
        fill_price = self._fill_price(base_price, fill_side)
        order_commission = self._commission_amount(qty=fill_qty, price=fill_price)
        if order_commission > 0:
            self._commission += order_commission
        closed_qty, _ = self._close_lots(
            id=str(id),
            exit_id=str(id),
            target_qty=fill_qty,
            fill_price=fill_price,
            order_commission=order_commission,
            order_fill_qty=fill_qty,
        )
        if abs(closed_qty) <= 0:
            return
        self._touched = True
        order = {
            "time": self._current_time(),
            "id": str(id),
            "type": "close",
            "side": "flat",
            "qty": _round8(abs(closed_qty)),
            "price": _round8(fill_price),
            "position_after": self.position_size,
            "comment": comment,
            "_seq": self._next_seq(),
            "_target_qty": _round8(target_qty),
            "_requested_fill_qty": _round8(requested_qty),
            "_filled_qty": _round8(abs(closed_qty)),
        }
        if order_commission > 0:
            order["commission"] = _round8(order_commission)
        self._orders.append(order)

    def close_all(self, *, price: float | None = None, when: bool = True, comment: str = "") -> None:
        if not when or not self._open_trades:
            return
        self.close("", qty=abs(self.position_size), price=price, when=True, comment=comment)
        if self._orders:
            self._orders[-1]["type"] = "close_all"
            self._orders[-1]["id"] = "close_all"
            self._orders[-1]["_target_qty"] = self._orders[-1]["qty"]
            self._orders[-1]["_requested_fill_qty"] = self._orders[-1]["qty"]
            self._orders[-1]["_filled_qty"] = self._orders[-1]["qty"]
            for trade in self._closed_trades:
                if trade.get("exit_id") == "" and trade.get("exit_time") == self._current_time():
                    trade["exit_id"] = "close_all"

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
        if not when or (stop is None and limit is None):
            return
        self._touched = True
        pending = self._upsert_pending_exit_order({
            "id": str(id),
            "from_entry": str(from_entry),
            "type": "exit",
            "side": "flat",
            "qty": 0.0,
            "price": self._current_price(),
            "position_after": 0.0,
            "comment": comment,
            "_limit": _optional_float(limit),
            "_stop": _optional_float(stop),
            "_requested_qty": _optional_float(qty),
            "_qty_percent": _optional_float(qty_percent),
            "_submit_time": self._current_time(),
        })
        if self._try_fill_pending_exit_order(pending):
            self._pending_exit_orders = [
                order
                for order in self._pending_exit_orders
                if not (
                    order.get("id") == pending.get("id")
                    and order.get("from_entry") == pending.get("from_entry")
                )
            ]

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
                "locked": self._risk_locked,
                "max_drawdown": (
                    _round8(self._max_drawdown_value)
                    if self._max_drawdown_value is not None
                    else None
                ),
                "max_drawdown_type": self._max_drawdown_type,
                "max_intraday_loss": (
                    _round8(self._max_intraday_loss_value)
                    if self._max_intraday_loss_value is not None
                    else None
                ),
                "max_intraday_loss_type": self._max_intraday_loss_type,
                "max_position_size": (
                    _round8(self._max_position_size)
                    if self._max_position_size is not None
                    else None
                ),
                "max_intraday_filled_orders": self._max_intraday_filled_orders,
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

    def _upsert_pending_exit_order(self, next_order: dict[str, Any]) -> dict[str, Any]:
        for order in self._pending_exit_orders:
            if (
                order.get("id") == next_order.get("id")
                and order.get("from_entry") == next_order.get("from_entry")
            ):
                order.update(next_order)
                return order
        next_order["_seq"] = self._next_seq()
        self._pending_exit_orders.append(next_order)
        return next_order

    def _try_fill_pending_exit_order(self, order: dict[str, Any]) -> bool:
        if not self._open_trades:
            return False
        current_position = self.position_size
        if current_position == 0:
            return False
        bar = self._context.current_bar
        if bar is None:
            return False
        trigger = _exit_trigger(
            current_position=current_position,
            high=float(bar.high),
            low=float(bar.low),
            stop=order.get("_stop"),
            limit=order.get("_limit"),
            tick_verify=self._limit_fill_verification_amount(),
            same_bar_fill_priority=self._same_bar_fill_priority,
            intrabar_path=self._intrabar_path,
        )
        if trigger is None:
            return False
        reason, event_price = trigger
        target_qty = self._target_open_qty(str(order.get("from_entry", "")))
        requested_qty = _requested_exit_qty(
            target_qty=target_qty,
            qty=order.get("_requested_qty"),
            qty_percent=order.get("_qty_percent"),
        )
        fill_qty = min(target_qty, abs(current_position), requested_qty)
        if fill_qty <= 0:
            return False
        fill_side = "sell" if current_position > 0 else "buy"
        fill_price = self._fill_price(event_price, fill_side)
        order_commission = self._commission_amount(qty=fill_qty, price=fill_price)
        if order_commission > 0:
            self._commission += order_commission
        closed_qty, _ = self._close_lots(
            id=str(order.get("from_entry", "")),
            exit_id=str(order.get("id", "")),
            target_qty=fill_qty,
            fill_price=fill_price,
            order_commission=order_commission,
            order_fill_qty=fill_qty,
        )
        if abs(closed_qty) <= 0:
            return False
        public_order = {
            "time": self._current_time(),
            "id": str(order.get("id", "")),
            "from_entry": str(order.get("from_entry", "")),
            "type": "exit",
            "side": "flat",
            "qty": _round8(abs(closed_qty)),
            "price": _round8(fill_price),
            "position_after": self.position_size,
            "reason": reason,
            "comment": str(order.get("comment", "")),
            "_base_price": float(fill_price),
            "_target_qty": _round8(target_qty),
            "_requested_fill_qty": _round8(requested_qty),
            "_filled_qty": _round8(abs(closed_qty)),
            "_requested_qty": order.get("_requested_qty"),
            "_qty_percent": order.get("_qty_percent"),
            "_seq": order.get("_seq", self._next_seq()),
            "_submit_time": self._current_time(),
        }
        if order_commission > 0:
            public_order["commission"] = _round8(order_commission)
        self._orders.append(public_order)
        return True

    def _reject_order(self, order: dict[str, Any], *, reason: str) -> None:
        order["_active"] = False
        order["position_after"] = 0.0
        order["_rejected_reason"] = reason
        order["_rejected_time"] = self._current_time()
        order.setdefault("_requested_fill_qty", float(order.get("_requested_fill_qty", order.get("qty", 0.0))))
        order["_filled_qty"] = 0.0

    def _sync_risk_locked(self) -> None:
        self._risk_locked = self._drawdown_locked or self._intraday_locked or self._filled_orders_locked

    def _position_after_fill(
        self,
        *,
        order_type: str,
        side: str,
        qty: float,
        previous_size: float,
    ) -> float:
        signed_qty = abs(float(qty)) if side == self.long else -abs(float(qty))
        if order_type == "entry" and (previous_size == 0 or (previous_size > 0) != (signed_qty > 0)):
            return _round8(signed_qty)
        return _round8(previous_size + signed_qty)

    def _margin_allows_position(
        self,
        *,
        previous_size: float,
        next_size: float,
        price: float,
        equity: float,
    ) -> bool:
        if next_size == 0:
            return True
        if _is_exposure_reduction(previous_size, next_size):
            return True
        margin_percent = self._margin_long if next_size > 0 else self._margin_short
        required = _margin_required(
            position_size=next_size,
            price=price,
            margin_percent=margin_percent,
            pointvalue=float(getattr(self._context.syminfo, "pointvalue", 1.0)),
        )
        return required <= max(float(equity), 0.0)

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

    def _close_lots(
        self,
        *,
        id: str,
        exit_id: str,
        target_qty: float,
        fill_price: float,
        order_commission: float = 0.0,
        order_fill_qty: float | None = None,
    ) -> tuple[float, float]:
        remaining = abs(float(target_qty))
        closed_signed_qty = 0.0
        used_order_commission = 0.0
        fill_qty_total = max(float(order_fill_qty if order_fill_qty is not None else target_qty), 1e-12)
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
            entry_commission = float(trade.get("commission", 0.0))
            entry_commission_share = entry_commission * closing_qty / max(trade_qty, 1e-12)
            exit_commission_share = float(order_commission) * closing_qty / fill_qty_total
            used_order_commission += exit_commission_share
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
                "commission": _round8(entry_commission_share + exit_commission_share),
                "net_profit": _round8(profit - entry_commission_share - exit_commission_share),
            })
            closed_signed_qty += closing_qty if side == self.long else -closing_qty
            leftover_qty = trade_qty - closing_qty
            if leftover_qty > 1e-9:
                kept_trade = {**trade, "qty": _round8(leftover_qty)}
                remaining_entry_commission = entry_commission - entry_commission_share
                if remaining_entry_commission > 0:
                    kept_trade["commission"] = _round8(remaining_entry_commission)
                else:
                    kept_trade.pop("commission", None)
                kept.append(kept_trade)
        self._open_trades = kept
        if self.position_size == 0:
            self._same_direction_entry_count = 0
        return _round8(closed_signed_qty), _round8(used_order_commission)

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

    def _fill_price(self, price: float, side: str) -> float:
        slippage = self._slippage_ticks * self._mintick
        if side == "buy":
            return float(price) + slippage
        return float(price) - slippage

    def _commission_amount(self, *, qty: float, price: float) -> float:
        return _commission_amount(
            commission_type=self._commission_type,
            commission_value=self._commission_value,
            qty=qty,
            price=price,
        )

    def _apply_commission(self, order: dict[str, Any], *, qty: float, price: float) -> float:
        commission = self._commission_amount(qty=qty, price=price)
        if commission > 0:
            order["commission"] = _round8(commission)
            self._commission += commission
        return commission

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
        max_drawing_objects: int = 500,
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
        self._object_lines: dict[str, dict[str, Any]] = {}
        self._object_labels: dict[str, dict[str, Any]] = {}
        self._object_boxes: dict[str, dict[str, Any]] = {}
        self._object_tables: dict[str, dict[str, Any]] = {}
        self._object_events: list[dict[str, Any]] = []
        self._object_counter = 0
        self._max_drawing_objects = max(int(max_drawing_objects), 1)
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

    def line_new(
        self,
        x1: Any,
        y1: Any,
        x2: Any,
        y2: Any,
        color: str = "#2196f3",
        width: int = 1,
        style: str = "solid",
        extend: str = "none",
        xloc: str = "bar_index",
        pane: str | None = None,
    ) -> ObjectRef:
        object_id = self._next_object_id("line")
        entry = {
            "id": object_id,
            "x1": _drawing_scalar(x1),
            "y1": _drawing_scalar(y1),
            "x2": _drawing_scalar(x2),
            "y2": _drawing_scalar(y2),
            "color": color,
            "width": int(width),
            "style": style,
            "extend": extend,
            "xloc": xloc,
            "pane": pane or "main",
        }
        self._object_lines[object_id] = entry
        self._record_object_event("create", "line", entry)
        return ObjectRef(id=object_id, kind="line")

    def line_set_xy1(self, ref: ObjectRef, x: Any, y: Any) -> None:
        self._update_object(ref, "line", {"x1": _drawing_scalar(x), "y1": _drawing_scalar(y)})

    def line_set_xy2(self, ref: ObjectRef, x: Any, y: Any) -> None:
        self._update_object(ref, "line", {"x2": _drawing_scalar(x), "y2": _drawing_scalar(y)})

    def line_set_x1(self, ref: ObjectRef, x: Any) -> None:
        self._update_object(ref, "line", {"x1": _drawing_scalar(x)})

    def line_set_y1(self, ref: ObjectRef, y: Any) -> None:
        self._update_object(ref, "line", {"y1": _drawing_scalar(y)})

    def line_set_x2(self, ref: ObjectRef, x: Any) -> None:
        self._update_object(ref, "line", {"x2": _drawing_scalar(x)})

    def line_set_y2(self, ref: ObjectRef, y: Any) -> None:
        self._update_object(ref, "line", {"y2": _drawing_scalar(y)})

    def line_set_color(self, ref: ObjectRef, color: str) -> None:
        self._update_object(ref, "line", {"color": color})

    def line_set_width(self, ref: ObjectRef, width: int) -> None:
        self._update_object(ref, "line", {"width": int(width)})

    def line_set_style(self, ref: ObjectRef, style: str) -> None:
        self._update_object(ref, "line", {"style": style})

    def line_set_extend(self, ref: ObjectRef, extend: str) -> None:
        self._update_object(ref, "line", {"extend": extend})

    def line_delete(self, ref: ObjectRef) -> None:
        self._delete_object(ref, "line")

    def label_new(
        self,
        x: Any,
        y: Any,
        text: str = "",
        color: str = "#ffffff",
        textcolor: str = "#000000",
        style: str = "label_down",
        size: str = "normal",
        xloc: str = "bar_index",
        yloc: str = "price",
        pane: str | None = None,
    ) -> ObjectRef:
        object_id = self._next_object_id("label")
        entry = {
            "id": object_id,
            "x": _drawing_scalar(x),
            "y": _drawing_scalar(y),
            "text": str(text),
            "color": color,
            "textcolor": textcolor,
            "style": style,
            "size": size,
            "xloc": xloc,
            "yloc": yloc,
            "pane": pane or "main",
        }
        self._object_labels[object_id] = entry
        self._record_object_event("create", "label", entry)
        return ObjectRef(id=object_id, kind="label")

    def label_set_xy(self, ref: ObjectRef, x: Any, y: Any) -> None:
        self._update_object(ref, "label", {"x": _drawing_scalar(x), "y": _drawing_scalar(y)})

    def label_set_x(self, ref: ObjectRef, x: Any) -> None:
        self._update_object(ref, "label", {"x": _drawing_scalar(x)})

    def label_set_y(self, ref: ObjectRef, y: Any) -> None:
        self._update_object(ref, "label", {"y": _drawing_scalar(y)})

    def label_set_text(self, ref: ObjectRef, text: str) -> None:
        self._update_object(ref, "label", {"text": str(text)})

    def label_set_color(self, ref: ObjectRef, color: str) -> None:
        self._update_object(ref, "label", {"color": color})

    def label_set_textcolor(self, ref: ObjectRef, textcolor: str) -> None:
        self._update_object(ref, "label", {"textcolor": textcolor})

    def label_set_style(self, ref: ObjectRef, style: str) -> None:
        self._update_object(ref, "label", {"style": style})

    def label_set_size(self, ref: ObjectRef, size: str) -> None:
        self._update_object(ref, "label", {"size": size})

    def label_set_xloc(self, ref: ObjectRef, xloc: str) -> None:
        self._update_object(ref, "label", {"xloc": xloc})

    def label_set_yloc(self, ref: ObjectRef, yloc: str) -> None:
        self._update_object(ref, "label", {"yloc": yloc})

    def label_delete(self, ref: ObjectRef) -> None:
        self._delete_object(ref, "label")

    def box_new(
        self,
        left: Any,
        top: Any,
        right: Any,
        bottom: Any,
        bgcolor: str = "rgba(0,0,0,0)",
        border_color: str = "#787b86",
        border_width: int = 1,
        border_style: str = "solid",
        xloc: str = "bar_index",
        pane: str | None = None,
    ) -> ObjectRef:
        object_id = self._next_object_id("box")
        entry = {
            "id": object_id,
            "left": _drawing_scalar(left),
            "top": _drawing_scalar(top),
            "right": _drawing_scalar(right),
            "bottom": _drawing_scalar(bottom),
            "bgcolor": bgcolor,
            "border_color": border_color,
            "border_width": int(border_width),
            "border_style": border_style,
            "xloc": xloc,
            "pane": pane or "main",
        }
        self._object_boxes[object_id] = entry
        self._record_object_event("create", "box", entry)
        return ObjectRef(id=object_id, kind="box")

    def box_set_left(self, ref: ObjectRef, left: Any) -> None:
        self._update_object(ref, "box", {"left": _drawing_scalar(left)})

    def box_set_top(self, ref: ObjectRef, top: Any) -> None:
        self._update_object(ref, "box", {"top": _drawing_scalar(top)})

    def box_set_right(self, ref: ObjectRef, right: Any) -> None:
        self._update_object(ref, "box", {"right": _drawing_scalar(right)})

    def box_set_bottom(self, ref: ObjectRef, bottom: Any) -> None:
        self._update_object(ref, "box", {"bottom": _drawing_scalar(bottom)})

    def box_set_lefttop(self, ref: ObjectRef, left: Any, top: Any) -> None:
        self._update_object(ref, "box", {"left": _drawing_scalar(left), "top": _drawing_scalar(top)})

    def box_set_rightbottom(self, ref: ObjectRef, right: Any, bottom: Any) -> None:
        self._update_object(
            ref,
            "box",
            {"right": _drawing_scalar(right), "bottom": _drawing_scalar(bottom)},
        )

    def box_set_bgcolor(self, ref: ObjectRef, bgcolor: str) -> None:
        self._update_object(ref, "box", {"bgcolor": bgcolor})

    def box_set_border_color(self, ref: ObjectRef, border_color: str) -> None:
        self._update_object(ref, "box", {"border_color": border_color})

    def box_set_border_width(self, ref: ObjectRef, border_width: int) -> None:
        self._update_object(ref, "box", {"border_width": int(border_width)})

    def box_delete(self, ref: ObjectRef) -> None:
        self._delete_object(ref, "box")

    def table_new(
        self,
        position: str = "top_right",
        columns: int = 1,
        rows: int = 1,
        bgcolor: str | None = None,
        frame_color: str = "#787b86",
        frame_width: int = 1,
        border_color: str = "#787b86",
        border_width: int = 1,
        pane: str | None = None,
    ) -> ObjectRef:
        object_id = self._next_object_id("table")
        entry = {
            "id": object_id,
            "position": position,
            "columns": int(columns),
            "rows": int(rows),
            "bgcolor": bgcolor,
            "frame_color": frame_color,
            "frame_width": int(frame_width),
            "border_color": border_color,
            "border_width": int(border_width),
            "pane": pane or "main",
            "cells": [],
        }
        self._object_tables[object_id] = entry
        self._record_object_event("create", "table", entry)
        return ObjectRef(id=object_id, kind="table")

    def table_cell(
        self,
        ref: ObjectRef,
        column: int,
        row: int,
        text: Any = "",
        text_color: str = "#000000",
        bgcolor: str | None = None,
        width: int | None = None,
        height: int | None = None,
        text_halign: str = "center",
        text_valign: str = "middle",
    ) -> None:
        entry = self._object_entry(ref, "table")
        if entry is None:
            return
        cell = {
            "column": int(column),
            "row": int(row),
            "text": str(_drawing_scalar(text)),
            "text_color": text_color,
            "bgcolor": bgcolor,
            "width": width,
            "height": height,
            "text_halign": text_halign,
            "text_valign": text_valign,
        }
        _upsert_table_cell(entry, cell)
        self._record_object_event("update", "table", entry)

    def table_clear(self, ref: ObjectRef) -> None:
        self._update_object(ref, "table", {"cells": []})

    def table_set_position(self, ref: ObjectRef, position: str) -> None:
        self._update_object(ref, "table", {"position": position})

    def table_set_bgcolor(self, ref: ObjectRef, bgcolor: str) -> None:
        self._update_object(ref, "table", {"bgcolor": bgcolor})

    def table_set_frame_color(self, ref: ObjectRef, frame_color: str) -> None:
        self._update_object(ref, "table", {"frame_color": frame_color})

    def table_set_border_color(self, ref: ObjectRef, border_color: str) -> None:
        self._update_object(ref, "table", {"border_color": border_color})

    def table_delete(self, ref: ObjectRef) -> None:
        self._delete_object(ref, "table")

    def _next_object_id(self, kind: str) -> str:
        self._ensure_object_capacity()
        self._object_counter += 1
        return f"{kind}_{self._object_counter}"

    def _ensure_object_capacity(self) -> None:
        total = (
            len(self._object_lines)
            + len(self._object_labels)
            + len(self._object_boxes)
            + len(self._object_tables)
        )
        if total >= self._max_drawing_objects:
            raise RuntimeError(f"Drawing object limit exceeded (max {self._max_drawing_objects})")

    def _object_entry(self, ref: ObjectRef, kind: str) -> dict[str, Any] | None:
        if not isinstance(ref, ObjectRef) or ref.kind != kind:
            return None
        buckets = {
            "line": self._object_lines,
            "label": self._object_labels,
            "box": self._object_boxes,
            "table": self._object_tables,
        }
        return buckets[kind].get(ref.id)

    def _update_object(self, ref: ObjectRef, kind: str, updates: dict[str, Any]) -> None:
        entry = self._object_entry(ref, kind)
        if entry is None:
            return
        entry.update(updates)
        self._record_object_event("update", kind, entry)

    def _delete_object(self, ref: ObjectRef, kind: str) -> None:
        entry = self._object_entry(ref, kind)
        if entry is None:
            return
        self._record_object_event("delete", kind, entry)
        {
            "line": self._object_lines,
            "label": self._object_labels,
            "box": self._object_boxes,
            "table": self._object_tables,
        }[kind].pop(ref.id, None)

    def _record_object_event(self, action: str, kind: str, entry: dict[str, Any]) -> None:
        event: dict[str, Any] = {
            "action": action,
            "kind": kind,
            "id": entry.get("id"),
            "object": copy.deepcopy(entry),
        }
        if self.current_bar is not None:
            event["time"] = self.current_bar.time
            event["bar_index"] = self.bar_index
            event["confirmed"] = self.barstate.isconfirmed
            event["realtime"] = self.barstate.isrealtime
        self._object_events.append(event)

    def _objects_snapshot(self) -> dict[str, Any]:
        objects: dict[str, Any] = {}
        if self._object_lines:
            objects["lines"] = list(copy.deepcopy(self._object_lines).values())
        if self._object_labels:
            objects["labels"] = list(copy.deepcopy(self._object_labels).values())
        if self._object_boxes:
            objects["boxes"] = list(copy.deepcopy(self._object_boxes).values())
        if self._object_tables:
            objects["tables"] = list(copy.deepcopy(self._object_tables).values())
        return objects

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
        objects = self._objects_snapshot()
        if objects:
            output["objects"] = objects
        object_events = _filter_object_events(self._object_events, start_s, end_s)
        if object_events:
            output["object_events"] = object_events

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
        self._active_ctx: IncrementalContext | None = None
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
            max_drawing_objects=self.settings.max_drawing_objects,
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
                max_drawing_objects=self.settings.max_drawing_objects,
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
                max_drawing_objects=self.settings.max_drawing_objects,
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
        previous_ctx = self._active_ctx
        self._active_ctx = ctx
        try:
            with execution_timeout(self.policy.timeout_seconds):
                self._call_required(func, ctx, bar)
        finally:
            self._active_ctx = previous_ctx
        ctx.strategy.end_bar()

    def _build_namespace(self) -> dict[str, Any]:
        def indicator(title: str = "", overlay: bool = True, **kwargs: Any) -> None:
            self._meta = {"title": title, "overlay": overlay, **kwargs}

        drawing_namespaces = self._drawing_namespaces()
        return {
            "indicator": indicator,
            "params": self.params,
            "syminfo": self.settings.syminfo,
            "timeframe": self.settings.timeframe,
            "session": self.settings.session,
            "true": True,
            "false": False,
            "color": color_singleton,
            "math": PyneMath(mintick=getattr(self.settings.syminfo, "mintick", 0.01)),
            "pyne": pyne_cache_namespace,
            "cache": pyne_cache_namespace.cache,
            "cache_clear": pyne_cache_namespace.cache_clear,
            "cache_stats": pyne_cache_namespace.cache_stats,
            **drawing_namespaces,
            "__builtins__": build_builtins(self.policy),
        }

    def _drawing_namespaces(self) -> dict[str, Any]:
        def ctx() -> IncrementalContext:
            if self._active_ctx is None:
                raise PyneSecurityError("Drawing objects can only be mutated inside incremental callbacks")
            return self._active_ctx

        line_namespace = SimpleNamespace(
            new=lambda *args, **kwargs: ctx().line_new(*args, **kwargs),
            set_xy1=lambda *args, **kwargs: ctx().line_set_xy1(*args, **kwargs),
            set_xy2=lambda *args, **kwargs: ctx().line_set_xy2(*args, **kwargs),
            set_x1=lambda *args, **kwargs: ctx().line_set_x1(*args, **kwargs),
            set_y1=lambda *args, **kwargs: ctx().line_set_y1(*args, **kwargs),
            set_x2=lambda *args, **kwargs: ctx().line_set_x2(*args, **kwargs),
            set_y2=lambda *args, **kwargs: ctx().line_set_y2(*args, **kwargs),
            set_color=lambda *args, **kwargs: ctx().line_set_color(*args, **kwargs),
            set_width=lambda *args, **kwargs: ctx().line_set_width(*args, **kwargs),
            set_style=lambda *args, **kwargs: ctx().line_set_style(*args, **kwargs),
            set_extend=lambda *args, **kwargs: ctx().line_set_extend(*args, **kwargs),
            delete=lambda *args, **kwargs: ctx().line_delete(*args, **kwargs),
            style_solid="solid",
            style_dashed="dashed",
            style_dotted="dotted",
            extend_none="none",
            extend_left="left",
            extend_right="right",
            extend_both="both",
        )
        label_namespace = SimpleNamespace(
            new=lambda *args, **kwargs: ctx().label_new(*args, **kwargs),
            set_xy=lambda *args, **kwargs: ctx().label_set_xy(*args, **kwargs),
            set_x=lambda *args, **kwargs: ctx().label_set_x(*args, **kwargs),
            set_y=lambda *args, **kwargs: ctx().label_set_y(*args, **kwargs),
            set_text=lambda *args, **kwargs: ctx().label_set_text(*args, **kwargs),
            set_color=lambda *args, **kwargs: ctx().label_set_color(*args, **kwargs),
            set_textcolor=lambda *args, **kwargs: ctx().label_set_textcolor(*args, **kwargs),
            set_style=lambda *args, **kwargs: ctx().label_set_style(*args, **kwargs),
            set_size=lambda *args, **kwargs: ctx().label_set_size(*args, **kwargs),
            set_xloc=lambda *args, **kwargs: ctx().label_set_xloc(*args, **kwargs),
            set_yloc=lambda *args, **kwargs: ctx().label_set_yloc(*args, **kwargs),
            delete=lambda *args, **kwargs: ctx().label_delete(*args, **kwargs),
            style_label_up="label_up",
            style_label_down="label_down",
            style_label_left="label_left",
            style_label_right="label_right",
            style_label_center="label_center",
        )
        box_namespace = SimpleNamespace(
            new=lambda *args, **kwargs: ctx().box_new(*args, **kwargs),
            set_left=lambda *args, **kwargs: ctx().box_set_left(*args, **kwargs),
            set_top=lambda *args, **kwargs: ctx().box_set_top(*args, **kwargs),
            set_right=lambda *args, **kwargs: ctx().box_set_right(*args, **kwargs),
            set_bottom=lambda *args, **kwargs: ctx().box_set_bottom(*args, **kwargs),
            set_lefttop=lambda *args, **kwargs: ctx().box_set_lefttop(*args, **kwargs),
            set_rightbottom=lambda *args, **kwargs: ctx().box_set_rightbottom(*args, **kwargs),
            set_bgcolor=lambda *args, **kwargs: ctx().box_set_bgcolor(*args, **kwargs),
            set_border_color=lambda *args, **kwargs: ctx().box_set_border_color(*args, **kwargs),
            set_border_width=lambda *args, **kwargs: ctx().box_set_border_width(*args, **kwargs),
            delete=lambda *args, **kwargs: ctx().box_delete(*args, **kwargs),
            border_style_solid="solid",
            border_style_dashed="dashed",
            border_style_dotted="dotted",
        )
        table_namespace = SimpleNamespace(
            new=lambda *args, **kwargs: ctx().table_new(*args, **kwargs),
            cell=lambda *args, **kwargs: ctx().table_cell(*args, **kwargs),
            clear=lambda *args, **kwargs: ctx().table_clear(*args, **kwargs),
            set_position=lambda *args, **kwargs: ctx().table_set_position(*args, **kwargs),
            set_bgcolor=lambda *args, **kwargs: ctx().table_set_bgcolor(*args, **kwargs),
            set_frame_color=lambda *args, **kwargs: ctx().table_set_frame_color(*args, **kwargs),
            set_border_color=lambda *args, **kwargs: ctx().table_set_border_color(*args, **kwargs),
            delete=lambda *args, **kwargs: ctx().table_delete(*args, **kwargs),
        )
        return {
            "line": line_namespace,
            "label": label_namespace,
            "box": box_namespace,
            "table": table_namespace,
            "position": SimpleNamespace(
                top_left="top_left",
                top_center="top_center",
                top_right="top_right",
                middle_left="middle_left",
                middle_center="middle_center",
                middle_right="middle_right",
                bottom_left="bottom_left",
                bottom_center="bottom_center",
                bottom_right="bottom_right",
            ),
            "xloc": SimpleNamespace(bar_index="bar_index", bar_time="bar_time"),
            "yloc": SimpleNamespace(price="price", abovebar="abovebar", belowbar="belowbar"),
            "text": SimpleNamespace(
                align_left="left",
                align_center="center",
                align_right="right",
                align_top="top",
                align_middle="middle",
                align_bottom="bottom",
            ),
            "size": SimpleNamespace(
                tiny="tiny",
                small="small",
                normal="normal",
                large="large",
                huge="huge",
            ),
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
                max_drawing_objects=self.settings.max_drawing_objects,
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


def _filter_object_events(
    events: list[dict[str, Any]],
    start_s: int | None,
    end_s: int | None,
) -> list[dict[str, Any]]:
    if start_s is None and end_s is None:
        return copy.deepcopy(events)
    filtered = []
    for event in events:
        try:
            ts = int(event.get("time"))
        except (TypeError, ValueError):
            continue
        if start_s is not None and ts < start_s:
            continue
        if end_s is not None and ts > end_s:
            continue
        filtered.append(copy.deepcopy(event))
    return filtered


def _drawing_scalar(value: Any) -> Any:
    if isinstance(value, StateCell):
        value = value.value
    if value is None:
        return None
    if isinstance(value, bool | str | int):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) else _round8(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return None if math.isnan(number) else _round8(number)


def _upsert_table_cell(entry: dict[str, Any], cell: dict[str, Any]) -> None:
    cells = entry.setdefault("cells", [])
    for idx, existing in enumerate(cells):
        if existing.get("column") == cell["column"] and existing.get("row") == cell["row"]:
            cells[idx] = cell
            return
    cells.append(cell)
    cells.sort(key=lambda item: (item.get("row", 0), item.get("column", 0)))


def _round8(value: float) -> float:
    return round(float(value), 8)


def _trade_float(trade: dict[str, Any], key: str) -> float:
    value = trade.get(key)
    if value is None or value == "":
        return math.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


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


def _normalize_allowed_entry_direction(value: str) -> str:
    normalized = str(value or IncrementalStrategyDirection.all).strip().lower()
    aliases = {
        "all": IncrementalStrategyDirection.all,
        "both": IncrementalStrategyDirection.all,
        "strategy.direction.all": IncrementalStrategyDirection.all,
        "strategy.direction.both": IncrementalStrategyDirection.all,
        "long": IncrementalStrategyDirection.long,
        "strategy.long": IncrementalStrategyDirection.long,
        "strategy.direction.long": IncrementalStrategyDirection.long,
        "short": IncrementalStrategyDirection.short,
        "strategy.short": IncrementalStrategyDirection.short,
        "strategy.direction.short": IncrementalStrategyDirection.short,
        "none": IncrementalStrategyDirection.none,
        "false": IncrementalStrategyDirection.none,
        "off": IncrementalStrategyDirection.none,
        "strategy.direction.none": IncrementalStrategyDirection.none,
    }
    return aliases.get(normalized, IncrementalStrategyDirection.all)


def _normalize_risk_mode(value: str) -> str:
    normalized = str(value or IncrementalStrategyRiskMode.percent_of_equity).strip().lower()
    if normalized in {
        "percent",
        "percent_of_equity",
        "strategy.percent_of_equity",
        "strategy.risk.percent_of_equity",
    }:
        return IncrementalStrategyRiskMode.percent_of_equity
    if normalized in {"cash", "money", "strategy.cash", "strategy.risk.cash"}:
        return IncrementalStrategyRiskMode.cash
    return IncrementalStrategyRiskMode.percent_of_equity


def _normalize_commission_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"percent", "strategy.commission.percent"}:
        return IncrementalStrategyCommission.percent
    if normalized in {"cash_per_order", "cash_per_order_contract", "strategy.commission.cash_per_order"}:
        return IncrementalStrategyCommission.cash_per_order
    if normalized in {"cash_per_contract", "cash_per_contracts", "strategy.commission.cash_per_contract"}:
        return IncrementalStrategyCommission.cash_per_contract
    return normalized


def _commission_amount(
    *,
    commission_type: str | None,
    commission_value: float,
    qty: float,
    price: float,
) -> float:
    if commission_type is None or commission_value <= 0:
        return 0.0
    if commission_type == IncrementalStrategyCommission.percent:
        return abs(float(qty) * float(price)) * commission_value / 100.0
    if commission_type == IncrementalStrategyCommission.cash_per_order:
        return commission_value
    if commission_type == IncrementalStrategyCommission.cash_per_contract:
        return abs(float(qty)) * commission_value
    return 0.0


def _entry_rejection_reason(
    *,
    side: str,
    previous_size: float,
    same_direction_entry_count: int,
    pyramiding: int,
    allow_entry_in: str = IncrementalStrategyDirection.all,
) -> str | None:
    if allow_entry_in == IncrementalStrategyDirection.none:
        return "direction_not_allowed"
    if allow_entry_in == IncrementalStrategyDirection.long and side != IncrementalStrategyNamespace.long:
        return "direction_not_allowed"
    if allow_entry_in == IncrementalStrategyDirection.short and side != IncrementalStrategyNamespace.short:
        return "direction_not_allowed"
    if previous_size == 0:
        return None
    if side == IncrementalStrategyNamespace.long and previous_size < 0:
        return None
    if side == IncrementalStrategyNamespace.short and previous_size > 0:
        return None
    if same_direction_entry_count >= pyramiding + 1:
        return "pyramiding_exceeded"
    return None


def _entry_qty_for_max_position_size(
    *,
    side: str,
    previous_size: float,
    requested_qty: float,
    max_position_size: float | None,
) -> float:
    qty = abs(float(requested_qty))
    if max_position_size is None:
        return qty
    limit = max(float(max_position_size), 0.0)
    if side == IncrementalStrategyNamespace.long:
        available = limit - float(previous_size) if previous_size > 0 else limit
    else:
        available = limit + float(previous_size) if previous_size < 0 else limit
    return max(min(qty, available), 0.0)


def _max_drawdown_hit(
    *,
    equity: float,
    peak_equity: float,
    threshold: float,
    risk_type: str,
) -> bool:
    if threshold <= 0:
        return False
    drawdown = max(float(peak_equity) - float(equity), 0.0)
    if risk_type == IncrementalStrategyRiskMode.cash:
        return drawdown >= threshold
    if peak_equity <= 0:
        return False
    return drawdown / peak_equity * 100.0 >= threshold


def _intraday_filled_orders_hit(*, filled_orders: int, threshold: int | None) -> bool:
    if threshold is None:
        return False
    return int(filled_orders) >= max(int(threshold), 0)


def _margin_required(
    *,
    position_size: float,
    price: float,
    margin_percent: float,
    pointvalue: float,
) -> float:
    if position_size == 0 or margin_percent <= 0:
        return 0.0
    return abs(float(position_size) * float(price) * float(pointvalue)) * margin_percent / 100.0


def _is_exposure_reduction(previous_size: float, next_size: float) -> bool:
    if previous_size == 0:
        return False
    if (previous_size > 0) != (next_size > 0):
        return False
    return abs(next_size) <= abs(previous_size)


def _incremental_strategy_lifecycle_events(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for order in sorted(orders, key=lambda item: (item.get("_submit_time", item.get("time", 0)), item.get("_seq", 0))):
        order_type = str(order.get("type", ""))
        pending = bool(order.get("_pending_submission"))
        active = bool(order.get("_active", True))
        canceled = bool(order.get("_canceled")) or order_type in {"cancel", "cancel_all"}
        rejected = bool(order.get("_rejected_reason"))
        if canceled:
            status = "canceled"
            phase = "pending_canceled" if pending else "cancel"
        elif rejected:
            status = "rejected"
            phase = "pending_rejected" if pending else "rejected"
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
            "rejected_time": order.get("_rejected_time") if rejected else None,
            "side": order.get("side"),
            "qty": order.get("qty"),
            "price": order.get("price"),
            "position_after": order.get("position_after"),
        }
        if order.get("reason") is not None:
            event["reason"] = order.get("reason")
        if order.get("comment") is not None:
            event["comment"] = order.get("comment")
        if order.get("commission") is not None:
            event["commission"] = order.get("commission")
        if order.get("oca_name") is not None:
            event["oca_name"] = order.get("oca_name")
        if order.get("oca_type") is not None:
            event["oca_type"] = order.get("oca_type")
        if order.get("_limit") is not None:
            event["limit"] = order.get("_limit")
        if order.get("_stop") is not None:
            event["stop"] = order.get("_stop")
        if order.get("_requested_fill_qty") is not None and (active or rejected or (pending and order.get("reason"))):
            event["requested_qty"] = _round8(float(order.get("_requested_fill_qty", 0.0)))
        if order.get("_filled_qty") is not None and (active or rejected):
            event["filled_qty"] = _round8(float(order.get("_filled_qty", 0.0)))
        if order.get("_target_qty") is not None:
            event["target_qty"] = _round8(float(order.get("_target_qty", 0.0)))
        if order.get("_qty_percent") is not None:
            event["qty_percent"] = _round8(float(order.get("_qty_percent", 0.0)))
        if order.get("_transaction_qty") is not None:
            event["transaction_qty"] = _round8(float(order.get("_transaction_qty", 0.0)))
        if order.get("_canceled_by") is not None:
            event["canceled_by"] = order.get("_canceled_by")
        if order.get("_rejected_reason") is not None:
            event["rejected_reason"] = order.get("_rejected_reason")
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
