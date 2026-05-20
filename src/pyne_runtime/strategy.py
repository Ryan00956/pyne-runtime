"""Pine-like strategy event helpers."""
from __future__ import annotations

from typing import Any

import numpy as np

from .context import PyneContext
from .plot import OutputCollector
from .series import PyneSeries
from .state import PyneVar
from .values import is_na_value


class StrategyCommission:
    """Pine-like commission type constants."""

    percent = "percent"
    cash_per_order = "cash_per_order"
    cash_per_contract = "cash_per_contract"


class StrategyOca:
    """Pine-like OCA group constants."""

    none = "none"
    cancel = "cancel"
    reduce = "reduce"


class StrategyDirection:
    """Pine-like strategy direction constants."""

    all = "all"
    both = "all"
    long = "long"
    short = "short"
    none = "none"


class StrategyRiskMode:
    """Pine-like risk value type constants."""

    percent_of_equity = "percent_of_equity"
    cash = "cash"


class StrategyRiskNamespace:
    """Pine-like ``strategy.risk`` configuration namespace."""

    all = StrategyDirection.all
    both = StrategyDirection.both
    long = StrategyDirection.long
    short = StrategyDirection.short
    none = StrategyDirection.none
    percent_of_equity = StrategyRiskMode.percent_of_equity
    cash = StrategyRiskMode.cash

    def __init__(self, strategy: "StrategyModule") -> None:
        self._strategy = strategy

    def allow_entry_in(self, direction: str = StrategyDirection.all) -> None:
        self._strategy._allow_entry_in = _normalize_allowed_entry_direction(direction)

    def max_drawdown(
        self,
        value: float,
        type: str = StrategyRiskMode.percent_of_equity,
    ) -> None:
        self._strategy._max_drawdown_value = max(float(value), 0.0)
        self._strategy._max_drawdown_type = _normalize_risk_mode(type)

    def max_intraday_loss(
        self,
        value: float,
        type: str = StrategyRiskMode.percent_of_equity,
    ) -> None:
        self._strategy._max_intraday_loss_value = max(float(value), 0.0)
        self._strategy._max_intraday_loss_type = _normalize_risk_mode(type)

    def max_position_size(self, contracts: float) -> None:
        self._strategy._max_position_size = max(float(contracts), 0.0)


class StrategyTradesNamespace:
    """Script-facing trade ledger namespace.

    The object behaves like a count series for plotting and exposes Pine-like
    field accessors for the current replayed ledger.
    """

    def __init__(self, strategy: "StrategyModule", kind: str) -> None:
        self._strategy = strategy
        self._kind = kind

    @property
    def count(self) -> PyneSeries:
        return PyneSeries(self.to_numpy(), name=f"strategy.{self._kind}")

    def to_numpy(self) -> np.ndarray:
        if self._kind == "closedtrades":
            return self._strategy._closedtrades_count.copy()
        return self._strategy._opentrades_count.copy()

    def size(self, trade_num: int = -1) -> float:
        return _trade_float(self._trade(trade_num), "qty")

    def qty(self, trade_num: int = -1) -> float:
        return self.size(trade_num)

    def profit(self, trade_num: int = -1) -> float:
        return _trade_float(self._trade(trade_num), "profit")

    def net_profit(self, trade_num: int = -1) -> float:
        return _trade_float(self._trade(trade_num), "net_profit")

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

    def _trade(self, trade_num: int) -> dict[str, Any]:
        trades = (
            self._strategy._closed_trades
            if self._kind == "closedtrades"
            else self._strategy._open_trades
        )
        if not trades:
            return {}
        index = int(trade_num)
        if index < 0:
            index = len(trades) + index
        if index < 0 or index >= len(trades):
            return {}
        return trades[index]


