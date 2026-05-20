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

RequestValues = list[Any] | tuple[list[Any], ...]

_REQUEST_SECURITY_CAPABILITIES = ("request.security", "security", "ohlcv")
_REQUEST_LOWER_TF_CAPABILITIES = ("request.security_lower_tf", "security_lower_tf", "lower_tf")


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
class LowerTimeframeSeries:
    """Array-per-chart-bar result returned by ``request.security_lower_tf()``."""

    groups: tuple[tuple[Any, ...], ...]
    name: str | None = None

    def __len__(self) -> int:
        return len(self.groups)

    def __iter__(self):
        return iter(self.groups)

    def __getitem__(self, key: int | slice) -> Any:
        if isinstance(key, slice):
            return self.groups[key]
        if not isinstance(key, (int, np.integer)):
            raise TypeError("LowerTimeframeSeries indices must be a non-negative bars-back integer")
        if key < 0:
            raise IndexError("LowerTimeframeSeries does not support forward history references")
        return self.shift(int(key))

    def to_lists(self) -> list[list[Any]]:
        return [list(group) for group in self.groups]

    def shift(self, periods: int = 1) -> "LowerTimeframeSeries":
        periods = int(periods)
        if periods <= 0:
            return self
        empty: tuple[Any, ...] = ()
        groups = [empty] * len(self.groups)
        if periods < len(self.groups):
            groups[periods:] = self.groups[: len(self.groups) - periods]
        return LowerTimeframeSeries(tuple(groups), name=f"{self.name}[{periods}]" if self.name else None)

    def size(self) -> PyneSeries:
        return _lower_tf_numeric_series(
            [len(group) for group in self.groups],
            name=f"{self.name}.size" if self.name else None,
        )

    def first(self, default: Any = np.nan) -> PyneSeries:
        return self._edge(0, default=default, label="first")

    def last(self, default: Any = np.nan) -> PyneSeries:
        return self._edge(-1, default=default, label="last")

    def get(self, index: int, default: Any = np.nan) -> PyneSeries:
        """Return the value at ``index`` from each chart bar's lower-TF group."""
        index = int(index)
        if index < 0:
            raise IndexError("LowerTimeframeSeries.get() requires a non-negative index")
        values = [group[index] if index < len(group) else default for group in self.groups]
        return _lower_tf_numeric_series(
            values,
            name=f"{self.name}.get" if self.name else None,
        )

    def sum(self, default: Any = np.nan) -> PyneSeries:
        return self._aggregate(np.sum, default=default, label="sum")

    def min(self, default: Any = np.nan) -> PyneSeries:
        return self._aggregate(np.min, default=default, label="min")

    def max(self, default: Any = np.nan) -> PyneSeries:
        return self._aggregate(np.max, default=default, label="max")

    def avg(self, default: Any = np.nan) -> PyneSeries:
        return self._aggregate(np.mean, default=default, label="avg")

    def _edge(self, index: int, *, default: Any, label: str) -> PyneSeries:
        values = [group[index] if group else default for group in self.groups]
        return _lower_tf_numeric_series(
            values,
            name=f"{self.name}.{label}" if self.name else None,
        )

    def _aggregate(
        self,
        op: Callable[[np.ndarray], Any],
        *,
        default: Any,
        label: str,
    ) -> PyneSeries:
        values: list[Any] = []
        for group in self.groups:
            clean = np.asarray(
                [float(value) for value in group if not is_na_value(value)],
                dtype=np.float64,
            )
            values.append(default if len(clean) == 0 else op(clean))
        return _lower_tf_numeric_series(
            values,
            name=f"{self.name}.{label}" if self.name else None,
        )


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
    def time_close(self) -> PyneSeries:
        return self.context.time_close

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
    def syminfo(self) -> Any:
        return self.context.syminfo

    @property
    def timeframe_info(self) -> Any:
        return self.context.timeframe

    @property
    def session(self) -> Any:
        return self.context.session

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
        expression: PyneSeries | str | tuple[Any, ...] | list[Any] | Callable[[RequestEvalContext], Any],
        *,
        gaps: str = "off",
        lookahead: str = "off",
    ) -> PyneSeries | tuple[PyneSeries, ...]:
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
        if not _provider_supports(self._provider, _REQUEST_SECURITY_CAPABILITIES):
            raise PyneRequestError(
                "request.security() requires provider capability 'request.security'",
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
        requested_ctx = PyneContext.from_ohlcv(
            requested,
            syminfo={"tickerid": str(symbol), "ticker": str(symbol)},
            timeframe=str(timeframe),
        )
        requested_times = requested_ctx.times
        if callable(expression):
            requested_values, expression_name = self._evaluate_expression_thunk(
                expression,
                symbol=str(symbol),
                timeframe=str(timeframe),
                requested_ctx=requested_ctx,
            )
        else:
            requested_values, expression_name = _values_from_field_expression(
                expression,
                requested,
                requested_ctx,
            )

        return _align_request_values(
            symbol=str(symbol),
            timeframe=str(timeframe),
            expression_name=expression_name,
            chart_times=self._context.times,
            requested_times=requested_times,
            requested_values=requested_values,
            gaps=gaps,
            lookahead=lookahead,
        )

    def security_lower_tf(
        self,
        symbol: str,
        timeframe: str,
        expression: PyneSeries | str | tuple[Any, ...] | list[Any] | Callable[[RequestEvalContext], Any],
    ) -> LowerTimeframeSeries | tuple[LowerTimeframeSeries, ...]:
        """Return lower-timeframe arrays grouped by chart bar.

        The provider supplies lower-timeframe OHLCV. Pyne evaluates the
        expression in that requested context, then groups requested values into
        ``[chart_time, next_chart_time)`` buckets.
        """
        if self._provider is None:
            raise PyneRequestError(
                "request.security_lower_tf() requires a host data provider",
                code="PYNE_UNSUPPORTED_FEATURE",
            )
        if not _provider_supports(self._provider, _REQUEST_LOWER_TF_CAPABILITIES):
            raise PyneRequestError(
                "request.security_lower_tf() requires provider capability 'request.security_lower_tf'",
                code="PYNE_UNSUPPORTED_FEATURE",
            )
        if self._evaluating:
            raise PyneRequestError(
                "Nested request.security_lower_tf() expressions are not supported",
                code="PYNE_UNSUPPORTED_FEATURE",
            )

        start, end = self._context.times[0], self._context.times[-1]
        requested = self._provider.get_ohlcv(str(symbol), str(timeframe), start, end)
        requested = sorted(requested, key=lambda item: int(item.get("time", 0)))
        requested_ctx = PyneContext.from_ohlcv(
            requested,
            syminfo={"tickerid": str(symbol), "ticker": str(symbol)},
            timeframe=str(timeframe),
        )
        if callable(expression):
            requested_values, expression_name = self._evaluate_expression_thunk(
                expression,
                symbol=str(symbol),
                timeframe=str(timeframe),
                requested_ctx=requested_ctx,
            )
        else:
            requested_values, expression_name = _values_from_field_expression(
                expression,
                requested,
                requested_ctx,
            )

        return _group_lower_timeframe_values(
            symbol=str(symbol),
            timeframe=str(timeframe),
            expression_name=expression_name,
            chart_times=self._context.times,
            requested_times=requested_ctx.times,
            requested_values=requested_values,
        )

    def _evaluate_expression_thunk(
        self,
        expression: Callable[[RequestEvalContext], Any],
        *,
        symbol: str,
        timeframe: str,
        requested_ctx: PyneContext,
    ) -> tuple[RequestValues, str]:
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
    if field not in {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "time",
        "time_close",
        "hl2",
        "hlc3",
        "ohlc4",
        "hlcc4",
    }:
        raise PyneRequestError(
            f"request.security() does not support expression field '{field}'",
            code="PYNE_UNSUPPORTED_FEATURE",
        )
    return field, offset


def _values_from_field_expression(
    expression: PyneSeries | str | tuple[Any, ...] | list[Any],
    requested: list[dict[str, Any]],
    requested_ctx: PyneContext,
) -> tuple[RequestValues, str]:
    if isinstance(expression, tuple | list):
        values = []
        names = []
        for item in expression:
            field, history_offset = _resolve_requested_field(item)
            values.append(_apply_history_offset(
                _field_values(requested, requested_ctx, field),
                history_offset,
            ))
            names.append(field if history_offset <= 0 else f"{field}[{history_offset}]")
        if not values:
            raise PyneRequestError(
                "request.security() multi-return expression cannot be empty",
                code="PYNE_UNSUPPORTED_FEATURE",
            )
        return tuple(values), ",".join(names)

    field, history_offset = _resolve_requested_field(expression)
    values = _apply_history_offset(
        _field_values(requested, requested_ctx, field),
        history_offset,
    )
    expression_name = field if history_offset <= 0 else f"{field}[{history_offset}]"
    return values, expression_name


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


def _values_from_expression_result(result: Any, requested_ctx: PyneContext) -> RequestValues:
    length = requested_ctx.bar_count
    if isinstance(result, tuple):
        if not result:
            raise PyneRequestError(
                "request.security() expression cannot return an empty tuple",
                code="PYNE_UNSUPPORTED_FEATURE",
            )
        return tuple(_values_from_expression_result(item, requested_ctx) for item in result)

    if isinstance(result, PyneSeries):
        values = result.to_numpy().tolist()
    elif isinstance(result, np.ndarray):
        values = result.tolist()
    elif isinstance(result, list):
        values = result
    elif isinstance(result, dict) or result is None:
        raise PyneRequestError(
            "request.security() expression must return a series, tuple of series, or scalar value",
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


def _align_request_values(
    *,
    symbol: str,
    timeframe: str,
    expression_name: str,
    chart_times: list[int],
    requested_times: list[int],
    requested_values: RequestValues,
    gaps: str,
    lookahead: str,
) -> PyneSeries | tuple[PyneSeries, ...]:
    if isinstance(requested_values, tuple):
        return tuple(
            _align_single_request_values(
                symbol=symbol,
                timeframe=timeframe,
                expression_name=f"{expression_name}[{index}]",
                chart_times=chart_times,
                requested_times=requested_times,
                requested_values=values,
                gaps=gaps,
                lookahead=lookahead,
            )
            for index, values in enumerate(requested_values)
        )

    return _align_single_request_values(
        symbol=symbol,
        timeframe=timeframe,
        expression_name=expression_name,
        chart_times=chart_times,
        requested_times=requested_times,
        requested_values=requested_values,
        gaps=gaps,
        lookahead=lookahead,
    )


def _group_lower_timeframe_values(
    *,
    symbol: str,
    timeframe: str,
    expression_name: str,
    chart_times: list[int],
    requested_times: list[int],
    requested_values: RequestValues,
) -> LowerTimeframeSeries | tuple[LowerTimeframeSeries, ...]:
    if isinstance(requested_values, tuple):
        return tuple(
            _group_single_lower_timeframe_values(
                symbol=symbol,
                timeframe=timeframe,
                expression_name=f"{expression_name}[{index}]",
                chart_times=chart_times,
                requested_times=requested_times,
                requested_values=values,
            )
            for index, values in enumerate(requested_values)
        )
    return _group_single_lower_timeframe_values(
        symbol=symbol,
        timeframe=timeframe,
        expression_name=expression_name,
        chart_times=chart_times,
        requested_times=requested_times,
        requested_values=requested_values,
    )


def _group_single_lower_timeframe_values(
    *,
    symbol: str,
    timeframe: str,
    expression_name: str,
    chart_times: list[int],
    requested_times: list[int],
    requested_values: list[Any],
) -> LowerTimeframeSeries:
    groups: list[tuple[Any, ...]] = []
    for index, chart_time in enumerate(chart_times):
        next_time = chart_times[index + 1] if index + 1 < len(chart_times) else None
        start = bisect_left(requested_times, chart_time)
        end = len(requested_times) if next_time is None else bisect_left(requested_times, next_time)
        groups.append(tuple(
            np.nan if is_na_value(value) else value
            for value in requested_values[start:end]
        ))
    return LowerTimeframeSeries(
        tuple(groups),
        name=f"request.security_lower_tf({symbol},{timeframe},{expression_name})",
    )


def _lower_tf_numeric_series(values: list[Any], *, name: str | None = None) -> PyneSeries:
    return PyneSeries(
        np.asarray(
            [np.nan if is_na_value(value) else float(value) for value in values],
            dtype=np.float64,
        ),
        name=name,
    )


def _align_single_request_values(
    *,
    symbol: str,
    timeframe: str,
    expression_name: str,
    chart_times: list[int],
    requested_times: list[int],
    requested_values: list[Any],
    gaps: str,
    lookahead: str,
) -> PyneSeries:
    values = [
        _aligned_value(
            chart_time,
            requested_times,
            requested_values,
            gaps=gaps,
            lookahead=lookahead,
        )
        for chart_time in chart_times
    ]
    return PyneSeries(
        np.asarray(values, dtype=np.float64),
        name=f"request.security({symbol},{timeframe},{expression_name})",
    )


def _field_values(requested: list[dict[str, Any]], requested_ctx: PyneContext, field: str) -> list[float]:
    context_fields = {
        "open": requested_ctx.open,
        "high": requested_ctx.high,
        "low": requested_ctx.low,
        "close": requested_ctx.close,
        "volume": requested_ctx.volume,
        "time": requested_ctx.time,
        "time_close": requested_ctx.time_close,
        "hl2": requested_ctx.hl2,
        "hlc3": requested_ctx.hlc3,
        "ohlc4": requested_ctx.ohlc4,
        "hlcc4": requested_ctx.hlcc4,
    }
    series = context_fields.get(field)
    if series is not None:
        return series.to_numpy().tolist()
    return [_field_value(bar, field) for bar in requested]


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


def _provider_supports(provider: DataProvider, capability_names: tuple[str, ...]) -> bool:
    declared_capabilities = getattr(provider, "capabilities", None)
    if callable(declared_capabilities):
        declared_capabilities = declared_capabilities()
    if declared_capabilities is None:
        return True
    if isinstance(declared_capabilities, dict):
        for capability in capability_names:
            if capability in declared_capabilities:
                return bool(declared_capabilities[capability])
        return True
    if isinstance(declared_capabilities, (set, list, tuple)):
        declared = set(declared_capabilities)
        return any(capability in declared for capability in capability_names)
    return bool(declared_capabilities)
