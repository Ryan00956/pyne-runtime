"""Host-backed data request helpers for Pine-like multi-context series."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Any, Callable, Protocol

import numpy as np

from .context import PyneContext
from .series import PyneSeries
from .series import switch as series_switch
from .series import when as series_when
from .series import where as series_where
from .ta import TaModule
from .values import is_na_value


class DataProvider(Protocol):
    """Host interface used by ``request.security()``.

    Pyne defines alignment semantics, but the host owns market data retrieval.
    """

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> list[dict[str, Any]]:
        """Return OHLCV bars for ``symbol`` and ``timeframe`` in ``[start, end]``."""


class PyneRequestError(Exception):
    """Stable runtime error raised by host-backed request helpers."""

    def __init__(self, message: str, *, code: str = "PYNE_UNSUPPORTED_FEATURE") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RequestEvalContext:
    """Calculation-only context passed to request expression thunks."""

    symbol: str
    timeframe: str
    context: PyneContext
    ta: TaModule

    @property
    def open(self) -> PyneSeries:
        return self.context.open

    @property
    def high(self) -> PyneSeries:
        return self.context.high

    @property
    def low(self) -> PyneSeries:
        return self.context.low

    @property
    def close(self) -> PyneSeries:
        return self.context.close

    @property
    def volume(self) -> PyneSeries:
        return self.context.volume

    @property
    def time(self) -> PyneSeries:
        return self.context.time

    @property
    def bar_index(self) -> PyneSeries:
        return self.context.bar_index

    @property
    def last_bar_index(self) -> PyneSeries:
        return self.context.last_bar_index

    @property
    def barstate(self) -> Any:
        return self.context.barstate

    @property
    def hl2(self) -> PyneSeries:
        return self.context.hl2

    @property
    def hlc3(self) -> PyneSeries:
        return self.context.hlc3

    @property
    def ohlc4(self) -> PyneSeries:
        return self.context.ohlc4

    @property
    def hlcc4(self) -> PyneSeries:
        return self.context.hlcc4

    def when(self, condition: Any, true_value: Any, false_value: Any) -> Any:
        return series_when(condition, true_value, false_value)

    def where(self, condition: Any, true_value: Any, false_value: Any) -> Any:
        return series_where(condition, true_value, false_value)

    def switch(self, *cases: Any, default: Any = np.nan) -> Any:
        return series_switch(*cases, default=default)


class RequestModule:
    """Pine-like ``request`` namespace bound to one execution context."""

    def __init__(
        self,
        context: PyneContext,
        provider: DataProvider | None = None,
    ) -> None:
        self._context = context
        self._provider = provider
        self._evaluating = False

    def security(
        self,
        symbol: str,
        timeframe: str,
        expression: PyneSeries | str | Callable[[RequestEvalContext], Any],
        *,
        gaps: str = "off",
        lookahead: str = "off",
    ) -> PyneSeries:
        """Return a requested symbol/timeframe field aligned to chart bars.

        Field-like expressions such as ``close``, ``close[1]``, or ``"close"``
        remain supported. Callable thunks are evaluated in the requested
        symbol/timeframe context.
        """
        if self._provider is None:
            raise PyneRequestError(
                "request.security() requires a host data provider",
                code="PYNE_UNSUPPORTED_FEATURE",
            )
        if self._evaluating:
            raise PyneRequestError(
                "Nested request.security() expressions are not supported",
                code="PYNE_UNSUPPORTED_FEATURE",
            )

        start, end = self._context.times[0], self._context.times[-1]
        requested = self._provider.get_ohlcv(str(symbol), str(timeframe), start, end)
        if not requested:
            return PyneSeries(
                np.full(self._context.bar_count, np.nan, dtype=np.float64),
                name=f"request.security({symbol},{timeframe})",
            )

        requested = sorted(requested, key=lambda item: int(item.get("time", 0)))
        requested_ctx = PyneContext.from_ohlcv(requested)
        requested_times = requested_ctx.times
        if callable(expression):
            requested_values, expression_name = self._evaluate_expression_thunk(
                expression,
                symbol=str(symbol),
                timeframe=str(timeframe),
                requested_ctx=requested_ctx,
            )
        else:
            field, history_offset = _resolve_requested_field(expression)
            requested_values = _apply_history_offset(
                [_field_value(item, field) for item in requested],
                history_offset,
            )
            expression_name = field
        values = [
            _aligned_value(
                chart_time,
                requested_times,
                requested_values,
                gaps=gaps,
                lookahead=lookahead,
            )
            for chart_time in self._context.times
        ]
        return PyneSeries(
            np.asarray(values, dtype=np.float64),
            name=f"request.security({symbol},{timeframe},{expression_name})",
        )

    def _evaluate_expression_thunk(
        self,
        expression: Callable[[RequestEvalContext], Any],
        *,
        symbol: str,
        timeframe: str,
        requested_ctx: PyneContext,
    ) -> tuple[list[Any], str]:
        requested_ta = TaModule(requested_ctx)
        eval_ctx = RequestEvalContext(
            symbol=symbol,
            timeframe=timeframe,
            context=requested_ctx,
            ta=requested_ta,
        )
        try:
            self._evaluating = True
            result = expression(eval_ctx)
        except PyneRequestError:
            raise
        except Exception as exc:
            raise PyneRequestError(
                f"request.security() expression failed: {exc}",
                code="PYNE_RUNTIME_ERROR",
            ) from exc
        finally:
            self._evaluating = False

        return _values_from_expression_result(result, requested_ctx), "expression"


def _resolve_requested_field(expression: PyneSeries | str) -> tuple[str, int]:
    if isinstance(expression, str):
        name = expression
    elif isinstance(expression, PyneSeries) and expression.name:
        name = expression.name
    else:
        raise PyneRequestError(
            "request.security() currently supports OHLCV field expressions only",
            code="PYNE_UNSUPPORTED_FEATURE",
        )

    field, offset = _split_history_name(name)
    if field not in {"open", "high", "low", "close", "volume", "hl2", "hlc3", "ohlc4", "hlcc4"}:
        raise PyneRequestError(
            f"request.security() does not support expression field '{field}'",
            code="PYNE_UNSUPPORTED_FEATURE",
        )
    return field, offset


def _split_history_name(name: str) -> tuple[str, int]:
    if "[" not in name:
        return name, 0
    field, raw_offset = name.split("[", 1)
    try:
        return field, int(raw_offset.rstrip("]"))
    except ValueError:
        return field, 0


def _apply_history_offset(values: list[float], offset: int) -> list[float]:
    if offset <= 0:
        return values
    shifted = [np.nan] * len(values)
    if offset < len(values):
        shifted[offset:] = values[: len(values) - offset]
    return shifted


def _values_from_expression_result(result: Any, requested_ctx: PyneContext) -> list[Any]:
    length = requested_ctx.bar_count
    if isinstance(result, PyneSeries):
        values = result.to_numpy().tolist()
    elif isinstance(result, np.ndarray):
        values = result.tolist()
    elif isinstance(result, list):
        values = result
    elif isinstance(result, tuple | dict) or result is None:
        raise PyneRequestError(
            "request.security() expression must return a single series or scalar value",
            code="PYNE_UNSUPPORTED_FEATURE",
        )
    elif isinstance(result, bool | int | float | np.generic):
        values = [result] * length
    else:
        raise PyneRequestError(
            f"request.security() expression returned unsupported type {type(result).__name__}",
            code="PYNE_UNSUPPORTED_FEATURE",
        )

    if len(values) != length:
        raise PyneRequestError(
            "request.security() expression result length must match requested OHLCV length",
            code="PYNE_RUNTIME_ERROR",
        )
    return [np.nan if is_na_value(item) else item for item in values]


def _field_value(bar: dict[str, Any], field: str) -> float:
    if field == "hl2":
        return (float(bar.get("high", np.nan)) + float(bar.get("low", np.nan))) / 2
    if field == "hlc3":
        return (
            float(bar.get("high", np.nan))
            + float(bar.get("low", np.nan))
            + float(bar.get("close", np.nan))
        ) / 3
    if field == "ohlc4":
        return (
            float(bar.get("open", np.nan))
            + float(bar.get("high", np.nan))
            + float(bar.get("low", np.nan))
            + float(bar.get("close", np.nan))
        ) / 4
    if field == "hlcc4":
        return (
            float(bar.get("high", np.nan))
            + float(bar.get("low", np.nan))
            + float(bar.get("close", np.nan))
            + float(bar.get("close", np.nan))
        ) / 4
    return float(bar.get(field, np.nan))


def _aligned_value(
    chart_time: int,
    requested_times: list[int],
    requested_values: list[float],
    *,
    gaps: str,
    lookahead: str,
) -> float:
    normalized_gaps = str(gaps or "off").lower()
    normalized_lookahead = str(lookahead or "off").lower()

    if normalized_gaps in {"on", "gaps_on"}:
        idx = bisect_left(requested_times, chart_time)
        if idx < len(requested_times) and requested_times[idx] == chart_time:
            value = requested_values[idx]
            return np.nan if is_na_value(value) else float(value)
        return np.nan

    if normalized_lookahead in {"on", "lookahead_on"}:
        idx = bisect_left(requested_times, chart_time)
    else:
        idx = bisect_right(requested_times, chart_time) - 1

    if idx < 0 or idx >= len(requested_values):
        return np.nan
    value = requested_values[idx]
    return np.nan if is_na_value(value) else float(value)