class StrategyModule:
    """Lightweight Pine-like ``strategy`` namespace.

    This module emits deterministic strategy events and maintains a simple
    position timeline. It is not a broker simulator.
    """

    long = "long"
    short = "short"
    commission = StrategyCommission
    oca = StrategyOca
    direction = StrategyDirection
    percent_of_equity = StrategyRiskMode.percent_of_equity
    cash = StrategyRiskMode.cash

    def __init__(self, context: PyneContext, collector: OutputCollector) -> None:
        self._context = context
        self._collector = collector
        self._position_size = np.zeros(context.bar_count, dtype=np.float64)
        self._position_avg_price = np.full(context.bar_count, np.nan, dtype=np.float64)
        self._equity = np.zeros(context.bar_count, dtype=np.float64)
        self._netprofit = np.zeros(context.bar_count, dtype=np.float64)
        self._openprofit = np.zeros(context.bar_count, dtype=np.float64)
        self._grossprofit = np.zeros(context.bar_count, dtype=np.float64)
        self._grossloss = np.zeros(context.bar_count, dtype=np.float64)
        self._closedtrades_count = np.zeros(context.bar_count, dtype=np.float64)
        self._opentrades_count = np.zeros(context.bar_count, dtype=np.float64)
        self._closed_trades: list[dict[str, Any]] = []
        self._open_trades: list[dict[str, Any]] = []
        self._closedtrades_namespace = StrategyTradesNamespace(self, "closedtrades")
        self._opentrades_namespace = StrategyTradesNamespace(self, "opentrades")
        self._touched = False
        self._event_seq = 0
        self._pyramiding = 0
        self._allow_entry_in = StrategyDirection.all
        self._max_drawdown_value: float | None = None
        self._max_drawdown_type = StrategyRiskMode.percent_of_equity
        self._max_intraday_loss_value: float | None = None
        self._max_intraday_loss_type = StrategyRiskMode.percent_of_equity
        self._max_position_size: float | None = None
        self._risk_locked = False
        self.risk = StrategyRiskNamespace(self)
        self._initial_capital = 100000.0
        self._currency = str(context.syminfo.currency or "")
        self._slippage_ticks = 0
        self._mintick = max(float(context.syminfo.mintick), 0.0)
        self._commission_type: str | None = None
        self._commission_value = 0.0
        self._backtest_fill_limits_assumption = 0
        self._margin_long = 100.0
        self._margin_short = 100.0

    def __call__(self, title: str = "", overlay: bool = True, **kwargs: Any) -> None:
        """Declare strategy metadata and Pine-like replay settings."""
        config = {
            key: kwargs.get(key)
            for key in (
                "pyramiding",
                "slippage",
                "mintick",
                "min_tick",
                "commission_type",
                "commission_value",
                "initial_capital",
                "currency",
                "backtest_fill_limits_assumption",
                "margin_long",
                "margin_short",
            )
            if key in kwargs
        }
        self.configure(**config)
        self._collector.set_indicator_meta(
            title=title,
            overlay=overlay,
            script_type="strategy",
            **kwargs,
        )

    def configure(
        self,
        *,
        pyramiding: int | None = None,
        slippage: int | None = None,
        mintick: float | None = None,
        min_tick: float | None = None,
        commission_type: str | None = None,
        commission_value: float | None = None,
        initial_capital: float | None = None,
        currency: str | None = None,
        backtest_fill_limits_assumption: int | None = None,
        margin_long: float | None = None,
        margin_short: float | None = None,
    ) -> None:
        """Configure lightweight strategy replay options.

        ``pyramiding`` follows Pine's mental model: ``0`` allows the first
        same-direction entry and blocks additional same-direction entries.
        Positive values allow that many additional same-direction entries.
        """
        if pyramiding is not None:
            self._pyramiding = max(int(pyramiding), 0)
        if slippage is not None:
            self._slippage_ticks = max(int(slippage), 0)
        tick_value = mintick if mintick is not None else min_tick
        if tick_value is not None:
            self._mintick = max(float(tick_value), 0.0)
        if commission_type is not None:
            self._commission_type = _normalize_commission_type(commission_type)
        if commission_value is not None:
            self._commission_value = max(float(commission_value), 0.0)
        if initial_capital is not None:
            self._initial_capital = max(float(initial_capital), 0.0)
        if currency is not None:
            self._currency = str(currency)
        if backtest_fill_limits_assumption is not None:
            self._backtest_fill_limits_assumption = max(
                int(backtest_fill_limits_assumption),
                0,
            )
        if margin_long is not None:
            self._margin_long = max(float(margin_long), 0.0)
        if margin_short is not None:
            self._margin_short = max(float(margin_short), 0.0)

    @property
    def position_size(self) -> PyneSeries:
        return PyneSeries(self._position_size.copy(), name="strategy.position_size")

    @property
    def position_avg_price(self) -> PyneSeries:
        return PyneSeries(
            self._position_avg_price.copy(),
            name="strategy.position_avg_price",
        )

    @property
    def equity(self) -> PyneSeries:
        return PyneSeries(self._equity.copy(), name="strategy.equity")

    @property
    def netprofit(self) -> PyneSeries:
        return PyneSeries(self._netprofit.copy(), name="strategy.netprofit")

    @property
    def openprofit(self) -> PyneSeries:
        return PyneSeries(self._openprofit.copy(), name="strategy.openprofit")

    @property
    def grossprofit(self) -> PyneSeries:
        return PyneSeries(self._grossprofit.copy(), name="strategy.grossprofit")

    @property
    def grossloss(self) -> PyneSeries:
        return PyneSeries(self._grossloss.copy(), name="strategy.grossloss")

    @property
    def closedtrades(self) -> StrategyTradesNamespace:
        return self._closedtrades_namespace

    @property
    def opentrades(self) -> StrategyTradesNamespace:
        return self._opentrades_namespace

    def entry(
        self,
        id: str,
        direction: str = long,
        *,
        qty: float = 1.0,
        when: PyneSeries | np.ndarray | list | bool = True,
        price: PyneSeries | np.ndarray | list | float | None = None,
        limit: PyneSeries | np.ndarray | list | float | None = None,
        stop: PyneSeries | np.ndarray | list | float | None = None,
        oca_name: str = "",
        oca_type: str | None = None,
        comment: str = "",
    ) -> None:
        """Emit entry events when ``when`` is true."""
        self.entry_when(
            when,
            id=id,
            direction=direction,
            qty=qty,
            price=price,
            limit=limit,
            stop=stop,
            oca_name=oca_name,
            oca_type=oca_type,
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
        limit: PyneSeries | np.ndarray | list | float | None = None,
        stop: PyneSeries | np.ndarray | list | float | None = None,
        oca_name: str = "",
        oca_type: str | None = None,
        comment: str = "",
    ) -> None:
        flags = _condition_values(condition, self._context.bar_count)
        prices = _price_values(price, self._context.close, self._context.bar_count)
        limits = _optional_price_values(limit, self._context.bar_count)
        stops = _optional_price_values(stop, self._context.bar_count)
        side = _normalize_direction(direction)
        qty_abs = abs(float(qty))

        for idx, flag in enumerate(flags):
            if not flag:
                continue
            event_price = prices[idx]
            self._collector.strategy_orders.append({
                "time": self._context.times[idx],
                "id": str(id),
                "type": "entry",
                "side": side,
                "qty": qty_abs,
                "price": round(float(event_price), 8),
                "position_after": 0.0,
                "comment": comment,
                "_base_price": float(event_price),
                "_limit": limits[idx],
                "_stop": stops[idx],
                "_original_qty": qty_abs,
                "_oca_name": str(oca_name or ""),
                "_oca_type": _normalize_oca_type(oca_type),
                "_submit_time": self._context.times[idx],
                "_seq": self._next_event_seq(),
            })
            self._touched = True

        self._replay_position()
        self._sync_position_snapshot()

    def order(
        self,
        id: str,
        direction: str = long,
        *,
        qty: float = 1.0,
        when: PyneSeries | np.ndarray | list | bool = True,
        price: PyneSeries | np.ndarray | list | float | None = None,
        limit: PyneSeries | np.ndarray | list | float | None = None,
        stop: PyneSeries | np.ndarray | list | float | None = None,
        oca_name: str = "",
        oca_type: str | None = None,
        comment: str = "",
    ) -> None:
        """Emit lower-level strategy order events when ``when`` is true."""
        self.order_when(
            when,
            id=id,
            direction=direction,
            qty=qty,
            price=price,
            limit=limit,
            stop=stop,
            oca_name=oca_name,
            oca_type=oca_type,
            comment=comment,
        )

    def order_when(
        self,
        condition: PyneSeries | np.ndarray | list | bool,
        id: str,
        direction: str = long,
        *,
        qty: float = 1.0,
        price: PyneSeries | np.ndarray | list | float | None = None,
        limit: PyneSeries | np.ndarray | list | float | None = None,
        stop: PyneSeries | np.ndarray | list | float | None = None,
        oca_name: str = "",
        oca_type: str | None = None,
        comment: str = "",
    ) -> None:
        """Emit lower-level order events when ``condition`` is true.

        Unlike ``entry_when()``, these events are not limited by pyramiding.
        They add, reduce, or reverse the replayed net position.
        """
        flags = _condition_values(condition, self._context.bar_count)
        prices = _price_values(price, self._context.close, self._context.bar_count)
        limits = _optional_price_values(limit, self._context.bar_count)
        stops = _optional_price_values(stop, self._context.bar_count)
        side = _normalize_direction(direction)
        qty_abs = abs(float(qty))

        for idx, flag in enumerate(flags):
            if not flag:
                continue
            event_price = prices[idx]
            self._collector.strategy_orders.append({
                "time": self._context.times[idx],
                "id": str(id),
                "type": "order",
                "side": side,
                "qty": qty_abs,
                "price": round(float(event_price), 8),
                "position_after": 0.0,
                "comment": comment,
                "_base_price": float(event_price),
                "_limit": limits[idx],
                "_stop": stops[idx],
                "_original_qty": qty_abs,
                "_oca_name": str(oca_name or ""),
                "_oca_type": _normalize_oca_type(oca_type),
                "_submit_time": self._context.times[idx],
                "_seq": self._next_event_seq(),
            })
            self._touched = True

        self._replay_position()
        self._sync_position_snapshot()

    def cancel(
        self,
        id: str,
        *,
        when: PyneSeries | np.ndarray | list | bool = True,
        comment: str = "",
    ) -> None:
        """Cancel pending orders with a matching id."""
        flags = _condition_values(when, self._context.bar_count)
        for idx, flag in enumerate(flags):
            if not flag:
                continue
            self._collector.strategy_orders.append({
                "time": self._context.times[idx],
                "id": str(id),
                "type": "cancel",
                "side": "flat",
                "qty": 0.0,
                "price": None,
                "position_after": 0.0,
                "comment": comment,
                "_seq": self._next_event_seq(),
            })
            self._touched = True

        self._replay_position()
        self._sync_position_snapshot()

    def cancel_all(
        self,
        *,
        when: PyneSeries | np.ndarray | list | bool = True,
        comment: str = "",
    ) -> None:
        """Cancel all pending strategy entry/order events."""
        flags = _condition_values(when, self._context.bar_count)
        for idx, flag in enumerate(flags):
            if not flag:
                continue
            self._collector.strategy_orders.append({
                "time": self._context.times[idx],
                "id": "cancel_all",
                "type": "cancel_all",
                "side": "flat",
                "qty": 0.0,
                "price": None,
                "position_after": 0.0,
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
                "_base_price": float(event_price),
                "_seq": self._next_event_seq(),
            })
            self._touched = True
            self._replay_position()

        self._sync_position_snapshot()

    def close_all(
        self,
        *,
        when: PyneSeries | np.ndarray | list | bool = True,
        price: PyneSeries | np.ndarray | list | float | None = None,
        comment: str = "",
    ) -> None:
        """Emit close-all events when ``when`` is true."""
        flags = _condition_values(when, self._context.bar_count)
        prices = _price_values(price, self._context.close, self._context.bar_count)

        for idx, flag in enumerate(flags):
            if not flag:
                continue
            event_price = prices[idx]
            self._collector.strategy_orders.append({
                "time": self._context.times[idx],
                "id": "close_all",
                "type": "close_all",
                "side": "flat",
                "qty": 0.0,
                "price": round(float(event_price), 8),
                "position_after": 0.0,
                "comment": comment,
                "_base_price": float(event_price),
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
                tick_verify=self._limit_fill_verification_amount(),
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
                "_base_price": float(event_price),
                "_seq": self._next_event_seq(),
            })
            self._touched = True
            self._replay_position()

        self._sync_position_snapshot()

    def _replay_position(self) -> None:
        current_size = 0.0
        current_avg = np.nan
        same_direction_entry_count = 0
        gross_profit = 0.0
        gross_loss = 0.0
        total_commission = 0.0
        closed_trades: list[dict[str, Any]] = []
        open_trades: list[dict[str, Any]] = []
        pending_orders: list[dict[str, Any]] = []
        orders_by_time: dict[int, list[dict[str, Any]]] = {}
        drawdown_locked = False
        intraday_locked = False
        risk_locked = False
        peak_equity = self._initial_capital
        intraday_peak_equity = self._initial_capital
        session_first = _condition_values(self._context.session.isfirstbar, self._context.bar_count)
        for order in sorted(
            self._collector.strategy_orders,
            key=lambda item: (item.get("time", 0), item.get("_seq", 0)),
        ):
            order["_active"] = False
            if order.get("type") in {"entry", "order"}:
                order.pop("_canceled", None)
                order["time"] = int(order.get("_submit_time", order.get("time", 0)))
                order["qty"] = float(order.get("_original_qty", order.get("qty", 0.0)))
                order["position_after"] = 0.0
                order["price"] = round(float(order.get("_base_price", order.get("price", np.nan))), 8)
                order.pop("commission", None)
                order.pop("oca_name", None)
                order.pop("oca_type", None)
                if _is_pending_submission(order):
                    order.pop("reason", None)
            elif order.get("type") in {"cancel", "cancel_all"}:
                order.pop("canceled", None)
            orders_by_time.setdefault(int(order.get("time", 0)), []).append(order)

        for idx, timestamp in enumerate(self._context.times):
            if session_first[idx]:
                intraday_locked = False
                intraday_peak_equity = (
                    float(self._equity[idx - 1])
                    if idx > 0
                    else self._initial_capital
                )
            risk_locked = drawdown_locked or intraday_locked
            for order in orders_by_time.get(timestamp, []):
                if order.get("type") == "entry":
                    if risk_locked:
                        continue
                    if _is_pending_submission(order):
                        pending_orders.append(order)
                        continue
                    side = _normalize_direction(str(order.get("side", self.long)))
                    if not _entry_allowed(
                        side=side,
                        previous_size=current_size,
                        same_direction_entry_count=same_direction_entry_count,
                        pyramiding=self._pyramiding,
                        allow_entry_in=self._allow_entry_in,
                    ):
                        continue
                    fill_side = "buy" if side == self.long else "sell"
                    fill_price = self._fill_price(float(order.get("_base_price", order.get("price", np.nan))), fill_side)
                    qty = _entry_qty_for_max_position_size(
                        side=side,
                        previous_size=current_size,
                        requested_qty=float(order.get("qty", 0.0)),
                        max_position_size=self._max_position_size,
                    )
                    if qty <= 0:
                        continue
                    position_after, avg_after = _entry_position_after(
                        previous_size=current_size,
                        previous_avg=current_avg,
                        side=side,
                        qty=qty,
                        price=fill_price,
                    )
                    pre_fill_equity = _strategy_equity(
                        initial_capital=self._initial_capital,
                        gross_profit=gross_profit,
                        gross_loss=gross_loss,
                        total_commission=total_commission,
                        position_size=current_size,
                        position_avg=current_avg,
                        close_price=float(self._context.close.values[idx]),
                    )
                    if not self._margin_allows_position(
                        previous_size=current_size,
                        next_size=position_after,
                        price=fill_price,
                        equity=pre_fill_equity,
                    ):
                        continue
                    if current_size == 0 or (current_size > 0) != (position_after > 0):
                        same_direction_entry_count = 1
                    else:
                        same_direction_entry_count += 1
                    previous_size = current_size
                    current_size = position_after
                    current_avg = avg_after
                    order["qty"] = round(qty, 8)
                    order["price"] = round(float(fill_price), 8)
                    order["position_after"] = round(float(position_after), 8)
                    commission = self._apply_commission(
                        order,
                        qty=qty,
                        price=fill_price,
                    )
                    signed_qty = qty if side == self.long else -qty
                    gross_profit, gross_loss, total_commission, open_trades = _record_fill(
                        order=order,
                        signed_qty=position_after - previous_size,
                        previous_size=previous_size,
                        fill_price=fill_price,
                        next_size=position_after,
                        commission=commission,
                        open_trades=open_trades,
                        closed_trades=closed_trades,
                        gross_profit=gross_profit,
                        gross_loss=gross_loss,
                        total_commission=total_commission,
                    )
                    order["_avg_price_after"] = round(float(avg_after), 8) if not is_na_value(avg_after) else None
                    order["_active"] = True
                elif order.get("type") == "order":
                    if risk_locked:
                        continue
                    if _is_pending_submission(order):
                        pending_orders.append(order)
                        continue
                    side = _normalize_direction(str(order.get("side", self.long)))
                    fill_side = "buy" if side == self.long else "sell"
                    fill_price = self._fill_price(float(order.get("_base_price", order.get("price", np.nan))), fill_side)
                    qty = float(order.get("qty", 0.0))
                    position_after, avg_after = _order_position_after(
                        previous_size=current_size,
                        previous_avg=current_avg,
                        side=side,
                        qty=qty,
                        price=fill_price,
                    )
                    pre_fill_equity = _strategy_equity(
                        initial_capital=self._initial_capital,
                        gross_profit=gross_profit,
                        gross_loss=gross_loss,
                        total_commission=total_commission,
                        position_size=current_size,
                        position_avg=current_avg,
                        close_price=float(self._context.close.values[idx]),
                    )
                    if not self._margin_allows_position(
                        previous_size=current_size,
                        next_size=position_after,
                        price=fill_price,
                        equity=pre_fill_equity,
                    ):
                        continue
                    if position_after == 0:
                        same_direction_entry_count = 0
                    elif current_size == 0 or (current_size > 0) != (position_after > 0):
                        same_direction_entry_count = 1
                    previous_size = current_size
                    current_size = position_after
                    current_avg = avg_after
                    order["price"] = round(float(fill_price), 8)
                    order["position_after"] = round(float(position_after), 8)
                    commission = self._apply_commission(order, qty=qty, price=fill_price)
                    signed_qty = qty if side == self.long else -qty
                    gross_profit, gross_loss, total_commission, open_trades = _record_fill(
                        order=order,
                        signed_qty=signed_qty,
                        previous_size=previous_size,
                        fill_price=fill_price,
                        next_size=position_after,
                        commission=commission,
                        open_trades=open_trades,
                        closed_trades=closed_trades,
                        gross_profit=gross_profit,
                        gross_loss=gross_loss,
                        total_commission=total_commission,
                    )
                    order["_avg_price_after"] = round(float(avg_after), 8) if not is_na_value(avg_after) else None
                    order["_active"] = True
                elif order.get("type") in {"close", "close_all", "exit"} and current_size != 0:
                    previous_size = current_size
                    if order.get("type") == "exit":
                        requested_qty = abs(float(order.get("qty", abs(current_size))))
                        target_qty = _target_open_qty(order, open_trades, current_size)
                        fill_qty = min(requested_qty, target_qty)
                    elif order.get("type") == "close":
                        target_qty = _target_open_qty(order, open_trades, current_size)
                        fill_qty = min(target_qty, abs(current_size))
                    else:
                        fill_qty = abs(current_size)
                    if fill_qty <= 0:
                        continue
                    remaining = abs(current_size) - fill_qty
                    next_size = 0.0
                    if remaining > 0:
                        next_size = remaining if current_size > 0 else -remaining
                    fill_side = "sell" if current_size > 0 else "buy"
                    fill_price = self._fill_price(float(order.get("_base_price", order.get("price", np.nan))), fill_side)
                    order["qty"] = round(fill_qty, 8)
                    order["price"] = round(float(fill_price), 8)
                    order["position_after"] = round(next_size, 8)
                    commission = self._apply_commission(order, qty=fill_qty, price=fill_price)
                    signed_qty = -fill_qty if previous_size > 0 else fill_qty
                    gross_profit, gross_loss, total_commission, open_trades = _record_fill(
                        order=order,
                        signed_qty=signed_qty,
                        previous_size=previous_size,
                        fill_price=fill_price,
                        next_size=next_size,
                        commission=commission,
                        open_trades=open_trades,
                        closed_trades=closed_trades,
                        gross_profit=gross_profit,
                        gross_loss=gross_loss,
                        total_commission=total_commission,
                    )
                    order["_active"] = True
                    current_size = next_size
                    if current_size == 0:
                        current_avg = np.nan
                        same_direction_entry_count = 0
                elif order.get("type") == "cancel":
                    canceled = [item for item in pending_orders if item.get("id") == order.get("id")]
                    if canceled:
                        for item in canceled:
                            item["_canceled"] = True
                        order["canceled"] = len(canceled)
                        order["_active"] = True
                    pending_orders = [item for item in pending_orders if not item.get("_canceled")]
                elif order.get("type") == "cancel_all":
                    if pending_orders:
                        for item in pending_orders:
                            item["_canceled"] = True
                        order["canceled"] = len(pending_orders)
                        order["_active"] = True
                    pending_orders = []

            if pending_orders:
                high = float(self._context.high.values[idx])
                low = float(self._context.low.values[idx])
                remaining_pending = []
                for order in sorted(pending_orders, key=lambda item: item.get("_seq", 0)):
                    if order.get("_canceled"):
                        continue
                    if risk_locked and order.get("type") in {"entry", "order"}:
                        remaining_pending.append(order)
                        continue
                    trigger = _pending_trigger(
                        side=_normalize_direction(str(order.get("side", self.long))),
                        high=high,
                        low=low,
                        limit=order.get("_limit"),
                        stop=order.get("_stop"),
                        tick_verify=self._limit_fill_verification_amount(),
                    )
                    if trigger is None:
                        remaining_pending.append(order)
                        continue
                    reason, trigger_price = trigger
                    order["time"] = timestamp
                    order["reason"] = reason
                    order["_base_price"] = float(trigger_price)
                    if order.get("type") == "entry":
                        side = _normalize_direction(str(order.get("side", self.long)))
                        if not _entry_allowed(
                            side=side,
                            previous_size=current_size,
                            same_direction_entry_count=same_direction_entry_count,
                            pyramiding=self._pyramiding,
                            allow_entry_in=self._allow_entry_in,
                        ):
                            continue
                        fill_side = "buy" if side == self.long else "sell"
                        fill_price = self._fill_price(float(trigger_price), fill_side)
                        qty = _entry_qty_for_max_position_size(
                            side=side,
                            previous_size=current_size,
                            requested_qty=float(order.get("qty", 0.0)),
                            max_position_size=self._max_position_size,
                        )
                        if qty <= 0:
                            continue
                        position_after, avg_after = _entry_position_after(
                            previous_size=current_size,
                            previous_avg=current_avg,
                            side=side,
                            qty=qty,
                            price=fill_price,
                        )
                        pre_fill_equity = _strategy_equity(
                            initial_capital=self._initial_capital,
                            gross_profit=gross_profit,
                            gross_loss=gross_loss,
                            total_commission=total_commission,
                            position_size=current_size,
                            position_avg=current_avg,
                            close_price=float(self._context.close.values[idx]),
                        )
                        if not self._margin_allows_position(
                            previous_size=current_size,
                            next_size=position_after,
                            price=fill_price,
                            equity=pre_fill_equity,
                        ):
                            remaining_pending.append(order)
                            continue
                        if current_size == 0 or (current_size > 0) != (position_after > 0):
                            same_direction_entry_count = 1
                        else:
                            same_direction_entry_count += 1
                    else:
                        side = _normalize_direction(str(order.get("side", self.long)))
                        fill_side = "buy" if side == self.long else "sell"
                        fill_price = self._fill_price(float(trigger_price), fill_side)
                        qty = float(order.get("qty", 0.0))
                        position_after, avg_after = _order_position_after(
                            previous_size=current_size,
                            previous_avg=current_avg,
                            side=side,
                            qty=qty,
                            price=fill_price,
                        )
                        pre_fill_equity = _strategy_equity(
                            initial_capital=self._initial_capital,
                            gross_profit=gross_profit,
                            gross_loss=gross_loss,
                            total_commission=total_commission,
                            position_size=current_size,
                            position_avg=current_avg,
                            close_price=float(self._context.close.values[idx]),
                        )
                        if not self._margin_allows_position(
                            previous_size=current_size,
                            next_size=position_after,
                            price=fill_price,
                            equity=pre_fill_equity,
                        ):
                            remaining_pending.append(order)
                            continue
                        if position_after == 0:
                            same_direction_entry_count = 0
                        elif current_size == 0 or (current_size > 0) != (position_after > 0):
                            same_direction_entry_count = 1
                    previous_size = current_size
                    current_size = position_after
                    current_avg = avg_after
                    if order.get("type") == "entry":
                        order["qty"] = round(qty, 8)
                    order["price"] = round(float(fill_price), 8)
                    order["position_after"] = round(float(position_after), 8)
                    if order.get("_oca_name"):
                        order["oca_name"] = order.get("_oca_name")
                        order["oca_type"] = order.get("_oca_type") or StrategyOca.none
                    fill_qty = float(order.get("qty", 0.0))
                    commission = self._apply_commission(order, qty=fill_qty, price=fill_price)
                    signed_qty = fill_qty if side == self.long else -fill_qty
                    gross_profit, gross_loss, total_commission, open_trades = _record_fill(
                        order=order,
                        signed_qty=position_after - previous_size if order.get("type") == "entry" else signed_qty,
                        previous_size=previous_size,
                        fill_price=fill_price,
                        next_size=position_after,
                        commission=commission,
                        open_trades=open_trades,
                        closed_trades=closed_trades,
                        gross_profit=gross_profit,
                        gross_loss=gross_loss,
                        total_commission=total_commission,
                    )
                    order["_avg_price_after"] = round(float(avg_after), 8) if not is_na_value(avg_after) else None
                    order["_active"] = True
                    _apply_oca_after_fill(order, pending_orders)
                pending_orders = [item for item in remaining_pending if not item.get("_canceled")]
            net_profit = gross_profit + gross_loss - total_commission
            open_profit = _open_profit(current_size, current_avg, float(self._context.close.values[idx]))
            self._position_size[idx] = current_size
            self._position_avg_price[idx] = current_avg
            self._grossprofit[idx] = gross_profit
            self._grossloss[idx] = gross_loss
            self._netprofit[idx] = net_profit
            self._openprofit[idx] = open_profit
            self._equity[idx] = self._initial_capital + net_profit + open_profit
            self._closedtrades_count[idx] = len(closed_trades)
            self._opentrades_count[idx] = len([trade for trade in open_trades if float(trade.get("qty", 0.0)) > 0])
            peak_equity = max(peak_equity, float(self._equity[idx]))
            intraday_peak_equity = max(intraday_peak_equity, float(self._equity[idx]))
            if self._max_drawdown_value is not None and _max_drawdown_hit(
                equity=float(self._equity[idx]),
                peak_equity=peak_equity,
                threshold=self._max_drawdown_value,
                risk_type=self._max_drawdown_type,
            ):
                drawdown_locked = True
            if self._max_intraday_loss_value is not None and _max_drawdown_hit(
                equity=float(self._equity[idx]),
                peak_equity=intraday_peak_equity,
                threshold=self._max_intraday_loss_value,
                risk_type=self._max_intraday_loss_type,
            ):
                intraday_locked = True
            risk_locked = drawdown_locked or intraday_locked
        self._risk_locked = risk_locked

        self._sync_strategy_report(
            closed_trades=closed_trades,
            open_trades=open_trades,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            total_commission=total_commission,
        )

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

    def _sync_strategy_report(
        self,
        *,
        closed_trades: list[dict[str, Any]],
        open_trades: list[dict[str, Any]],
        gross_profit: float,
        gross_loss: float,
        total_commission: float,
    ) -> None:
        if not self._touched:
            return
        final_openprofit = float(self._openprofit[-1]) if len(self._openprofit) else 0.0
        final_netprofit = float(self._netprofit[-1]) if len(self._netprofit) else 0.0
        final_equity = float(self._equity[-1]) if len(self._equity) else self._initial_capital
        final_close = float(self._context.close.values[-1]) if self._context.bar_count else np.nan
        serialized_open_trades = [
            {
                **trade,
                "profit": round(_trade_open_profit(trade, final_close), 8),
            }
            for trade in open_trades
            if float(trade.get("qty", 0.0)) > 0
        ]
        self._closed_trades = list(closed_trades)
        self._open_trades = list(serialized_open_trades)
        self._collector.strategy_report = {
            "summary": {
                "initial_capital": round(self._initial_capital, 8),
                "currency": self._currency,
                "equity": round(final_equity, 8),
                "netprofit": round(final_netprofit, 8),
                "openprofit": round(final_openprofit, 8),
                "grossprofit": round(gross_profit, 8),
                "grossloss": round(gross_loss, 8),
                "commission": round(total_commission, 8),
                "backtest_fill_limits_assumption": self._backtest_fill_limits_assumption,
                "margin_long": round(self._margin_long, 8),
                "margin_short": round(self._margin_short, 8),
            },
            "risk": {
                "locked": self._risk_locked,
                "max_drawdown": (
                    round(self._max_drawdown_value, 8)
                    if self._max_drawdown_value is not None
                    else None
                ),
                "max_drawdown_type": self._max_drawdown_type,
                "max_intraday_loss": (
                    round(self._max_intraday_loss_value, 8)
                    if self._max_intraday_loss_value is not None
                    else None
                ),
                "max_intraday_loss_type": self._max_intraday_loss_type,
                "max_position_size": (
                    round(self._max_position_size, 8)
                    if self._max_position_size is not None
                    else None
                ),
            },
            "closedtrades": closed_trades,
            "opentrades": serialized_open_trades,
        }

    def _next_event_seq(self) -> int:
        self._event_seq += 1
        return self._event_seq

    def _fill_price(self, price: float, side: str) -> float:
        slippage = self._slippage_ticks * self._mintick
        if side == "buy":
            return float(price) + slippage
        return float(price) - slippage

    def _apply_commission(self, order: dict[str, Any], *, qty: float, price: float) -> float:
        commission = _commission_amount(
            commission_type=self._commission_type,
            commission_value=self._commission_value,
            qty=qty,
            price=price,
        )
        if commission > 0:
            order["commission"] = round(commission, 8)
        return commission

    def _limit_fill_verification_amount(self) -> float:
        return self._backtest_fill_limits_assumption * self._mintick

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
            pointvalue=self._context.syminfo.pointvalue,
        )
        return required <= max(float(equity), 0.0)


