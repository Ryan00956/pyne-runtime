"""Strategy trade ledger helpers."""
from __future__ import annotations

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
            return {"_empty_ledger": True} if int(trade_num) in {-1, 0} else {}
        index = int(trade_num)
        if index < 0:
            index = len(trades) + index
        if index < 0 or index >= len(trades):
            return {}
        return trades[index]

    def _trade_float(self, trade_num: int, key: str) -> float | PyneSeries:
        snapshots = (
            self._strategy._closed_trades_by_bar
            if self._kind == "closedtrades"
            else self._strategy._open_trades_by_bar
        )
        if self._strategy._process_orders_on_close and snapshots:
            values = [
                _trade_float(_trade_from_snapshot(trades, trade_num), key)
                for trades in snapshots
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


def _trade_from_snapshot(trades: list[dict[str, Any]], trade_num: int) -> dict[str, Any]:
    if not trades:
        return {"_empty_ledger": True} if int(trade_num) in {-1, 0} else {}
    index = int(trade_num)
    if index < 0:
        index = len(trades) + index
    if index < 0 or index >= len(trades):
        return {}
    return trades[index]


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
    fill_qty_total = remaining
    remaining_order_commission = float(commission)
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
            trade_qty_before = float(trade.get("qty", 0.0))
            entry_commission = float(trade.get("commission", 0.0))
            entry_commission_share = (
                entry_commission * close_qty / max(trade_qty_before, 1e-12)
            )
            exit_commission_share = (
                commission
                * close_qty
                / max(fill_qty_total, 1e-12)
            )
            remaining_order_commission -= exit_commission_share
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
                commission=entry_commission_share + exit_commission_share,
            ))
            trade["qty"] = round(trade_qty_before - close_qty, 8)
            remaining_entry_commission = entry_commission - entry_commission_share
            if remaining_entry_commission > 0:
                trade["commission"] = round(remaining_entry_commission, 8)
            else:
                trade.pop("commission", None)
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
                commission=remaining_order_commission,
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
    commission: float = 0.0,
) -> dict[str, Any]:
    trade = {
        "entry_time": int(order.get("time", 0)),
        "entry_id": str(order.get("id", "")),
        "side": side,
        "qty": round(float(qty), 8),
        "entry_price": round(float(entry_price), 8),
    }
    if commission > 0:
        trade["commission"] = round(float(commission), 8)
    return trade


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
