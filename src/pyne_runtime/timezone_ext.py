"""Shared Pine-like timezone parsing helpers."""

from __future__ import annotations

import re
from datetime import UTC, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_OFFSET_PATTERN = re.compile(
    r"^(?:(?:UTC|GMT))?([+-])(\d{1,2})(?::?(\d{2}))?$",
    re.IGNORECASE,
)


def parse_timezone(
    value: str | None,
    *,
    strict: bool = False,
) -> tzinfo:
    """Parse IANA and Pine-style UTC/GMT offset timezone strings.

    Unknown host-provided timezones retain the historical UTC fallback unless
    ``strict`` is requested for an explicit script argument.
    """
    text = str(value or "UTC").strip()
    if text.upper() in {"UTC", "GMT", "Z"}:
        return UTC

    match = _OFFSET_PATTERN.fullmatch(text)
    if match is not None:
        sign_text, hour_text, minute_text = match.groups()
        hours = int(hour_text)
        minutes = int(minute_text or 0)
        if hours >= 24 or minutes >= 60:
            if strict:
                raise ValueError(f"invalid timezone offset: {text!r}")
            return UTC
        sign = 1 if sign_text == "+" else -1
        return timezone(sign * timedelta(hours=hours, minutes=minutes))

    try:
        return ZoneInfo(text)
    except ZoneInfoNotFoundError:
        if strict:
            raise ValueError(f"unknown timezone: {text!r}") from None
        return UTC