def _condition_values(value: Any, length: int) -> list[bool]:
    values = _values(value, length)
    return [False if is_na_value(item) else bool(item) for item in values]


def _trade_float(trade: dict[str, Any], key: str) -> float:
    value = trade.get(key)
    if value is None or value == "":
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


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
    tick_verify: float = 0.0,
) -> tuple[str, float] | None:
    if current_position > 0:
        if stop is not None and low <= stop:
            return "stop", stop
        if limit is not None and high >= limit + tick_verify:
            return "limit", limit
        return None
    if stop is not None and high >= stop:
        return "stop", stop
    if limit is not None and low <= limit - tick_verify:
        return "limit", limit
    return None


def _is_pending_submission(order: dict[str, Any]) -> bool:
    return order.get("_limit") is not None or order.get("_stop") is not None


def _pending_trigger(
    *,
    side: str,
    high: float,
    low: float,
    limit: float | None,
    stop: float | None,
    tick_verify: float = 0.0,
) -> tuple[str, float] | None:
    if side == StrategyModule.long:
        if stop is not None and high >= stop:
            return "stop", float(stop)
        if limit is not None and low <= limit - tick_verify:
            return "limit", float(limit)
        return None
    if stop is not None and low <= stop:
        return "stop", float(stop)
    if limit is not None and high >= limit + tick_verify:
        return "limit", float(limit)
    return None


