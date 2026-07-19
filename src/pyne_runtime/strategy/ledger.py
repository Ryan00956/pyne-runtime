"""Strategy trade ledger helpers."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import numpy as np

from ..series import PyneSeries
from ..values import is_na_value

if TYPE_CHECKING:
    from .module import StrategyModule


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

    def size(self, trade_num: int = -1) -> float | PyneSeries:
        return self._trade_float(trade_num, "qty")

    def qty(self, trade_num: int = -1) -> float | PyneSeries:
        return self.size(trade_num)

    def profit(self, trade_num: int = -1) -> float | PyneSeries:
        return self._trade_float(trade_num, "profit")

    def profit_percent(self, trade_num: int = -1) -> float | PyneSeries:
        if self._strategy._process_orders_on_close:
            close_values = self._strategy._context.close.values
            values = [
                _trade_profit_percent(
                    trade,
                    close_price=close_values[idx] if self._kind == "opentrades" else None,
                )
                for idx, trade in enumerate(_trades_by_bar(self._strategy, self._kind, trade_num))
            ]
            if all(is_na_value(value) for value in values):
                return float("nan")
            return PyneSeries(
                values,
                name=f"strategy.{self._kind}.profit_percent({trade_num})",
            )
        return _trade_profit_percent(self._trade(trade_num))

    def net_profit(self, trade_num: int = -1) -> float | PyneSeries:
        return self._trade_float(trade_num, "net_profit")

    def commission(self, trade_num: int = -1) -> float | PyneSeries:
        return self._trade_float(trade_num, "commission")

    def entry_price(self, trade_num: int = -1) -> float | PyneSeries:
        return self._trade_float(trade_num, "entry_price")

    def exit_price(self, trade_num: int = -1) -> float | PyneSeries:
        return self._trade_float(trade_num, "exit_price")

    def entry_time(self, trade_num: int = -1) -> float | PyneSeries:
        return self._trade_float(trade_num, "entry_time")

    def exit_time(self, trade_num: int = -1) -> float | PyneSeries:
        return self._trade_float(trade_num, "exit_time")

    def entry_bar_index(self, trade_num: int = -1) -> float | PyneSeries:
        return self._trade_float(trade_num, "_entry_bar_index")

    def exit_bar_index(self, trade_num: int = -1) -> float | PyneSeries:
        return self._trade_float(trade_num, "_exit_bar_index")

    def entry_id(self, trade_num: int = -1) -> str:
        return str(self._trade(trade_num).get("entry_id", ""))

    def exit_id(self, trade_num: int = -1) -> str:
        return str(self._trade(trade_num).get("exit_id", ""))

    def entry_comment(self, trade_num: int = -1) -> str:
        return str(self._trade(trade_num).get("entry_comment", ""))

    def exit_comment(self, trade_num: int = -1) -> str:
        return str(self._trade(trade_num).get("exit_comment", ""))

    def side(self, trade_num: int = -1) -> str:
        return str(self._trade(trade_num).get("side", ""))

    def _trade(self, trade_num: int) -> dict[str, Any]:
        trades = (
            self._strategy._closed_trades
            if self._kind == "closedtrades"
            else self._strategy._open_trades
        )
        if not trades:
            return {"_empty_ledger": True} if int(trade_num) in {-1, 0} else {}
        index = int(trade_num)
        if index < 0:
            index = len(trades) + index
        if index < 0 or index >= len(trades):
            return {}
        return trades[index]

    def _trade_float(self, trade_num: int, key: str) -> float | PyneSeries:
        if self._strategy._process_orders_on_close:
            values = [
                _trade_float(trade, key)
                for trade in _trades_by_bar(self._strategy, self._kind, trade_num)
            ]
            if all(is_na_value(value) for value in values):
                return float("nan")
            return PyneSeries(values, name=f"strategy.{self._kind}.{key}({trade_num})")
        return _trade_float(self._trade(trade_num), key)


def _trade_float(trade: dict[str, Any], key: str) -> float:
    value = trade.get(key)
    if value is None or value == "":
        if trade.get("_empty_ledger"):
            return 0.0
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _trade_profit_percent(
    trade: dict[str, Any],
    *,
    close_price: float | None = None,
) -> float:
    if trade.get("_empty_ledger"):
        return 0.0
    qty = abs(_trade_float(trade, "qty"))
    entry_price = abs(_trade_float(trade, "entry_price"))
    denominator = qty * entry_price
    if is_na_value(denominator) or denominator <= 0:
        return float("nan")
    profit = _trade_float(trade, "profit")
    if is_na_value(profit) and close_price is not None:
        profit = _trade_open_profit(trade, float(close_price))
    if is_na_value(profit):
        return float("nan")
    return round(float(profit) / denominator * 100.0, 8)


def _trades_by_bar(
    strategy: "StrategyModule",
    kind: str,
    trade_num: int,
) -> Iterator[dict[str, Any]]:
    if kind == "closedtrades":
        for count in strategy._closedtrades_count:
            yield _closed_trade_from_count(
                strategy._closed_trades,
                int(count),
                trade_num,
            )
        return

    lot_ids: list[int] = []
    seen_lot_ids: set[int] = set()
    for events in strategy._open_trade_events_by_bar:
        for action, lot_id, _trade in events:
            if action == "upsert" and lot_id not in seen_lot_ids:
                seen_lot_ids.add(lot_id)
                lot_ids.append(lot_id)

    active_trades = _ActiveTradeIndex(lot_ids)
    for events in strategy._open_trade_events_by_bar:
        for action, lot_id, trade in events:
            if action == "upsert" and trade is not None:
                active_trades.upsert(lot_id, trade)
            elif action == "remove":
                active_trades.remove(lot_id)
        yield active_trades.trade_at(trade_num)


def _closed_trade_from_count(
    trades: list[dict[str, Any]],
    count: int,
    trade_num: int,
) -> dict[str, Any]:
    visible_count = min(max(int(count), 0), len(trades))
    if visible_count == 0:
        index = int(trade_num)
        return {"_empty_ledger": True} if index in {-1, 0, 1} else {}
    index = int(trade_num)
    if index < 0:
        index = visible_count + index
    if index < 0 or index >= visible_count:
        if index == visible_count:
            return {"_empty_ledger": True}
        return {}
    return trades[index]


class _ActiveTradeIndex:
    """Insertion-ordered active lots with O(log n) rank selection."""

    def __init__(self, lot_ids: list[int]) -> None:
        self._lot_ids = lot_ids
        self._positions = {lot_id: index for index, lot_id in enumerate(lot_ids)}
        self._tree = [0] * (len(lot_ids) + 1)
        self._active: dict[int, dict[str, Any]] = {}

    def upsert(self, lot_id: int, trade: dict[str, Any]) -> None:
        if lot_id not in self._active:
            self._add(self._positions[lot_id], 1)
        self._active[lot_id] = trade

    def remove(self, lot_id: int) -> None:
        if self._active.pop(lot_id, None) is not None:
            self._add(self._positions[lot_id], -1)

    def trade_at(self, trade_num: int) -> dict[str, Any]:
        count = len(self._active)
        if count == 0:
            index = int(trade_num)
            return {"_empty_ledger": True} if index in {-1, 0, 1} else {}
        index = int(trade_num)
        if index < 0:
            index = count + index
        if index < 0 or index >= count:
            if index == count:
                return {"_empty_ledger": True}
            return {}
        lot_position = self._position_for_rank(index)
        return self._active[self._lot_ids[lot_position]]

    def _add(self, position: int, delta: int) -> None:
        tree_index = position + 1
        while tree_index < len(self._tree):
            self._tree[tree_index] += delta
            tree_index += tree_index & -tree_index

    def _position_for_rank(self, rank: int) -> int:
        target = rank + 1
        position = 0
        step = 1 << (len(self._lot_ids).bit_length() - 1)
        while step:
            candidate = position + step
            if candidate < len(self._tree) and self._tree[candidate] < target:
                position = candidate
                target -= self._tree[candidate]
            step >>= 1
        return position


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
    open_trade_events: list[tuple[str, int, dict[str, Any] | None]] | None = None,
) -> tuple[float, float, float, list[dict[str, Any]]]:
    total_commission += commission
    if signed_qty == 0:
        return gross_profit, gross_loss, total_commission, open_trades

    remaining = abs(float(signed_qty))
    fill_qty_total = remaining
    remaining_order_commission = float(commission)
    fill_side = "long" if signed_qty > 0 else "short"
    previous_side = "long" if previous_size > 0 else "short" if previous_size < 0 else ""
    target_entry = "" if order.get("_fifo_close") else _target_entry_id(order)
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
            trade_qty_before = float(trade.get("qty", 0.0))
            entry_commission = float(trade.get("commission", 0.0))
            reported_profit = profit
            if entry_commission > 0 and close_qty < trade_qty_before:
                reported_profit -= entry_commission
            entry_commission_share = entry_commission * close_qty / max(trade_qty_before, 1e-12)
            exit_commission_share = commission * close_qty / max(fill_qty_total, 1e-12)
            remaining_order_commission -= exit_commission_share
            if profit >= 0:
                gross_profit += profit
            else:
                gross_loss += profit
            closed_trades.append(
                _closed_trade(
                    previous_trade=trade,
                    order=order,
                    qty=close_qty,
                    exit_price=fill_price,
                    profit=reported_profit,
                    commission=entry_commission_share + exit_commission_share,
                )
            )
            trade["qty"] = round(trade_qty_before - close_qty, 8)
            remaining_entry_commission = entry_commission - entry_commission_share
            if remaining_entry_commission > 0:
                trade["commission"] = round(remaining_entry_commission, 8)
            else:
                trade.pop("commission", None)
            if float(trade.get("qty", 0.0)) > 0:
                _record_open_trade_upsert(open_trade_events, trade)
            else:
                _record_open_trade_removal(open_trade_events, trade)
            remaining_to_close -= close_qty
            closed_qty_done += close_qty

        open_trades = [trade for trade in open_trades if float(trade.get("qty", 0.0)) > 0]
        remaining -= closed_qty_done

    opens_new = next_size != 0 and (not closes_existing or remaining > 0)
    if opens_new and (previous_size == 0 or fill_side == ("long" if next_size > 0 else "short")):
        if remaining <= 0 and not open_trades:
            remaining = abs(next_size)
        if remaining > 0:
            opened_trade = _open_trade_from_order(
                order=order,
                side=fill_side,
                qty=remaining,
                entry_price=fill_price,
                commission=remaining_order_commission,
            )
            open_trades.append(opened_trade)
            _record_open_trade_upsert(open_trade_events, opened_trade)

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
    commission: float = 0.0,
) -> dict[str, Any]:
    trade = {
        "_lot_id": int(order.get("_seq", 0)),
        "entry_time": int(order.get("time", 0)),
        "_entry_bar_index": int(order.get("_fill_bar_index", 0)),
        "entry_id": str(order.get("id", "")),
        "side": side,
        "qty": round(float(qty), 8),
        "entry_price": round(float(entry_price), 8),
    }
    if order.get("comment"):
        trade["entry_comment"] = str(order.get("comment", ""))
    if commission > 0:
        trade["commission"] = round(float(commission), 8)
    return trade


def _record_open_trade_upsert(
    events: list[tuple[str, int, dict[str, Any] | None]] | None,
    trade: dict[str, Any],
) -> None:
    if events is None:
        return
    lot_id = int(trade.get("_lot_id", 0))
    events.append(("upsert", lot_id, dict(trade)))


def _record_open_trade_removal(
    events: list[tuple[str, int, dict[str, Any] | None]] | None,
    trade: dict[str, Any],
) -> None:
    if events is None:
        return
    events.append(("remove", int(trade.get("_lot_id", 0)), None))


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
    trade = {
        "entry_time": previous_trade.get("entry_time"),
        "exit_time": int(order.get("time", 0)),
        "_entry_bar_index": previous_trade.get("_entry_bar_index"),
        "_exit_bar_index": int(order.get("_fill_bar_index", 0)),
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
    if previous_trade.get("entry_comment"):
        trade["entry_comment"] = str(previous_trade.get("entry_comment", ""))
    if order.get("comment"):
        trade["exit_comment"] = str(order.get("comment", ""))
    return trade


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
