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


class StrategyModule:
    """Lightweight Pine-like ``strategy`` namespace.

    This module emits deterministic strategy events and maintains a simple
    position timeline. It is not a broker simulator.
    """

    long = "long"
    short = "short"
    commission = StrategyCommission
    oca = StrategyOca

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
        self._touched = False
        self._event_seq = 0
        self._pyramiding = 0
        self._initial_capital = 100000.0
        self._currency = str(context.syminfo.currency or "")
        self._slippage_ticks = 0
        self._mintick = max(float(context.syminfo.mintick), 0.0)
        self._commission_type: str | None = None
        self._commission_value = 0.0

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
        open_trade: dict[str, Any] | None = None
        pending_orders: list[dict[str, Any]] = []
        orders_by_time: dict[int, list[dict[str, Any]]] = {}
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
            for order in orders_by_time.get(timestamp, []):
                if order.get("type") == "entry":
                    if _is_pending_submission(order):
                        pending_orders.append(order)
                        continue
                    side = _normalize_direction(str(order.get("side", self.long)))
                    if not _entry_allowed(
                        side=side,
                        previous_size=current_size,
                        same_direction_entry_count=same_direction_entry_count,
                        pyramiding=self._pyramiding,
                    ):
                        continue
                    fill_side = "buy" if side == self.long else "sell"
                    fill_price = self._fill_price(float(order.get("_base_price", order.get("price", np.nan))), fill_side)
                    qty = float(order.get("qty", 0.0))
                    position_after, avg_after = _entry_position_after(
                        previous_size=current_size,
                        previous_avg=current_avg,
                        side=side,
                        qty=qty,
                        price=fill_price,
                    )
                    if current_size == 0 or (current_size > 0) != (position_after > 0):
                        same_direction_entry_count = 1
                    else:
                        same_direction_entry_count += 1
                    previous_size = current_size
                    previous_avg = current_avg
                    current_size = position_after
                    current_avg = avg_after
                    order["price"] = round(float(fill_price), 8)
                    order["position_after"] = round(float(position_after), 8)
                    commission = self._apply_commission(
                        order,
                        qty=qty,
                        price=fill_price,
                    )
                    signed_qty = qty if side == self.long else -qty
                    gross_profit, gross_loss, total_commission, open_trade = _record_fill(
                        order=order,
                        signed_qty=signed_qty,
                        previous_size=previous_size,
                        previous_avg=previous_avg,
                        previous_trade=open_trade,
                        fill_price=fill_price,
                        next_size=position_after,
                        next_avg=avg_after,
                        commission=commission,
                        closed_trades=closed_trades,
                        gross_profit=gross_profit,
                        gross_loss=gross_loss,
                        total_commission=total_commission,
                    )
                    order["_avg_price_after"] = round(float(avg_after), 8) if not is_na_value(avg_after) else None
                    order["_active"] = True
                elif order.get("type") == "order":
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
                    if position_after == 0:
                        same_direction_entry_count = 0
                    elif current_size == 0 or (current_size > 0) != (position_after > 0):
                        same_direction_entry_count = 1
                    previous_size = current_size
                    previous_avg = current_avg
                    current_size = position_after
                    current_avg = avg_after
                    order["price"] = round(float(fill_price), 8)
                    order["position_after"] = round(float(position_after), 8)
                    commission = self._apply_commission(order, qty=qty, price=fill_price)
                    signed_qty = qty if side == self.long else -qty
                    gross_profit, gross_loss, total_commission, open_trade = _record_fill(
                        order=order,
                        signed_qty=signed_qty,
                        previous_size=previous_size,
                        previous_avg=previous_avg,
                        previous_trade=open_trade,
                        fill_price=fill_price,
                        next_size=position_after,
                        next_avg=avg_after,
                        commission=commission,
                        closed_trades=closed_trades,
                        gross_profit=gross_profit,
                        gross_loss=gross_loss,
                        total_commission=total_commission,
                    )
                    order["_avg_price_after"] = round(float(avg_after), 8) if not is_na_value(avg_after) else None
                    order["_active"] = True
                elif order.get("type") in {"close", "close_all", "exit"} and current_size != 0:
                    previous_size = current_size
                    previous_avg = current_avg
                    if order.get("type") == "exit":
                        requested_qty = abs(float(order.get("qty", abs(current_size))))
                        fill_qty = min(requested_qty, abs(current_size))
                    else:
                        fill_qty = abs(current_size)
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
                    gross_profit, gross_loss, total_commission, open_trade = _record_fill(
                        order=order,
                        signed_qty=signed_qty,
                        previous_size=previous_size,
                        previous_avg=previous_avg,
                        previous_trade=open_trade,
                        fill_price=fill_price,
                        next_size=next_size,
                        next_avg=current_avg if next_size != 0 else np.nan,
                        commission=commission,
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
                    trigger = _pending_trigger(
                        side=_normalize_direction(str(order.get("side", self.long))),
                        high=high,
                        low=low,
                        limit=order.get("_limit"),
                        stop=order.get("_stop"),
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
                        ):
                            continue
                        fill_side = "buy" if side == self.long else "sell"
                        fill_price = self._fill_price(float(trigger_price), fill_side)
                        position_after, avg_after = _entry_position_after(
                            previous_size=current_size,
                            previous_avg=current_avg,
                            side=side,
                            qty=float(order.get("qty", 0.0)),
                            price=fill_price,
                        )
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
                        if position_after == 0:
                            same_direction_entry_count = 0
                        elif current_size == 0 or (current_size > 0) != (position_after > 0):
                            same_direction_entry_count = 1
                    previous_size = current_size
                    previous_avg = current_avg
                    current_size = position_after
                    current_avg = avg_after
                    order["price"] = round(float(fill_price), 8)
                    order["position_after"] = round(float(position_after), 8)
                    if order.get("_oca_name"):
                        order["oca_name"] = order.get("_oca_name")
                        order["oca_type"] = order.get("_oca_type") or StrategyOca.none
                    fill_qty = float(order.get("qty", 0.0))
                    commission = self._apply_commission(order, qty=fill_qty, price=fill_price)
                    signed_qty = fill_qty if side == self.long else -fill_qty
                    gross_profit, gross_loss, total_commission, open_trade = _record_fill(
                        order=order,
                        signed_qty=signed_qty,
                        previous_size=previous_size,
                        previous_avg=previous_avg,
                        previous_trade=open_trade,
                        fill_price=fill_price,
                        next_size=position_after,
                        next_avg=avg_after,
                        commission=commission,
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

        self._sync_strategy_report(
            closed_trades=closed_trades,
            open_trade=open_trade,
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
        open_trade: dict[str, Any] | None,
        gross_profit: float,
        gross_loss: float,
        total_commission: float,
    ) -> None:
        if not self._touched:
            return
        final_openprofit = float(self._openprofit[-1]) if len(self._openprofit) else 0.0
        final_netprofit = float(self._netprofit[-1]) if len(self._netprofit) else 0.0
        final_equity = float(self._equity[-1]) if len(self._equity) else self._initial_capital
        open_trades = []
        if open_trade is not None:
            open_trades.append({
                **open_trade,
                "profit": round(final_openprofit, 8),
            })
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
            },
            "closedtrades": closed_trades,
            "opentrades": open_trades,
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


def _is_pending_submission(order: dict[str, Any]) -> bool:
    return order.get("_limit") is not None or order.get("_stop") is not None


def _pending_trigger(
    *,
    side: str,
    high: float,
    low: float,
    limit: float | None,
    stop: float | None,
) -> tuple[str, float] | None:
    if side == StrategyModule.long:
        if stop is not None and high >= stop:
            return "stop", float(stop)
        if limit is not None and low <= limit:
            return "limit", float(limit)
        return None
    if stop is not None and low <= stop:
        return "stop", float(stop)
    if limit is not None and high >= limit:
        return "limit", float(limit)
    return None


def _entry_allowed(
    *,
    side: str,
    previous_size: float,
    same_direction_entry_count: int,
    pyramiding: int,
) -> bool:
    if previous_size == 0:
        return True
    if side == StrategyModule.long and previous_size < 0:
        return True
    if side == StrategyModule.short and previous_size > 0:
        return True
    return same_direction_entry_count < pyramiding + 1


def _normalize_commission_type(value: str) -> str:
    normalized = str(value or "").lower()
    if normalized in {"percent", "strategy.commission.percent"}:
        return StrategyCommission.percent
    if normalized in {"cash_per_order", "cash_per_order_contract", "strategy.commission.cash_per_order"}:
        return StrategyCommission.cash_per_order
    if normalized in {"cash_per_contract", "cash_per_contracts", "strategy.commission.cash_per_contract"}:
        return StrategyCommission.cash_per_contract
    return normalized


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


def _record_fill(
    *,
    order: dict[str, Any],
    signed_qty: float,
    previous_size: float,
    previous_avg: float,
    previous_trade: dict[str, Any] | None,
    fill_price: float,
    next_size: float,
    next_avg: float,
    commission: float,
    closed_trades: list[dict[str, Any]],
    gross_profit: float,
    gross_loss: float,
    total_commission: float,
) -> tuple[float, float, float, dict[str, Any] | None]:
    total_commission += commission
    realized = _realized_profit(
        previous_size=previous_size,
        previous_avg=previous_avg,
        signed_qty=signed_qty,
        fill_price=fill_price,
    )
    closed_qty = _closed_quantity(previous_size=previous_size, signed_qty=signed_qty)

    if closed_qty > 0:
        if realized >= 0:
            gross_profit += realized
        else:
            gross_loss += realized
        if previous_trade is not None:
            closed_trades.append(_closed_trade(
                previous_trade=previous_trade,
                order=order,
                qty=closed_qty,
                exit_price=fill_price,
                profit=realized,
                commission=commission,
            ))

    next_trade = _next_open_trade(
        previous_trade=previous_trade,
        order=order,
        signed_qty=signed_qty,
        previous_size=previous_size,
        fill_price=fill_price,
        next_size=next_size,
        next_avg=next_avg,
    )
    return gross_profit, gross_loss, total_commission, next_trade


def _realized_profit(
    *,
    previous_size: float,
    previous_avg: float,
    signed_qty: float,
    fill_price: float,
) -> float:
    if previous_size == 0 or signed_qty == 0 or is_na_value(previous_avg):
        return 0.0
    if (previous_size > 0) == (signed_qty > 0):
        return 0.0
    qty = min(abs(previous_size), abs(signed_qty))
    if previous_size > 0:
        return (float(fill_price) - float(previous_avg)) * qty
    return (float(previous_avg) - float(fill_price)) * qty


def _closed_quantity(*, previous_size: float, signed_qty: float) -> float:
    if previous_size == 0 or signed_qty == 0:
        return 0.0
    if (previous_size > 0) == (signed_qty > 0):
        return 0.0
    return min(abs(previous_size), abs(signed_qty))


def _next_open_trade(
    *,
    previous_trade: dict[str, Any] | None,
    order: dict[str, Any],
    signed_qty: float,
    previous_size: float,
    fill_price: float,
    next_size: float,
    next_avg: float,
) -> dict[str, Any] | None:
    if next_size == 0:
        return None

    side = "long" if next_size > 0 else "short"
    next_qty = abs(next_size)
    reversed_position = previous_size != 0 and (previous_size > 0) != (next_size > 0)
    opened_from_flat = previous_size == 0

    if previous_trade is None or opened_from_flat or reversed_position:
        return {
            "entry_time": int(order.get("time", 0)),
            "entry_id": str(order.get("id", "")),
            "side": side,
            "qty": round(next_qty, 8),
            "entry_price": round(float(fill_price), 8),
        }

    if (previous_size > 0) == (signed_qty > 0):
        return {
            **previous_trade,
            "side": side,
            "qty": round(next_qty, 8),
            "entry_price": round(float(next_avg), 8) if not is_na_value(next_avg) else previous_trade["entry_price"],
        }

    return {
        **previous_trade,
        "side": side,
        "qty": round(next_qty, 8),
    }


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