def _entry_allowed(
    *,
    side: str,
    previous_size: float,
    same_direction_entry_count: int,
    pyramiding: int,
    allow_entry_in: str = StrategyDirection.all,
) -> bool:
    if allow_entry_in == StrategyDirection.none:
        return False
    if allow_entry_in == StrategyDirection.long and side != StrategyModule.long:
        return False
    if allow_entry_in == StrategyDirection.short and side != StrategyModule.short:
        return False
    if previous_size == 0:
        return True
    if side == StrategyModule.long and previous_size < 0:
        return True
    if side == StrategyModule.short and previous_size > 0:
        return True
    return same_direction_entry_count < pyramiding + 1


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
    if side == StrategyModule.long:
        available = limit - float(previous_size) if previous_size > 0 else limit
    else:
        available = limit + float(previous_size) if previous_size < 0 else limit
    return max(min(qty, available), 0.0)


def _normalize_commission_type(value: str) -> str:
    normalized = str(value or "").lower()
    if normalized in {"percent", "strategy.commission.percent"}:
        return StrategyCommission.percent
    if normalized in {"cash_per_order", "cash_per_order_contract", "strategy.commission.cash_per_order"}:
        return StrategyCommission.cash_per_order
    if normalized in {"cash_per_contract", "cash_per_contracts", "strategy.commission.cash_per_contract"}:
        return StrategyCommission.cash_per_contract
    return normalized


