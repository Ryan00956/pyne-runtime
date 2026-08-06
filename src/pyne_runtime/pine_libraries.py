"""Pinned adapters for external Pine libraries that Pyne implements explicitly."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .context import PyneContext
from .metadata import _timeframe_bucket, normalize_timeframe_info
from .request import LowerTimeframeSeries, PyneRequestError, RequestModule
from .series import PyneSeries
from .values import is_na_value


TRADINGVIEW_TA_10 = "TradingView/ta/10"


@dataclass(frozen=True)
class PineLibraryDescriptor:
    """Machine-readable declaration for one pinned, locally implemented library."""

    identifier: str
    members: tuple[str, ...]
    data_requirements: tuple[str, ...]
    member_data_requirements: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def requirements_for(self, members: set[str] | tuple[str, ...]) -> tuple[str, ...]:
        """Return the host capabilities required by the selected members."""
        selected = set(members)
        requirements = {
            requirement
            for member, member_requirements in self.member_data_requirements
            if member in selected
            for requirement in member_requirements
        }
        return tuple(sorted(requirements))


SUPPORTED_PINE_LIBRARIES = (
    PineLibraryDescriptor(
        identifier=TRADINGVIEW_TA_10,
        members=(
            "atr2",
            "cagr",
            "changePercent",
            "ema2",
            "highestSince",
            "lowestSince",
            "requestUpAndDownVolume",
            "requestVolumeDelta",
            "rma2",
        ),
        data_requirements=("request.security_lower_tf",),
        member_data_requirements=(
            ("requestUpAndDownVolume", ("request.security_lower_tf",)),
            ("requestVolumeDelta", ("request.security_lower_tf",)),
        ),
    ),
)


class TradingViewTa10Library:
    """The project-used subset of TradingView's public ``ta`` library v10."""

    def __init__(self, ctx: PyneContext, request: RequestModule) -> None:
        self._ctx = ctx
        self._request = request

    def ema2(self, src: Any, length: Any) -> PyneSeries:
        """Return an EMA whose smoothing length may vary on every bar."""
        values = _library_series(src, len(self._ctx.times))
        lengths = _library_series(length, len(self._ctx.times))
        result = _dynamic_average(values, lengths, alpha_numerator=2.0, ema_style=True)
        return PyneSeries(result, name="ta10.ema2")

    def rma2(self, source: Any, length: Any) -> PyneSeries:
        """Return an RMA whose smoothing length may vary on every bar."""
        values = _library_series(source, len(self._ctx.times))
        lengths = _library_series(length, len(self._ctx.times))
        result = _dynamic_average(values, lengths, alpha_numerator=1.0, ema_style=False)
        return PyneSeries(result, name="ta10.rma2")

    def atr2(self, length: Any) -> PyneSeries:
        """Return ATR using a per-bar RMA smoothing length."""
        size = len(self._ctx.times)
        lengths = _library_series(length, size)
        highs = np.asarray(self._ctx.high.values, dtype=np.float64)
        lows = np.asarray(self._ctx.low.values, dtype=np.float64)
        closes = np.asarray(self._ctx.close.values, dtype=np.float64)
        ranges = np.full(size, np.nan, dtype=np.float64)
        for index in range(size):
            if not np.isfinite(highs[index]) or not np.isfinite(lows[index]):
                continue
            values = [highs[index] - lows[index]]
            if index > 0 and np.isfinite(closes[index - 1]):
                values.extend(
                    (
                        abs(highs[index] - closes[index - 1]),
                        abs(lows[index] - closes[index - 1]),
                    )
                )
            ranges[index] = max(values)
        result = _dynamic_average(ranges, lengths, alpha_numerator=1.0, ema_style=False)
        return PyneSeries(result, name="ta10.atr2")

    def requestUpAndDownVolume(
        self,
        lowerTimeframe: str,
    ) -> tuple[PyneSeries, PyneSeries, PyneSeries]:
        """Return up volume, negative down volume, and their delta per chart bar.

        This v10 adapter deliberately uses host-provided lower-timeframe OHLCV.
        It never estimates intrabars from the chart bars.
        """
        requested = self._request_intrabar_ohlcv(lowerTimeframe)
        up_values: list[float] = []
        down_values: list[float] = []
        delta_values: list[float] = []
        previous_close: float | None = None
        for opens, closes, volumes in zip(
            requested[0].groups,
            requested[1].groups,
            requested[2].groups,
        ):
            up = 0.0
            down = 0.0
            seen = False
            for direction, volume, close_value in _polarized_intrabar_volumes(
                opens,
                closes,
                volumes,
                previous_close=previous_close,
            ):
                seen = True
                previous_close = close_value
                if direction > 0:
                    up += volume
                elif direction < 0:
                    down -= volume
            if not seen:
                up_values.append(np.nan)
                down_values.append(np.nan)
                delta_values.append(np.nan)
            else:
                up_values.append(up)
                down_values.append(down)
                delta_values.append(up + down)
        return (
            PyneSeries(np.asarray(up_values), name="ta10.upVolume"),
            PyneSeries(np.asarray(down_values), name="ta10.downVolume"),
            PyneSeries(np.asarray(delta_values), name="ta10.volumeDelta"),
        )

    request_up_and_down_volume = requestUpAndDownVolume

    def requestVolumeDelta(
        self,
        lowerTimeframe: str,
        cumulativePeriod: str,
    ) -> tuple[PyneSeries, PyneSeries, PyneSeries, PyneSeries]:
        """Return opening, high, low, and current CVD for each chart bar."""
        requested = self._request_intrabar_ohlcv(lowerTimeframe)
        period_text = str(cumulativePeriod or self._ctx.timeframe.period)
        period = normalize_timeframe_info(period_text)
        timezone_name = self._ctx.syminfo.timezone or "UTC"
        opening_values: list[float] = []
        high_values: list[float] = []
        low_values: list[float] = []
        current_values: list[float] = []
        active_bucket: int | None = None
        current = 0.0
        period_high = 0.0
        period_low = 0.0
        previous_close: float | None = None

        for chart_time, opens, closes, volumes in zip(
            self._ctx.times,
            requested[0].groups,
            requested[1].groups,
            requested[2].groups,
        ):
            bucket = _timeframe_bucket(int(chart_time), period, timezone_name)
            if bucket != active_bucket:
                active_bucket = bucket
                current = 0.0
                period_high = 0.0
                period_low = 0.0
            opening = current
            seen = False
            for direction, volume, close_value in _polarized_intrabar_volumes(
                opens,
                closes,
                volumes,
                previous_close=previous_close,
            ):
                seen = True
                previous_close = close_value
                current += volume if direction > 0 else -volume if direction < 0 else 0.0
                period_high = max(period_high, current)
                period_low = min(period_low, current)
            if not seen:
                opening_values.append(np.nan)
                high_values.append(np.nan)
                low_values.append(np.nan)
                current_values.append(np.nan)
            else:
                opening_values.append(opening)
                high_values.append(period_high)
                low_values.append(period_low)
                current_values.append(current)
        series = tuple(
            PyneSeries(np.asarray(values, dtype=np.float64), name=name)
            for values, name in (
                (opening_values, "ta10.cvdOpen"),
                (high_values, "ta10.cvdHigh"),
                (low_values, "ta10.cvdLow"),
                (current_values, "ta10.cvd"),
            )
        )
        return series[0], series[1], series[2], series[3]

    request_volume_delta = requestVolumeDelta

    def changePercent(self, newValue: Any, oldValue: Any) -> PyneSeries:
        new_values = _library_series(newValue, len(self._ctx.times))
        old_values = _library_series(oldValue, len(self._ctx.times))
        with np.errstate(divide="ignore", invalid="ignore"):
            result = np.where(
                old_values != 0.0,
                (new_values - old_values) / old_values * 100.0,
                np.nan,
            )
        return PyneSeries(result, name="ta10.changePercent")

    change_percent = changePercent

    def cagr(
        self,
        entryTime: Any,
        entryPrice: Any,
        exitTime: Any,
        exitPrice: Any,
    ) -> PyneSeries:
        size = len(self._ctx.times)
        starts = _library_series(entryTime, size)
        start_prices = _library_series(entryPrice, size)
        ends = _library_series(exitTime, size)
        end_prices = _library_series(exitPrice, size)
        elapsed = ends - starts
        milliseconds = np.maximum(np.abs(starts), np.abs(ends)) > 10_000_000_000
        elapsed_seconds = np.where(milliseconds, elapsed / 1_000.0, elapsed)
        years = elapsed_seconds / (365.0 * 86_400.0)
        chart_times = np.asarray(self._ctx.times, dtype=np.float64)
        chart_time_milliseconds = np.abs(chart_times) > 10_000_000_000
        comparable_chart_times = np.where(
            milliseconds & ~chart_time_milliseconds,
            chart_times * 1_000.0,
            np.where(~milliseconds & chart_time_milliseconds, chart_times / 1_000.0, chart_times),
        )
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            result = np.where(
                (elapsed_seconds >= 86_400.0)
                & (start_prices > 0.0)
                & (end_prices > 0.0)
                & (comparable_chart_times >= ends),
                (np.power(end_prices / start_prices, 1.0 / years) - 1.0) * 100.0,
                np.nan,
            )
        return PyneSeries(result, name="ta10.cagr")

    def highestSince(self, cond: Any, source: Any = None) -> PyneSeries:
        values = (
            self._ctx.high.values
            if source is None
            else _library_series(source, len(self._ctx.times))
        )
        return PyneSeries(_since_extreme(cond, values, highest=True), name="ta10.highestSince")

    highest_since = highestSince

    def lowestSince(self, cond: Any, source: Any = None) -> PyneSeries:
        values = (
            self._ctx.low.values
            if source is None
            else _library_series(source, len(self._ctx.times))
        )
        return PyneSeries(_since_extreme(cond, values, highest=False), name="ta10.lowestSince")

    lowest_since = lowestSince

    def _request_intrabar_ohlcv(
        self,
        lower_timeframe: str,
    ) -> tuple[LowerTimeframeSeries, LowerTimeframeSeries, LowerTimeframeSeries]:
        symbol = self._ctx.syminfo.tickerid or self._ctx.syminfo.ticker
        if not symbol:
            raise PyneRequestError(
                "TradingView/ta/10 requires syminfo.tickerid for lower-timeframe data",
                code="PYNE_INVALID_INPUT",
            )
        requested = self._request.security_lower_tf(
            symbol,
            str(lower_timeframe),
            lambda requested_ctx: (
                requested_ctx.open,
                requested_ctx.close,
                requested_ctx.volume,
            ),
        )
        if not isinstance(requested, tuple) or len(requested) != 3 or not all(
            isinstance(item, LowerTimeframeSeries) for item in requested
        ):
            raise PyneRequestError(
                "TradingView/ta/10 received an invalid lower-timeframe result",
                code="PYNE_RUNTIME_ERROR",
            )
        return requested


