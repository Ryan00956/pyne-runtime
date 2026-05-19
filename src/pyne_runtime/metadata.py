"""Pine-like runtime metadata namespaces."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class SymbolInfo:
    """Symbol metadata exposed as the Pine-like ``syminfo`` namespace."""

    ticker: str = ""
    tickerid: str = ""
    prefix: str = ""
    currency: str = ""
    basecurrency: str = ""
    mintick: float = 1.0
    pointvalue: float = 1.0
    type: str = ""

    @classmethod
    def from_value(cls, value: Any = None) -> "SymbolInfo":
        if isinstance(value, SymbolInfo):
            return value
        if value is None:
            return cls()
        if isinstance(value, str):
            return _symbol_from_mapping({"tickerid": value})
        if isinstance(value, Mapping):
            return _symbol_from_mapping(value)
        return cls()


@dataclass(frozen=True)
class TimeframeInfo:
    """Chart timeframe metadata exposed as ``timeframe``."""

    period: str = "1"
    multiplier: int = 1
    isintraday: bool = True
    isdaily: bool = False
    isweekly: bool = False
    ismonthly: bool = False

    @classmethod
    def from_value(cls, value: Any = None) -> "TimeframeInfo":
        if isinstance(value, TimeframeInfo):
            return value
        if value is None:
            return cls()
        if isinstance(value, Mapping):
            period = str(value.get("period") or value.get("timeframe") or "1").strip() or "1"
            parsed = _parse_timeframe(period)
            multiplier = value.get("multiplier")
            if multiplier is not None:
                try:
                    parsed = cls(
                        period=parsed.period,
                        multiplier=max(int(multiplier), 1),
                        isintraday=parsed.isintraday,
                        isdaily=parsed.isdaily,
                        isweekly=parsed.isweekly,
                        ismonthly=parsed.ismonthly,
                    )
                except (TypeError, ValueError):
                    pass
            return parsed
        return _parse_timeframe(str(value).strip() or "1")


@dataclass(frozen=True)
class SessionInfo:
    """Lightweight session metadata exposed as ``session``."""

    ismarket: bool = True
    isfirstbar: bool = False
    islastbar: bool = False

    @classmethod
    def from_value(cls, value: Any = None) -> "SessionInfo":
        if isinstance(value, SessionInfo):
            return value
        if value is None:
            return cls()
        if isinstance(value, bool):
            return cls(ismarket=value)
        if isinstance(value, Mapping):
            return cls(
                ismarket=bool(value.get("ismarket", True)),
                isfirstbar=bool(value.get("isfirstbar", False)),
                islastbar=bool(value.get("islastbar", False)),
            )
        return cls()


def normalize_symbol_info(value: Any = None) -> SymbolInfo:
    return SymbolInfo.from_value(value)


def normalize_timeframe_info(value: Any = None) -> TimeframeInfo:
    return TimeframeInfo.from_value(value)


def normalize_session_info(value: Any = None) -> SessionInfo:
    return SessionInfo.from_value(value)


def _symbol_from_mapping(value: Mapping[str, Any]) -> SymbolInfo:
    tickerid = str(value.get("tickerid") or value.get("symbol") or "").strip()
    ticker = str(value.get("ticker") or "").strip()
    prefix = str(value.get("prefix") or "").strip()

    if tickerid and ":" in tickerid:
        inferred_prefix, inferred_ticker = tickerid.split(":", 1)
        prefix = prefix or inferred_prefix
        ticker = ticker or inferred_ticker
    elif tickerid:
        ticker = ticker or tickerid
    elif ticker:
        tickerid = ticker

    return SymbolInfo(
        ticker=ticker,
        tickerid=tickerid,
        prefix=prefix,
        currency=str(value.get("currency") or "").strip(),
        basecurrency=str(value.get("basecurrency") or value.get("base_currency") or "").strip(),
        mintick=_positive_float(value.get("mintick", value.get("min_tick", 1.0)), 1.0),
        pointvalue=_positive_float(value.get("pointvalue", value.get("point_value", 1.0)), 1.0),
        type=str(value.get("type") or "").strip(),
    )


def _positive_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return number


def _parse_timeframe(period: str) -> TimeframeInfo:
    raw = period.strip() or "1"
    match = re.fullmatch(r"(\d+)?([A-Za-z]?)", raw)
    if match is None:
        return TimeframeInfo(period=raw, multiplier=1)

    number_text, suffix = match.groups()
    amount = int(number_text) if number_text else 1
    amount = max(amount, 1)

    if not suffix:
        return TimeframeInfo(period=raw, multiplier=amount, isintraday=True)

    if suffix in {"s", "S", "m"}:
        return TimeframeInfo(period=raw, multiplier=amount, isintraday=True)
    if suffix in {"h", "H"}:
        return TimeframeInfo(period=raw, multiplier=amount * 60, isintraday=True)
    if suffix in {"d", "D"}:
        return TimeframeInfo(
            period=raw,
            multiplier=amount,
            isintraday=False,
            isdaily=True,
        )
    if suffix in {"w", "W"}:
        return TimeframeInfo(
            period=raw,
            multiplier=amount,
            isintraday=False,
            isweekly=True,
        )
    if suffix == "M":
        return TimeframeInfo(
            period=raw,
            multiplier=amount,
            isintraday=False,
            ismonthly=True,
        )
    return TimeframeInfo(period=raw, multiplier=amount)