def _normalize_allowed_entry_direction(value: str) -> str:
    normalized = str(value or StrategyDirection.all).lower()
    if normalized in {"all", "both", "strategy.direction.all", "strategy.direction.both"}:
        return StrategyDirection.all
    if normalized in {"long", "strategy.long", "strategy.direction.long"}:
        return StrategyDirection.long
    if normalized in {"short", "strategy.short", "strategy.direction.short"}:
        return StrategyDirection.short
    if normalized in {"none", "false", "off", "strategy.direction.none"}:
        return StrategyDirection.none
    return StrategyDirection.all


def _normalize_risk_mode(value: str) -> str:
    normalized = str(value or StrategyRiskMode.percent_of_equity).lower()
    if normalized in {
        "percent",
        "percent_of_equity",
        "strategy.percent_of_equity",
        "strategy.risk.percent_of_equity",
    }:
        return StrategyRiskMode.percent_of_equity
    if normalized in {"cash", "money", "strategy.cash", "strategy.risk.cash"}:
        return StrategyRiskMode.cash
    return StrategyRiskMode.percent_of_equity


def _normalize_oca_type(value: str | None) -> str:
    if value is None:
        return StrategyOca.none
    normalized = str(value or "").lower()
    if normalized in {"cancel", "strategy.oca.cancel"}:
        return StrategyOca.cancel
    if normalized in {"reduce", "strategy.oca.reduce"}:
        return StrategyOca.reduce
    if normalized in {"none", "", "strategy.oca.none"}:
        return StrategyOca.none
    return normalized


