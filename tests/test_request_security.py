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


class CapabilityProvider(StaticProvider):
    def __init__(self, bars: list[dict[str, Any]], capabilities: Any) -> None:
        super().__init__(bars)
        self.capabilities = capabilities


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


def test_request_security_accepts_barmerge_alignment_constants() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1000},
        {"time": 3, "open": 30, "high": 31, "low": 29, "close": 30, "volume": 3000},
    ])

    result = pn.run(
        """
indicator("MTF Barmerge", overlay=True)
gapped = request.security("BTCUSDT", "2", "close", gaps=barmerge.gaps_on)
ahead = request.security("BTCUSDT", "2", "close", lookahead=barmerge.lookahead_on)
plot(gapped, "Gapped")
plot(ahead, "Ahead")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert provider.calls == [("BTCUSDT", "2", 1, 4)]
    assert result.get_series("Gapped") == [
        {"time": 1, "value": 10.0},
        {"time": 3, "value": 30.0},
    ]
    assert result.values("Ahead") == [10, 30, 30]


def test_request_security_rejects_invalid_gaps_before_provider_call() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1000},
    ])

    result = pn.run(
        """
indicator("Invalid Gaps", overlay=True)
higher = request.security("BTCUSDT", "2", "close", gaps="maybe")
plot(higher, "Higher")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert not result.ok
    assert result.code == "PYNE_UNSUPPORTED_FEATURE"
    assert "gaps must be one of" in str(result.error)
    assert provider.calls == []


def test_request_security_rejects_invalid_lookahead_before_provider_call() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1000},
    ])

    result = pn.run(
        """
indicator("Invalid Lookahead", overlay=True)
higher = request.security("BTCUSDT", "2", "close", lookahead="future")
plot(higher, "Higher")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert not result.ok
    assert result.code == "PYNE_UNSUPPORTED_FEATURE"
    assert "lookahead must be one of" in str(result.error)
    assert provider.calls == []


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


def test_request_security_respects_provider_capability_false() -> None:
    provider = CapabilityProvider(
        [{"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1000}],
        capabilities={"request.security": False},
    )

    result = pn.run(
        """
indicator("Unsupported Security", overlay=True)
higher = request.security("BTCUSDT", "2", close)
plot(higher, "Higher")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert not result.ok
    assert result.code == "PYNE_UNSUPPORTED_FEATURE"
    assert "provider capability" in str(result.error)
    assert provider.calls == []


def test_request_security_accepts_provider_capability_method_aliases() -> None:
    class MethodCapabilityProvider(StaticProvider):
        def capabilities(self) -> set[str]:
            return {"request.security", "request.security_lower_tf"}

    provider = MethodCapabilityProvider([
        {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1000},
        {"time": 3, "open": 30, "high": 31, "low": 29, "close": 30, "volume": 3000},
    ])

    result = pn.run(
        """
indicator("Capability Method", overlay=True)
higher = request.security("BTCUSDT", "2", close)
lower = request.security_lower_tf("BTCUSDT", "1", close)
plot(higher, "Higher")
plot(lower.size(), "Lower Count")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok
    assert provider.calls == [("BTCUSDT", "2", 1, 4), ("BTCUSDT", "1", 1, 4)]
    assert result.values("Higher") == [10, 10, 30, 30]
    assert result.values("Lower Count") == [1.0, 0.0, 1.0, 0.0]


def test_request_security_reuses_requested_context_for_repeated_requests() -> None:
    class MetadataProvider(StaticProvider):
        def __init__(self, bars: list[dict[str, Any]]) -> None:
            super().__init__(bars)
            self.metadata_calls: list[tuple[str, str]] = []

        def get_request_metadata(self, symbol: str, timeframe: str) -> dict[str, Any]:
            self.metadata_calls.append((symbol, timeframe))
            return {"syminfo": {"tickerid": f"TEST:{symbol}", "mintick": 0.5}}

    provider = MetadataProvider([
        {"time": 1, "open": 9, "high": 12, "low": 8, "close": 10, "volume": 1000},
        {"time": 3, "open": 29, "high": 34, "low": 28, "close": 30, "volume": 3000},
    ])

    result = pn.run(
        """
indicator("MTF Reuse", overlay=True)
higher_close = request.security("BTCUSDT", "2", "close")
higher_high = request.security("BTCUSDT", "2", lambda ctx: ctx.high)
higher_low, higher_open = request.security("BTCUSDT", "2", ("low", "open"))
plot(higher_close, "Higher Close")
plot(higher_high, "Higher High")
plot(higher_low, "Higher Low")
plot(higher_open, "Higher Open")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert provider.calls == [("BTCUSDT", "2", 1, 4)]
    assert provider.metadata_calls == [("BTCUSDT", "2")]
    assert result.values("Higher Close") == [10, 10, 30, 30]
    assert result.values("Higher High") == [12, 12, 34, 34]
    assert result.values("Higher Low") == [8, 8, 28, 28]
    assert result.values("Higher Open") == [9, 9, 29, 29]


def test_request_security_reuses_provider_data_across_request_shapes() -> None:
    class BothCapabilitiesProvider(StaticProvider):
        capabilities = {"request.security": True, "request.security_lower_tf": True}

    provider = BothCapabilitiesProvider([
        {"time": 1, "open": 9, "high": 12, "low": 8, "close": 10, "volume": 1000},
        {"time": 2, "open": 19, "high": 22, "low": 18, "close": 20, "volume": 2000},
        {"time": 3, "open": 29, "high": 32, "low": 28, "close": 30, "volume": 3000},
        {"time": 4, "open": 39, "high": 42, "low": 38, "close": 40, "volume": 4000},
    ])

    result = pn.run(
        """
indicator("Request Shape Reuse", overlay=True)
higher = request.security("BTCUSDT", "1", "close")
lower = request.security_lower_tf("BTCUSDT", "1", "close")
plot(higher, "Higher")
plot(lower.last(), "Lower Last")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert provider.calls == [("BTCUSDT", "1", 1, 4)]
    assert result.values("Higher") == [10, 20, 30, 40]
    assert result.values("Lower Last") == [10.0, 20.0, 30.0, 40.0]


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


def test_request_security_injects_provider_metadata_into_requested_context() -> None:
    class MetadataProvider(StaticProvider):
        def get_request_metadata(self, symbol: str, timeframe: str) -> dict[str, Any]:
            assert symbol == "BTCUSDT"
            assert timeframe == "1D"
            return {
                "syminfo": {
                    "tickerid": "BINANCE:BTCUSDT",
                    "mintick": 0.5,
                    "currency": "USDT",
                    "type": "crypto",
                },
                "timeframe": "1D",
                "session": {"ismarket": False},
            }

    provider = MetadataProvider([
        {"time": 1, "open": 10, "high": 12, "low": 8, "close": 10, "volume": 1000},
        {"time": 3, "open": 30, "high": 34, "low": 28, "close": 30, "volume": 3000},
    ])

    result = pn.run(
        """
indicator("MTF Metadata", overlay=True)
mintick, prefix_match, daily, market = request.security(
    "BTCUSDT",
    "1D",
    lambda ctx: (
        ctx.syminfo.mintick,
        1 if ctx.syminfo.prefix == "BINANCE" else 0,
        1 if ctx.timeframe_info.isdaily else 0,
        ctx.session.ismarket,
    ),
)
plot(mintick, "Requested Mintick")
plot(prefix_match, "Requested Prefix")
plot(daily, "Requested Daily")
plot(market, "Requested Market")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Requested Mintick") == [0.5, 0.5, 0.5, 0.5]
    assert result.values("Requested Prefix") == [1.0, 1.0, 1.0, 1.0]
    assert result.values("Requested Daily") == [1.0, 1.0, 1.0, 1.0]
    assert result.values("Requested Market") == [0.0, 0.0, 0.0, 0.0]


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


def test_request_security_lower_tf_groups_requested_values_by_chart_bar() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1000},
        {"time": 1, "open": 11, "high": 12, "low": 10, "close": 11, "volume": 1100},
        {"time": 2, "open": 20, "high": 21, "low": 19, "close": 20, "volume": 2000},
        {"time": 3, "open": 30, "high": 31, "low": 29, "close": 30, "volume": 3000},
        {"time": 3, "open": 31, "high": 32, "low": 30, "close": 31, "volume": 3100},
        {"time": 4, "open": 40, "high": 41, "low": 39, "close": 40, "volume": 4000},
    ])

    result = pn.run(
        """
indicator("Lower TF", overlay=True)
lower = request.security_lower_tf("BTCUSDT", "1", lambda ctx: ctx.close)
plot(lower.size(), "Lower Count")
plot(lower.last(), "Lower Last")
plot(lower[1].last(), "Previous Lower Last")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok
    assert provider.calls == [("BTCUSDT", "1", 1, 4)]
    assert result.values("Lower Count") == [2.0, 1.0, 2.0, 1.0]
    assert result.values("Lower Last") == [11.0, 20.0, 31.0, 40.0]
    assert result.values("Previous Lower Last") == [11.0, 20.0, 31.0]


def test_request_security_lower_tf_accepts_field_tuple_expression() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 10, "high": 12, "low": 9, "close": 11, "volume": 1000},
        {"time": 2, "open": 20, "high": 22, "low": 19, "close": 21, "volume": 2000},
        {"time": 3, "open": 30, "high": 32, "low": 29, "close": 31, "volume": 3000},
        {"time": 4, "open": 40, "high": 42, "low": 39, "close": 41, "volume": 4000},
    ])

    result = pn.run(
        """
indicator("Lower Tuple", overlay=True)
lower_high, lower_low = request.security_lower_tf("BTCUSDT", "1", ("high", "low"))
plot(lower_high.first(), "Lower High First")
plot(lower_low.last(), "Lower Low Last")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Lower High First") == [12.0, 22.0, 32.0, 42.0]
    assert result.values("Lower Low Last") == [9.0, 19.0, 29.0, 39.0]


def test_request_security_lower_tf_injects_provider_metadata_into_requested_context() -> None:
    class MetadataProvider(StaticProvider):
        request_metadata = {
            "syminfo": {"tickerid": "COINBASE:ETHUSD", "mintick": 0.25},
            "timeframe": "5",
            "session": {"ismarket": False},
        }

    provider = MetadataProvider([
        {"time": 1, "open": 10, "high": 12, "low": 9, "close": 11, "volume": 1000},
        {"time": 2, "open": 20, "high": 22, "low": 19, "close": 21, "volume": 2000},
        {"time": 3, "open": 30, "high": 32, "low": 29, "close": 31, "volume": 3000},
        {"time": 4, "open": 40, "high": 42, "low": 39, "close": 41, "volume": 4000},
    ])

    result = pn.run(
        """
indicator("Lower Metadata", overlay=True)
lower = request.security_lower_tf(
    "ETHUSD",
    "5",
    lambda ctx: ctx.syminfo.mintick + ctx.timeframe_info.multiplier + ctx.session.ismarket,
)
plot(lower.last(), "Lower Metadata")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Lower Metadata") == [5.25, 5.25, 5.25, 5.25]


def test_request_security_lower_tf_exposes_array_like_numeric_helpers() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 100},
        {"time": 1, "open": 2, "high": 2, "low": 2, "close": 2, "volume": 200},
        {"time": 1, "open": 3, "high": 3, "low": 3, "close": 3, "volume": 300},
        {"time": 3, "open": 4, "high": 4, "low": 4, "close": 4, "volume": 400},
        {"time": 3, "open": 5, "high": 5, "low": 5, "close": 5, "volume": 500},
    ])

    result = pn.run(
        """
indicator("Lower Helpers", overlay=True)
lower = request.security_lower_tf("BTCUSDT", "1", lambda ctx: ctx.close)
plot(lower.get(1), "Second")
plot(lower.sum(), "Sum")
plot(lower.min(), "Min")
plot(lower.max(), "Max")
plot(lower.avg(), "Average")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Second") == [2.0, 5.0]
    assert result.values("Sum") == [6.0, 9.0]
    assert result.values("Min") == [1.0, 4.0]
    assert result.values("Max") == [3.0, 5.0]
    assert result.values("Average") == [2.0, 4.5]


def test_request_security_lower_tf_helpers_use_default_for_empty_groups() -> None:
    provider = StaticProvider([
        {"time": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 100},
        {"time": 4, "open": 4, "high": 4, "low": 4, "close": 4, "volume": 400},
    ])

    result = pn.run(
        """
indicator("Lower Empty", overlay=True)
lower = request.security_lower_tf("BTCUSDT", "1", "close")
plot(lower.get(1, default=0), "Second")
plot(lower.sum(default=0), "Sum")
plot(lower.min(default=-1), "Min")
plot(lower.avg(default=0), "Average")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok
    assert result.values("Second") == [0.0, 0.0, 0.0, 0.0]
    assert result.values("Sum") == [1.0, 0.0, 0.0, 4.0]
    assert result.values("Min") == [1.0, -1.0, -1.0, 4.0]
    assert result.values("Average") == [1.0, 0.0, 0.0, 4.0]


def test_request_security_lower_tf_respects_provider_capabilities() -> None:
    provider = CapabilityProvider(
        [{"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1000}],
        capabilities={"security_lower_tf": False},
    )

    result = pn.run(
        """
indicator("Lower Unsupported", overlay=True)
lower = request.security_lower_tf("BTCUSDT", "1", close)
plot(lower.size(), "Lower Count")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert not result.ok
    assert result.code == "PYNE_UNSUPPORTED_FEATURE"
    assert "provider capability" in str(result.error)


def test_request_security_lower_tf_rejects_missing_list_capability() -> None:
    provider = CapabilityProvider(
        [{"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1000}],
        capabilities={"request.security"},
    )

    result = pn.run(
        """
indicator("Lower Missing Capability", overlay=True)
lower = request.security_lower_tf("BTCUSDT", "1", close)
plot(lower.size(), "Lower Count")
""",
        _bars(),
        data_provider=provider,
        executor_mode="inline",
    )

    assert not result.ok
    assert result.code == "PYNE_UNSUPPORTED_FEATURE"
    assert "provider capability" in str(result.error)
    assert provider.calls == []
