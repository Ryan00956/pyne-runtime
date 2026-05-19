from __future__ import annotations

from typing import Any

import pyne_runtime as pn


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 1, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100},
        {"time": 2, "open": 2, "high": 3, "low": 1.5, "close": 2.5, "volume": 120},
        {"time": 3, "open": 3, "high": 4, "low": 2.5, "close": 3.5, "volume": 140},
        {"time": 4, "open": 4, "high": 5, "low": 3.5, "close": 4.5, "volume": 160},
    ]


class StaticProvider:
    def __init__(self, bars: list[dict[str, Any]]) -> None:
        self.calls: list[tuple[str, str, int, int]] = []
        self._bars = bars

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> list[dict[str, Any]]:
        self.calls.append((symbol, timeframe, start, end))
        return self._bars


def test_request_security_aligns_host_data_to_chart_bars() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1000},
        {"time": 3, "open": 30, "high": 31, "low": 29, "close": 30, "volume": 3000},
    ])

    result = pn.run(
        """
indicator("MTF", overlay=True)
higher = request.security("BTCUSDT", "2", close)
plot(higher, "Higher")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok
    assert provider.calls == [("BTCUSDT", "2", 1, 4)]
    assert result.values("Higher") == [10, 10, 30, 30]


def test_request_security_applies_history_in_requested_context() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1000},
        {"time": 3, "open": 30, "high": 31, "low": 29, "close": 30, "volume": 3000},
    ])

    result = pn.run(
        """
indicator("MTF History", overlay=True)
higher_prev = request.security("BTCUSDT", "2", close[1])
plot(higher_prev, "Higher Previous")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Higher Previous") == [10, 10]


def test_request_security_gaps_on_requires_exact_requested_bar() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1000},
        {"time": 3, "open": 30, "high": 31, "low": 29, "close": 30, "volume": 3000},
    ])

    result = pn.run(
        """
indicator("MTF Gaps", overlay=True)
higher = request.security("BTCUSDT", "2", "close", gaps="on")
plot(higher, "Higher")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok
    assert result.get_series("Higher") == [
        {"time": 1, "value": 10.0},
        {"time": 3, "value": 30.0},
    ]


def test_request_security_requires_host_provider() -> None:
    result = pn.run(
        """
indicator("Missing Provider", overlay=True)
plot(request.security("BTCUSDT", "1h", close), "Higher")
""",
        _bars(),
        executor_mode="inline",
    )

    assert not result.ok
    assert result.code == "PYNE_UNSUPPORTED_FEATURE"
    assert "host data provider" in str(result.error)


def test_request_security_accepts_basic_expression_thunk() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 12, "low": 8, "close": 10, "volume": 1000},
        {"time": 3, "open": 30, "high": 34, "low": 28, "close": 30, "volume": 3000},
    ])

    result = pn.run(
        """
indicator("MTF Thunk", overlay=True)
higher = request.security("BTCUSDT", "2", lambda ctx: ctx.close)
plot(higher, "Higher")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Higher") == [10, 10, 30, 30]


def test_request_security_evaluates_ta_thunk_in_requested_context() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 12, "low": 8, "close": 10, "volume": 1000},
        {"time": 3, "open": 30, "high": 34, "low": 28, "close": 30, "volume": 3000},
    ])

    result = pn.run(
        """
indicator("MTF SMA", overlay=True)
higher_sma = request.security("BTCUSDT", "2", lambda ctx: ctx.ta.sma(ctx.close, 2))
plot(higher_sma, "Higher SMA")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Higher SMA") == [20, 20]


def test_request_security_applies_thunk_history_in_requested_context() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 12, "low": 8, "close": 10, "volume": 1000},
        {"time": 3, "open": 30, "high": 34, "low": 28, "close": 30, "volume": 3000},
    ])

    result = pn.run(
        """
indicator("MTF Thunk History", overlay=True)
higher_prev = request.security("BTCUSDT", "2", lambda ctx: ctx.close[1])
plot(higher_prev, "Higher Previous")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Higher Previous") == [10, 10]


def test_request_security_accepts_composite_thunk_expression() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 12, "low": 8, "close": 10, "volume": 1000},
        {"time": 3, "open": 30, "high": 34, "low": 28, "close": 30, "volume": 3000},
    ])

    result = pn.run(
        """
indicator("MTF Composite", overlay=True)
higher_mid = request.security("BTCUSDT", "2", lambda ctx: (ctx.high + ctx.low) / 2)
plot(higher_mid, "Higher Mid")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Higher Mid") == [10, 10, 31, 31]


def test_request_security_accepts_tuple_thunk_expression() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 9, "high": 12, "low": 8, "close": 10, "volume": 1000},
        {"time": 3, "open": 29, "high": 34, "low": 28, "close": 30, "volume": 3000},
    ])

    result = pn.run(
        """
indicator("MTF Tuple", overlay=True)
higher_open, higher_close = request.security("BTCUSDT", "2", lambda ctx: (ctx.open, ctx.close))
plot(higher_open, "Higher Open")
plot(higher_close, "Higher Close")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Higher Open") == [9, 9, 29, 29]
    assert result.values("Higher Close") == [10, 10, 30, 30]


def test_request_security_accepts_tuple_field_expression() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 9, "high": 12, "low": 8, "close": 10, "volume": 1000},
        {"time": 3, "open": 29, "high": 34, "low": 28, "close": 30, "volume": 3000},
    ])

    result = pn.run(
        """
indicator("MTF Field Tuple", overlay=True)
higher_high, higher_low = request.security("BTCUSDT", "2", ("high", "low"), gaps="on")
plot(higher_high, "Higher High")
plot(higher_low, "Higher Low")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok
    assert result.get_series("Higher High") == [
        {"time": 1, "value": 12.0},
        {"time": 3, "value": 34.0},
    ]
    assert result.get_series("Higher Low") == [
        {"time": 1, "value": 8.0},
        {"time": 3, "value": 28.0},
    ]


def test_request_security_gaps_and_lookahead_work_with_thunks() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 12, "low": 8, "close": 10, "volume": 1000},
        {"time": 3, "open": 30, "high": 34, "low": 28, "close": 30, "volume": 3000},
    ])

    result = pn.run(
        """
indicator("MTF Policies", overlay=True)
gapped = request.security("BTCUSDT", "2", lambda ctx: ctx.close, gaps="on")
ahead = request.security("BTCUSDT", "2", lambda ctx: ctx.close, lookahead="on")
plot(gapped, "Gapped")
plot(ahead, "Ahead")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok
    assert result.get_series("Gapped") == [
        {"time": 1, "value": 10.0},
        {"time": 3, "value": 30.0},
    ]
    assert result.values("Ahead") == [10, 30, 30]


def test_request_security_rejects_invalid_thunk_return_type() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 12, "low": 8, "close": 10, "volume": 1000},
    ])

    result = pn.run(
        """
indicator("Invalid Thunk", overlay=True)
bad = request.security("BTCUSDT", "2", lambda ctx: {"close": ctx.close})
plot(bad, "Bad")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert not result.ok
    assert result.code == "PYNE_UNSUPPORTED_FEATURE"
    assert "series, tuple of series, or scalar" in str(result.error)


def test_request_security_reports_thunk_exceptions() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 12, "low": 8, "close": 10, "volume": 1000},
    ])

    result = pn.run(
        """
indicator("Thunk Error", overlay=True)
bad = request.security("BTCUSDT", "2", lambda ctx: 1 / 0)
plot(bad, "Bad")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert not result.ok
    assert result.code == "PYNE_RUNTIME_ERROR"
    assert "expression failed" in str(result.error)


def test_request_security_rejects_nested_requests() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 12, "low": 8, "close": 10, "volume": 1000},
    ])

    result = pn.run(
        """
indicator("Nested Request", overlay=True)
bad = request.security(
    "BTCUSDT",
    "2",
    lambda ctx: request.security("BTCUSDT", "2", ctx.close),
)
plot(bad, "Bad")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert not result.ok
    assert result.code == "PYNE_UNSUPPORTED_FEATURE"
    assert "Nested request.security" in str(result.error)
