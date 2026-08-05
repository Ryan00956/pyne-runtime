"""Pine-like time helper namespace."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, tzinfo
from numbers import Integral
from typing import Any

import numpy as np

from .metadata import TimeframeInfo
from .series import PyneSeries
from .timezone_ext import parse_timezone
from .values import is_na_value


class TimeNamespace(PyneSeries):
    """Time series with Pine-like ``time.*`` helper methods."""

    sunday = 1
    monday = 2
    tuesday = 3
    wednesday = 4
    thursday = 5
    friday = 6
    saturday = 7

    def __call__(
        self,
        timeframe: str | TimeframeInfo | None = "",
        session: str | int | None = None,
        timezone: str | int | None = None,
        bars_back: int = 0,
        timeframe_bars_back: int = 0,
    ) -> PyneSeries:
        """Return Pine-like bar opening times, optionally filtered by a session."""
        session, timezone, bars_back, timeframe_bars_back = _normalize_time_arguments(
            session,
            timezone,
            bars_back,
            timeframe_bars_back,
        )
        chart_timeframe = getattr(self, "_chart_timeframe", TimeframeInfo())
        requested = (
            chart_timeframe
            if timeframe is None or timeframe == ""
            else TimeframeInfo.from_value(timeframe)
        )
        timezone_name = str(
            timezone if timezone not in {None, ""} else getattr(self, "_default_timezone", "UTC")
        )
        zone = parse_timezone(
            timezone_name,
            strict=timezone not in {None, ""},
        )
        source_times = _offset_chart_times(
            self.to_numpy(),
            chart_timeframe,
            bars_back,
            zone,
        )
        same_timeframe = _same_timeframe(chart_timeframe, requested)
        session_text = str(session or "").strip()
        values: list[float] = []
        for source_time in source_times:
            if is_na_value(source_time):
                values.append(np.nan)
                continue
            timestamp = (
                int(float(source_time))
                if same_timeframe
                else _timeframe_open(float(source_time), requested, zone)
            )
            if timeframe_bars_back:
                timestamp = int(
                    _advance_timeframe(
                        timestamp,
                        requested,
                        -timeframe_bars_back,
                        zone,
                    )
                )
            if session_text and not _session_contains(timestamp, session_text, zone):
                values.append(np.nan)
            else:
                values.append(float(timestamp))
        return PyneSeries(
            np.asarray(values, dtype=np.float64),
            name=f"time({requested.period})",
        )

    def year(
        self,
        source: Any = None,
        timezone: str | None = None,
    ) -> PyneSeries | int | None:
        return _component(self._source(source), self._timezone_name(timezone), lambda dt: dt.year)

    def month(
        self,
        source: Any = None,
        timezone: str | None = None,
    ) -> PyneSeries | int | None:
        return _component(self._source(source), self._timezone_name(timezone), lambda dt: dt.month)

    def dayofmonth(
        self,
        source: Any = None,
        timezone: str | None = None,
    ) -> PyneSeries | int | None:
        return _component(self._source(source), self._timezone_name(timezone), lambda dt: dt.day)

    def dayofweek(
        self,
        source: Any = None,
        timezone: str | None = None,
    ) -> PyneSeries | int | None:
        return _component(self._source(source), self._timezone_name(timezone), _pine_dayofweek)

    def hour(
        self,
        source: Any = None,
        timezone: str | None = None,
    ) -> PyneSeries | int | None:
        return _component(self._source(source), self._timezone_name(timezone), lambda dt: dt.hour)

    def minute(
        self,
        source: Any = None,
        timezone: str | None = None,
    ) -> PyneSeries | int | None:
        return _component(self._source(source), self._timezone_name(timezone), lambda dt: dt.minute)

    def second(
        self,
        source: Any = None,
        timezone: str | None = None,
    ) -> PyneSeries | int | None:
        return _component(self._source(source), self._timezone_name(timezone), lambda dt: dt.second)

    def timestamp(self, *args: Any, timezone: str | None = None) -> int:
        if args and isinstance(args[0], str):
            timezone = args[0]
            args = args[1:]
        elif len(args) == 7 and isinstance(args[-1], str):
            timezone = args[-1]
            args = args[:-1]
        if not 3 <= len(args) <= 6:
            raise TypeError(
                "time.timestamp() expects year, month, day, optional hour/minute/second"
            )
        year, month, day, *rest = args
        hour, minute, second = (*rest, 0, 0, 0)[:3]
        tz = parse_timezone(self._timezone_name(timezone), strict=timezone is not None)
        value = datetime(
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second),
            tzinfo=tz,
        )
        return int(value.timestamp())

    def format(
        self,
        source: Any = None,
        fmt: str = "%Y-%m-%d %H:%M:%S",
        timezone: str | None = None,
    ) -> str:
        value = _latest_scalar(self._source(source))
        if is_na_value(value):
            return "na"
        return _datetime(value, self._timezone_name(timezone)).strftime(fmt)

    def _source(self, source: Any = None) -> Any:
        return self if source is None else source

    def _timezone_name(self, timezone: str | None) -> str:
        if timezone is not None and str(timezone).strip():
            return str(timezone)
        return str(getattr(self, "_default_timezone", "UTC") or "UTC")


def time_namespace(
    series: PyneSeries,
    *,
    timeframe: str | TimeframeInfo | None = None,
    timezone: str = "UTC",
) -> TimeNamespace:
    value = TimeNamespace(series.to_numpy(), name=series.name)
    object.__setattr__(value, "_chart_timeframe", TimeframeInfo.from_value(timeframe))
    object.__setattr__(value, "_default_timezone", str(timezone or "UTC"))
    return value


def dayofweek_namespace(series: PyneSeries, timezone: str = "UTC") -> TimeNamespace:
    """Return the Pine-like global ``dayofweek`` series and enum namespace."""
    values = time_namespace(series, timezone=timezone).dayofweek()
    result = TimeNamespace(np.asarray(values), name="dayofweek")
    object.__setattr__(result, "_default_timezone", str(timezone or "UTC"))
    return result


def _component(source: Any, tz_name: str, getter: Any) -> PyneSeries | int | None:
    if isinstance(source, PyneSeries):
        values = []
        for item in source.to_numpy():
            if is_na_value(item):
                values.append(np.nan)
            else:
                values.append(float(getter(_datetime(item, tz_name))))
        return PyneSeries(np.array(values, dtype=np.float64), name=source.name)
    if is_na_value(source):
        return None
    return int(getter(_datetime(source, tz_name)))


def _latest_scalar(source: Any) -> Any:
    if isinstance(source, PyneSeries):
        values = source.to_numpy().tolist()
    elif isinstance(source, np.ndarray):
        values = source.tolist()
    elif isinstance(source, list | tuple):
        values = list(source)
    else:
        return source
    for item in reversed(values):
        if not is_na_value(item):
            return item
    return None


def _datetime(timestamp: Any, tz_name: str) -> datetime:
    seconds = _timestamp_seconds(timestamp)
    return datetime.fromtimestamp(seconds, tz=parse_timezone(tz_name))


def _timestamp_seconds(timestamp: Any) -> float:
    value = float(timestamp)
    if abs(value) > 100_000_000_000:
        return value / 1000.0
    return value


def _pine_dayofweek(value: datetime) -> int:
    # Python Monday=0; Pine dayofweek.sunday=1 ... saturday=7.
    return ((value.weekday() + 1) % 7) + 1


def _normalize_time_arguments(
    session: str | int | None,
    timezone: str | int | None,
    bars_back: int,
    timeframe_bars_back: int,
) -> tuple[str | None, str | None, int, int]:
    if _is_integer(session):
        if timezone is not None or bars_back != 0 or timeframe_bars_back != 0:
            raise TypeError("time(timeframe, bars_back) cannot include duplicate offset arguments")
        bars_back = int(session)
        session = None
    elif _is_integer(timezone):
        if bars_back != 0:
            if timeframe_bars_back != 0:
                raise TypeError("time(..., timeframe_bars_back) has duplicate offset arguments")
            timeframe_bars_back = bars_back
        bars_back = int(timezone)
        timezone = None
    normalized_bars_back = _normalize_bar_offset("bars_back", bars_back)
    normalized_timeframe_bars_back = _normalize_bar_offset(
        "timeframe_bars_back",
        timeframe_bars_back,
    )
    if session is not None and not isinstance(session, str):
        raise TypeError("time() session must be a string")
    if timezone is not None and not isinstance(timezone, str):
        raise TypeError("time() timezone must be a string")
    return (
        session,
        timezone,
        normalized_bars_back,
        normalized_timeframe_bars_back,
    )


def _normalize_bar_offset(name: str, value: Any) -> int:
    if not _is_integer(value):
        raise TypeError(f"time() {name} must be an integer")
    normalized = int(value)
    if normalized < -500 or normalized > 5000:
        raise ValueError(f"time() {name} must be between -500 and 5000")
    return normalized


def _is_integer(value: Any) -> bool:
    return isinstance(value, Integral) and not isinstance(value, bool)


def _offset_chart_times(
    values: np.ndarray,
    chart_timeframe: TimeframeInfo,
    bars_back: int,
    zone: tzinfo,
) -> np.ndarray:
    source = np.asarray(values, dtype=np.float64)
    if bars_back == 0:
        return source.copy()
    result = np.full(len(source), np.nan, dtype=np.float64)
    if bars_back > 0:
        if bars_back < len(source):
            result[bars_back:] = source[: len(source) - bars_back]
        return result
    steps = -bars_back
    for index, timestamp in enumerate(source):
        if not is_na_value(timestamp):
            result[index] = _advance_timeframe(float(timestamp), chart_timeframe, steps, zone)
    return result


def _advance_timeframe(
    timestamp: float,
    timeframe: TimeframeInfo,
    steps: int,
    zone: tzinfo,
) -> float:
    if timeframe.isticks:
        return np.nan
    local = datetime.fromtimestamp(_timestamp_seconds(timestamp), tz=zone)
    amount = max(int(timeframe.multiplier), 1) * steps
    if timeframe.unit == "M":
        month_index = local.year * 12 + local.month - 1 + amount
        year, month_zero = divmod(month_index, 12)
        try:
            shifted = local.replace(year=year, month=month_zero + 1)
        except ValueError:
            shifted = local.replace(year=year, month=month_zero + 1, day=1)
        return float(int(shifted.timestamp()))
    if timeframe.unit == "W":
        shifted = local + timedelta(weeks=amount)
        return float(int(shifted.timestamp()))
    if timeframe.unit == "D":
        shifted = local + timedelta(days=amount)
        return float(int(shifted.timestamp()))
    duration = amount if timeframe.unit == "S" else amount * 60
    return float(int(timestamp) + duration)


def _same_timeframe(left: TimeframeInfo, right: TimeframeInfo) -> bool:
    return left.unit == right.unit and int(left.multiplier) == int(right.multiplier)


def _timeframe_open(
    timestamp: float,
    timeframe: TimeframeInfo,
    zone: tzinfo,
) -> int:
    if timeframe.isticks:
        raise ValueError("time() cannot derive a tick-timeframe opening timestamp")
    local = datetime.fromtimestamp(_timestamp_seconds(timestamp), tz=zone)
    amount = max(int(timeframe.multiplier), 1)
    if timeframe.unit == "M":
        month_index = local.year * 12 + local.month - 1
        start_index = (month_index // amount) * amount
        year, month_zero = divmod(start_index, 12)
        return int(datetime(year, month_zero + 1, 1, tzinfo=zone).timestamp())

    ordinal_zero = local.date().toordinal() - 1
    if timeframe.unit == "W":
        start_ordinal = (ordinal_zero // (7 * amount)) * (7 * amount)
        return int(
            datetime.combine(
                date.fromordinal(start_ordinal + 1), datetime.min.time(), zone
            ).timestamp()
        )
    if timeframe.unit == "D":
        start_ordinal = (ordinal_zero // amount) * amount
        return int(
            datetime.combine(
                date.fromordinal(start_ordinal + 1), datetime.min.time(), zone
            ).timestamp()
        )

    local_seconds = ordinal_zero * 86_400 + local.hour * 3_600 + local.minute * 60 + local.second
    duration = amount if timeframe.unit == "S" else amount * 60
    start_seconds = (local_seconds // duration) * duration
    start_ordinal, seconds_in_day = divmod(start_seconds, 86_400)
    start_date = date.fromordinal(start_ordinal + 1)
    start_local = datetime.combine(start_date, datetime.min.time(), zone) + timedelta(
        seconds=seconds_in_day
    )
    return int(start_local.timestamp())


_SESSION_PERIOD_PATTERN = re.compile(r"^(\d{4})-(\d{4})$")


def _session_contains(timestamp: int, session: str, zone: tzinfo) -> bool:
    periods, days = _parse_session(session)
    local = datetime.fromtimestamp(_timestamp_seconds(timestamp), tz=zone)
    minute = local.hour * 60 + local.minute
    for start, end in periods:
        if start < end:
            if start <= minute < end and _pine_dayofweek(local) in days:
                return True
            continue

        in_period = start == end or minute >= start or minute < end
        if not in_period:
            continue
        effective = local + timedelta(days=1) if minute >= start else local
        if _pine_dayofweek(effective) in days:
            return True
    return False


def _parse_session(session: str) -> tuple[list[tuple[int, int]], set[int]]:
    text = str(session).strip()
    if text.lower() in {"24x7", "24/7"}:
        text = "0000-0000:1234567"
    body, separator, days_text = text.partition(":")
    if separator and ":" in days_text:
        raise ValueError(f"invalid session string: {session!r}")
    days_raw = days_text or "1234567"
    if not days_raw or any(char not in "1234567" for char in days_raw):
        raise ValueError(f"invalid session days: {session!r}")
    periods: list[tuple[int, int]] = []
    for item in body.split(","):
        match = _SESSION_PERIOD_PATTERN.fullmatch(item.strip())
        if match is None:
            raise ValueError(f"invalid session period: {session!r}")
        periods.append((_session_minute(match.group(1)), _session_minute(match.group(2))))
    if not periods:
        raise ValueError(f"invalid session string: {session!r}")
    return periods, {int(char) for char in days_raw}


def _session_minute(value: str) -> int:
    hours = int(value[:2])
    minutes = int(value[2:])
    if hours == 24 and minutes == 0:
        return 1_440
    if hours >= 24 or minutes >= 60:
        raise ValueError(f"invalid session time: {value!r}")
    return hours * 60 + minutes
