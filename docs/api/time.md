# Time API

Pyne exposes the chart `time` series as a Pine-like object. It still behaves as
a series, so history references such as `time[1]` continue to work, and it also
provides helper methods under the same `time.*` surface.

```python
plot(time[1], "Previous Time")
plot(time.year(), "Year")
plot(time.hour(time, "+08:00"), "Hour In UTC+8")
```

Pyne accepts timestamp values in seconds. Millisecond timestamps are detected
when the absolute value is larger than `100_000_000_000`.

## Callable Time Series

The same `time` object is callable:

```python
hour_open = time("60")
inside = time("", "0930-1600:23456", "America/New_York")
previous = time("", bars_back=1)
prior_daily = time("1D", bars_back=2, timeframe_bars_back=1)
```

Its full Python signature is:

```python
time(
    timeframe="",
    session=None,
    timezone=None,
    bars_back=0,
    timeframe_bars_back=0,
)
```

- An empty timeframe uses the script/chart timeframe.
- Session strings accept one or more `HHMM-HHMM` periods and an optional Pine
  day suffix, where `1` is Sunday and `7` is Saturday. Overnight periods use
  the ending day's day number.
- The session timezone defaults to `syminfo.timezone`, then UTC when the host
  does not provide one.
- `bars_back` offsets the main chart timeline first.
  `timeframe_bars_back` then offsets the requested timeframe. Both accept
  `-500..5000`; negative values calculate expected future times.

Current-timeframe calls preserve the exact host bar opens. Higher-timeframe
opens use deterministic calendar boundaries in the configured symbol timezone.
This matches CandleScope's 24/7 crypto timeline, but it does not reconstruct
exchange-session-specific higher-timeframe opens from sparse bars. A host that
needs authoritative non-24/7 boundaries must supply aligned market metadata or
requested data rather than relying on ticker-name inference.

## Components

- `time.year(source=None, timezone="UTC")`
- `time.month(source=None, timezone="UTC")`
- `time.dayofmonth(source=None, timezone="UTC")`
- `time.dayofweek(source=None, timezone="UTC")`
- `time.hour(source=None, timezone="UTC")`
- `time.minute(source=None, timezone="UTC")`
- `time.second(source=None, timezone="UTC")`

When `source` is omitted, helpers use the chart `time` series. When `source` is
a series, helpers return a `PyneSeries`. When `source` is a scalar timestamp,
helpers return a scalar value.

`time.dayofweek()` follows Pine-style constants:

- `time.sunday`
- `time.monday`
- `time.tuesday`
- `time.wednesday`
- `time.thursday`
- `time.friday`
- `time.saturday`

The global `dayofweek` name is also a series with the same constants, so
`dayofweek == dayofweek.monday` produces a series condition.

## Timeframe Helpers

The runtime-bound `timeframe` namespace exposes:

- `timeframe.in_seconds(value=None)`
- `timeframe.from_seconds(seconds)`
- `timeframe.change(value=None)`
- `timeframe.isseconds`, `timeframe.isminutes`, `timeframe.isticks`,
  `timeframe.isintraday`, `timeframe.isdaily`, `timeframe.isweekly`,
  `timeframe.ismonthly`, and `timeframe.isdwm`

`timeframe.change()` returns a boolean series marking the first available bar
and each later boundary. Calendar boundaries use `syminfo.timezone` when the
host supplies it and UTC otherwise.

## Construction And Formatting

- `time.timestamp(year, month, day, hour=0, minute=0, second=0, timezone="UTC")`
- `time.timestamp(timezone, year, month, day, hour=0, minute=0, second=0)`
- `time.format(source=None, fmt="%Y-%m-%d %H:%M:%S", timezone="UTC")`

`timezone` accepts `"UTC"` / `"GMT"`, fixed offsets such as `"+08:00"` and
`"UTC-5"`, and IANA zone names supported by Python's `zoneinfo`, such as
`"America/New_York"`.

```python
stamp = time.timestamp(2024, 1, 2, 3, 4, 5)
shifted = time.timestamp("+08:00", 2024, 1, 2, 11, 4, 5)
label(time.format(stamp, "%Y-%m-%d %H:%M:%S"))
```