def _apply_oca_after_fill(filled_order: dict[str, Any], pending_orders: list[dict[str, Any]]) -> None:
    oca_type = filled_order.get("_oca_type")
    oca_name = str(filled_order.get("_oca_name") or "")
    if not oca_name or oca_type == StrategyOca.none:
        return
    filled_qty = abs(float(filled_order.get("qty", 0.0)))
    for order in pending_orders:
        if order is filled_order:
            continue
        if order.get("_oca_name") != oca_name or order.get("_oca_type") != oca_type:
            continue
        if oca_type == StrategyOca.cancel:
            order["_canceled"] = True
        elif oca_type == StrategyOca.reduce:
            remaining = max(float(order.get("qty", 0.0)) - filled_qty, 0.0)
            order["qty"] = remaining
            if remaining <= 0:
                order["_canceled"] = True


def _commission_amount(
    *,
    commission_type: str | None,
    commission_value: float,
    qty: float,
    price: float,
) -> float:
    if commission_type is None or commission_value <= 0:
        return 0.0
    if commission_type == StrategyCommission.percent:
        return abs(float(qty) * float(price)) * commission_value / 100.0
    if commission_type == StrategyCommission.cash_per_order:
        return commission_value
    if commission_type == StrategyCommission.cash_per_contract:
        return abs(float(qty)) * commission_value
    return 0.0