class PineLibraryRegistry:
    """Execution-bound allowlist for external Pine library adapters."""

    def __init__(self, ctx: PyneContext, request: RequestModule) -> None:
        self._ctx = ctx
        self._request = request

    def load(self, identifier: str) -> Any:
        normalized = str(identifier).strip()
        if normalized == TRADINGVIEW_TA_10:
            return TradingViewTa10Library(self._ctx, self._request)
        raise PyneRequestError(
            f"External Pine library '{normalized}' is not implemented by this runtime",
            code="PYNE_UNSUPPORTED_FEATURE",
        )

    def supported(self) -> list[dict[str, Any]]:
        return [
            {
                "identifier": item.identifier,
                "members": list(item.members),
                "dataRequirements": list(item.data_requirements),
                "memberDataRequirements": {
                    member: list(requirements)
                    for member, requirements in item.member_data_requirements
                },
            }
            for item in SUPPORTED_PINE_LIBRARIES
        ]

    __call__ = load


def _polarized_intrabar_volumes(
    opens: Any,
    closes: Any,
    volumes: Any,
    *,
    previous_close: float | None,
) -> list[tuple[int, float, float]]:
    result: list[tuple[int, float, float]] = []
    prior = previous_close
    for open_value, close_value, volume_value in zip(opens, closes, volumes):
        if any(is_na_value(value) for value in (open_value, close_value, volume_value)):
            continue
        open_number = float(open_value)
        close_number = float(close_value)
        volume = abs(float(volume_value))
        if close_number > open_number:
            direction = 1
        elif close_number < open_number:
            direction = -1
        elif prior is None or close_number >= prior:
            direction = 1
        else:
            direction = -1
        result.append((direction, volume, close_number))
        prior = close_number
    return result


