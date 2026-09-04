from __future__ import annotations

import pyne_runtime as pn


def _flat_bars(times: list[int]) -> list[dict[str, float]]:
    return [
        {
            "time": timestamp,
            "open": 1,
            "high": 2,
            "low": 1,
            "close": 1.5,
            "volume": 100,
        }
        for timestamp in times
    ]


def _bars() -> list[dict[str, float]]:
    return [
        {
            "time": 1704164645,  # 2024-01-02 03:04:05 UTC, Tuesday
            "open": 1,
            "high": 2,
            "low": 1,
            "close": 1.5,
            "volume": 100,
        },
        {
            "time": 1704254706,  # 2024-01-03 04:05:06 UTC, Wednesday
            "open": 2,
            "high": 3,
            "low": 1,
            "close": 2.5,
            "volume": 120,
        },
    ]


def test_time_namespace_preserves_series_history_and_adds_components() -> None:
    result = pn.run(
        """
plot(time[1], "Previous Time")
plot(time.year(), "Year")
plot(time.month(), "Month")
plot(time.dayofmonth(), "Day")
plot(time.dayofweek(), "Day Of Week")
plot(time.hour(), "Hour")
plot(time.minute(), "Minute")
plot(time.second(), "Second")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Previous Time") == [1704164645.0]
    assert result.values("Year") == [2024.0, 2024.0]
    assert result.values("Month") == [1.0, 1.0]
    assert result.values("Day") == [2.0, 3.0]
    assert result.values("Day Of Week") == [3.0, 4.0]
    assert result.values("Hour") == [3.0, 4.0]
    assert result.values("Minute") == [4.0, 5.0]
    assert result.values("Second") == [5.0, 6.0]


def test_global_dayofweek_is_both_a_series_and_enum_namespace() -> None:
    result = pn.run(
        """
plot(dayofweek, "Day Of Week")
plot(dayofweek == dayofweek.tuesday, "Tuesday")
plot(dayofweek == dayofweek.wednesday, "Wednesday")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Day Of Week") == [3.0, 4.0]
    assert result.values("Tuesday") == [1.0, 0.0]
    assert result.values("Wednesday") == [0.0, 1.0]


def test_global_dayofweek_uses_symbol_timezone_when_host_supplies_it() -> None:
    result = pn.run(
        """
plot(dayofweek, "Day Of Week")
plot(dayofweek == dayofweek.tuesday, "Tuesday")
""",
        [
            {
                "time": 1704132000,  # 2024-01-01 18:00 UTC; Tuesday at UTC+08:00.
                "open": 1,
                "high": 2,
                "low": 1,
                "close": 1.5,
                "volume": 100,
            }
        ],
        settings=pn.PyneSettings(syminfo={"timezone": "+08:00"}),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Day Of Week") == [3.0]
    assert result.values("Tuesday") == [1.0]


def test_time_callable_filters_session_in_explicit_timezone() -> None:
    start = 1704153600  # 2024-01-02 00:00 UTC; 08:00 at UTC+08:00.
    times = [
        start + 30 * 60,
        start + 60 * 60,
        start + 2 * 60 * 60,
        start + 2 * 60 * 60 + 30 * 60,
    ]
    result = pn.run(
        """
in_session = time("", "0900-1030:3", "+08:00")
previous = time("", "0900-1030:3", "+08:00", bars_back=1)
plot(nz(in_session, -1), "In Session")
plot(nz(previous, -1), "Previous")
""",
        _flat_bars(times),
        settings=pn.PyneSettings(
            syminfo={"timezone": "UTC"},
            timeframe="30",
        ),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("In Session") == [-1.0, float(times[1]), float(times[2]), -1.0]
    assert result.values("Previous") == [-1.0, -1.0, float(times[1]), float(times[2])]


def test_time_callable_maps_higher_timeframe_and_chart_bar_offsets() -> None:
    start = 1704153600  # 2024-01-02 00:00 UTC.
    times = [
        start + 15 * 60,
        start + 59 * 60,
        start + 60 * 60,
        start + 90 * 60,
    ]
    result = pn.run(
        """
plot(time("60"), "Hour Open")
plot(nz(time("", 1), -1), "Previous Bar")
plot(time("", -2), "Two Bars Ahead")
""",
        _flat_bars(times),
        settings=pn.PyneSettings(
            syminfo={"timezone": "UTC"},
            timeframe="1",
        ),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Hour Open") == [
        float(start),
        float(start),
        float(start + 3_600),
        float(start + 3_600),
    ]
    assert result.values("Previous Bar") == [
        -1.0,
        float(times[0]),
        float(times[1]),
        float(times[2]),
    ]
    assert result.values("Two Bars Ahead") == [float(value + 120) for value in times]


def test_time_callable_applies_chart_and_requested_timeframe_offsets_in_order() -> None:
    start = 1704067200  # 2024-01-01 00:00:00 UTC
    times = [
        start,
        start + 30 * 60,
        start + 60 * 60,
        start + 90 * 60,
    ]
    result = pn.run(
        """
plot(nz(time("60", bars_back=1, timeframe_bars_back=2), -1), "Named")
plot(nz(time("60", "", 1, 2), -1), "Short Positional")
plot(nz(time("60", "", "UTC", 1, -1), -1), "Full Positional")
""",
        _flat_bars(times),
        settings=pn.PyneSettings(
            syminfo={"timezone": "UTC"},
            timeframe="30",
        ),
        executor_mode="inline",
    )

    assert result.ok, result.error
    expected_past = [
        -1.0,
        float(start - 2 * 3_600),
        float(start - 2 * 3_600),
        float(start - 3_600),
    ]
    assert result.values("Named") == expected_past
    assert result.values("Short Positional") == expected_past
    assert result.values("Full Positional") == [
        -1.0,
        float(start + 3_600),
        float(start + 3_600),
        float(start + 2 * 3_600),
    ]


def test_time_callable_understands_overnight_session_days_and_utc_offsets() -> None:
    times = [
        1704668400,  # Sunday 23:00 UTC, part of Monday's overnight session.
        1704675600,  # Monday 01:00 UTC.
        1704682800,  # Monday 03:00 UTC.
    ]
    result = pn.run(
        """
overnight = time("", "2200-0200:2", "UTC")
plot(nz(overnight, -1), "Overnight")
plot(time.hour(time, "UTC-5"), "UTC Minus Five")
""",
        _flat_bars(times),
        settings=pn.PyneSettings(
            syminfo={"timezone": "UTC"},
            timeframe="60",
        ),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Overnight") == [float(times[0]), float(times[1]), -1.0]
    assert result.values("UTC Minus Five") == [18.0, 20.0, 22.0]


def test_time_callable_rejects_invalid_explicit_session_and_offset() -> None:
    invalid_session = pn.run(
        'plot(time("", "2500-2600"), "Invalid")',
        _bars(),
        executor_mode="inline",
    )
    invalid_offset = pn.run(
        'plot(time("", bars_back=-501), "Invalid")',
        _bars(),
        executor_mode="inline",
    )
    invalid_timeframe_offset = pn.run(
        'plot(time("", timeframe_bars_back=5001), "Invalid")',
        _bars(),
        executor_mode="inline",
    )

    assert not invalid_session.ok
    assert "invalid session time" in (invalid_session.error or "")
    assert not invalid_offset.ok
    assert "between -500 and 5000" in (invalid_offset.error or "")
    assert not invalid_timeframe_offset.ok
    assert "timeframe_bars_back" in (invalid_timeframe_offset.error or "")


def test_time_helpers_accept_explicit_source_and_timezone() -> None:
    result = pn.run(
        """
stamp = time.timestamp(2024, 1, 2, 3, 4, 5)
shifted = time.timestamp(2024, 1, 2, 11, 4, 5, timezone="+08:00")
label(time.format(stamp, "%Y-%m-%d %H:%M:%S"))
label(time.format(stamp, "%H:%M", timezone="+08:00"))

plot(stamp, "Timestamp")
plot(shifted, "Shifted")
plot(time.hour(stamp, "+08:00"), "Shanghai Hour")
plot(1 if time.dayofweek(stamp) == time.tuesday else 0, "Constant Match")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert [item["text"] for item in result.output["labels"]] == [
        "2024-01-02 03:04:05",
        "11:04",
    ]
    assert result.values("Timestamp") == [1704164645.0, 1704164645.0]
    assert result.values("Shifted") == [1704164645.0, 1704164645.0]
    assert result.values("Shanghai Hour") == [11.0, 11.0]
    assert result.values("Constant Match") == [1.0, 1.0]


def test_time_timestamp_accepts_timezone_first_pine_like_order() -> None:
    result = pn.run(
        """
keyword = time.timestamp(2024, 1, 2, 11, 4, 5, timezone="+08:00")
positional = time.timestamp("+08:00", 2024, 1, 2, 11, 4, 5)
legacy_positional = time.timestamp(2024, 1, 2, 11, 4, 5, "+08:00")
date_only = time.timestamp("UTC", 2024, 1, 2)
plot(keyword, "Keyword")
plot(positional, "Positional")
plot(legacy_positional, "Legacy Positional")
plot(date_only, "Date Only")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Keyword") == [1704164645.0, 1704164645.0]
    assert result.values("Positional") == [1704164645.0, 1704164645.0]
    assert result.values("Legacy Positional") == [1704164645.0, 1704164645.0]
    assert result.values("Date Only") == [1704153600.0, 1704153600.0]


def test_time_components_accept_millisecond_timestamps() -> None:
    result = pn.run(
        """
plot(time.year(1704164645000), "Year")
plot(time.second(1704164645000), "Second")
label(time.format(1704164645000, "%Y-%m-%d"))
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Year") == [2024.0, 2024.0]
    assert result.values("Second") == [5.0, 5.0]
    assert result.output["labels"][0]["text"] == "2024-01-02"