def _strategy_equity(
    *,
    initial_capital: float,
    gross_profit: float,
    gross_loss: float,
    total_commission: float,
    position_size: float,
    position_avg: float,
    close_price: float,
) -> float:
    net_profit = gross_profit + gross_loss - total_commission
    return initial_capital + net_profit + _open_profit(position_size, position_avg, close_price)


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
    if risk_type == StrategyRiskMode.cash:
        return drawdown >= threshold
    if peak_equity <= 0:
        return False
    return drawdown / peak_equity * 100.0 >= threshold


def _record_fill(
    *,
    order: dict[str, Any],
    signed_qty: float,
    previous_size: float,
    fill_price: float,
    next_size: float,
    commission: float,
    open_trades: list[dict[str, Any]],
    closed_trades: list[dict[str, Any]],
    gross_profit: float,
    gross_loss: float,
    total_commission: float,
) -> tuple[float, float, float, list[dict[str, Any]]]:
    total_commission += commission
    if signed_qty == 0:
        return gross_profit, gross_loss, total_commission, open_trades

    remaining = abs(float(signed_qty))
    fill_side = "long" if signed_qty > 0 else "short"
    previous_side = "long" if previous_size > 0 else "short" if previous_size < 0 else ""
    target_entry = _target_entry_id(order)
    closes_existing = bool(previous_side and previous_side != fill_side)

    if closes_existing:
        close_qty_total = min(abs(previous_size), remaining)
        remaining_to_close = close_qty_total
        closed_qty_done = 0.0
        for trade in list(open_trades):
            if remaining_to_close <= 0:
                break
            if trade.get("side") != previous_side:
                continue
            if target_entry and trade.get("entry_id") != target_entry:
                continue
            close_qty = min(float(trade.get("qty", 0.0)), remaining_to_close)
            if close_qty <= 0:
                continue
            profit = _trade_realized_profit(trade, close_qty, fill_price)
            commission_share = commission * close_qty / max(close_qty_total, 1e-12)
            if profit >= 0:
                gross_profit += profit
            else:
                gross_loss += profit
            closed_trades.append(_closed_trade(
                previous_trade=trade,
                order=order,
                qty=close_qty,
                exit_price=fill_price,
                profit=profit,
                commission=commission_share,
            ))
            trade["qty"] = round(float(trade.get("qty", 0.0)) - close_qty, 8)
            remaining_to_close -= close_qty
            closed_qty_done += close_qty

        open_trades = [trade for trade in open_trades if float(trade.get("qty", 0.0)) > 0]
        remaining -= closed_qty_done

    opens_new = next_size != 0 and (not closes_existing or remaining > 0)
    if opens_new and (previous_size == 0 or fill_side == ("long" if next_size > 0 else "short")):
        if remaining <= 0 and not open_trades:
            remaining = abs(next_size)
        if remaining > 0:
            open_trades.append(_open_trade_from_order(
                order=order,
                side=fill_side,
                qty=remaining,
                entry_price=fill_price,
            ))

    return gross_profit, gross_loss, total_commission, open_trades