def _library_series(value: Any, size: int) -> np.ndarray:
    if isinstance(value, PyneSeries):
        values = np.asarray(value.values, dtype=np.float64)
    elif np.isscalar(value):
        values = np.full(size, float(value), dtype=np.float64)
    else:
        values = np.asarray(value, dtype=np.float64)
    if len(values) != size:
        raise ValueError(f"TradingView/ta/10 expected {size} values, got {len(values)}")
    return values


def _dynamic_average(
    source: np.ndarray,
    lengths: np.ndarray,
    *,
    alpha_numerator: float,
    ema_style: bool,
) -> np.ndarray:
    """Evaluate TradingView library-style dynamic EMA/RMA smoothing."""
    result = np.full(len(source), np.nan, dtype=np.float64)
    previous = np.nan
    for index, (value, length) in enumerate(zip(source, lengths)):
        if not np.isfinite(length) or length <= 0.0:
            previous = np.nan
            continue
        if not np.isfinite(value):
            result[index] = previous
            continue
        if np.isnan(previous):
            # TradingView's public ta library seeds both dynamic recursive
            # averages from the first valid source value. This deliberately
            # differs from native ta.rma(), whose fixed-length seed is an SMA.
            previous = float(value)
        else:
            denominator = length + 1.0 if ema_style else length
            alpha = min(max(alpha_numerator / denominator, 0.0), 1.0)
            previous = alpha * float(value) + (1.0 - alpha) * previous
        result[index] = previous
    return result


def _since_extreme(cond: Any, source: Any, *, highest: bool) -> np.ndarray:
    values = np.asarray(source, dtype=np.float64)
    raw_conditions = _library_series(cond, len(values))
    conditions = np.isfinite(raw_conditions) & (raw_conditions != 0.0)
    if len(conditions) != len(values):
        raise ValueError("TradingView/ta/10 condition and source lengths must match")
    result = np.full(len(values), np.nan)
    current = np.nan
    for index, value in enumerate(values):
        if np.isnan(value):
            result[index] = current
            continue
        if conditions[index] or np.isnan(current):
            current = value
        elif highest:
            current = max(current, value)
        else:
            current = min(current, value)
        result[index] = current
    return result