def _target_entry_id(order: dict[str, Any]) -> str:
    if order.get("type") == "exit":
        return str(order.get("from_entry") or "")
    if order.get("type") == "close":
        return str(order.get("id") or "")
    return ""


def _target_open_qty(
    order: dict[str, Any],
    open_trades: list[dict[str, Any]],
    current_size: float,
) -> float:
    target_entry = _target_entry_id(order)
    if not target_entry:
        return abs(current_size)
    current_side = "long" if current_size > 0 else "short"
    return sum(
        abs(float(trade.get("qty", 0.0)))
        for trade in open_trades
        if trade.get("side") == current_side and trade.get("entry_id") == target_entry
    )


def _open_trade_from_order(
    *,
    order: dict[str, Any],
    side: str,
    qty: float,
    entry_price: float,
) -> dict[str, Any]:
    return {
        "entry_time": int(order.get("time", 0)),
        "entry_id": str(order.get("id", "")),
        "side": side,
        "qty": round(float(qty), 8),
        "entry_price": round(float(entry_price), 8),
    }


def _trade_realized_profit(trade: dict[str, Any], qty: float, exit_price: float) -> float:
    entry_price = float(trade.get("entry_price", 0.0))
    if trade.get("side") == "long":
        return (float(exit_price) - entry_price) * qty
    return (entry_price - float(exit_price)) * qty


def _closed_trade(
    *,
    previous_trade: dict[str, Any],
    order: dict[str, Any],
    qty: float,
    exit_price: float,
    profit: float,
    commission: float,
) -> dict[str, Any]:
    return {
        "entry_time": previous_trade.get("entry_time"),
        "exit_time": int(order.get("time", 0)),
        "entry_id": previous_trade.get("entry_id", ""),
        "exit_id": str(order.get("id", "")),
        "side": previous_trade.get("side", ""),
        "qty": round(float(qty), 8),
        "entry_price": previous_trade.get("entry_price"),
        "exit_price": round(float(exit_price), 8),
        "profit": round(float(profit), 8),
        "commission": round(float(commission), 8),
        "net_profit": round(float(profit) - float(commission), 8),
    }


def _open_profit(position_size: float, position_avg: float, close_price: float) -> float:
    if position_size == 0 or is_na_value(position_avg):
        return 0.0
    if position_size > 0:
        return (float(close_price) - float(position_avg)) * abs(position_size)
    return (float(position_avg) - float(close_price)) * abs(position_size)


def _trade_open_profit(trade: dict[str, Any], close_price: float) -> float:
    qty = abs(float(trade.get("qty", 0.0)))
    entry_price = float(trade.get("entry_price", 0.0))
    if trade.get("side") == "long":
        return (float(close_price) - entry_price) * qty
    return (entry_price - float(close_price)) * qty


def _entry_position_after(
    *,
    previous_size: float,
    previous_avg: float,
    side: str,
    qty: float,
    price: float,
) -> tuple[float, float]:
    signed_qty = qty if side == StrategyModule.long else -qty
    if previous_size == 0 or (previous_size > 0) != (signed_qty > 0):
        return signed_qty, float(price)

    new_size = previous_size + signed_qty
    if new_size == 0:
        return 0.0, np.nan
    if is_na_value(previous_avg):
        return new_size, float(price)
    weighted = (abs(previous_size) * previous_avg + qty * float(price)) / abs(new_size)
    return new_size, weighted


def _order_position_after(
    *,
    previous_size: float,
    previous_avg: float,
    side: str,
    qty: float,
    price: float,
) -> tuple[float, float]:
    signed_qty = qty if side == StrategyModule.long else -qty
    new_size = previous_size + signed_qty
    if new_size == 0:
        return 0.0, np.nan
    if previous_size == 0 or (previous_size > 0) != (new_size > 0):
        return new_size, float(price)
    if (previous_size > 0) != (signed_qty > 0):
        return new_size, previous_avg
    if is_na_value(previous_avg):
        return new_size, float(price)
    weighted = (abs(previous_size) * previous_avg + qty * float(price)) / abs(new_size)
    return new_size, weighted


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
