from __future__ import annotations

from typing import Any

import pyne_runtime as pn


def _bar(time: int, close: float, *, width: int) -> dict[str, Any]:
    return {
        "time": time,
        "time_close": time + width,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 10,
    }


class ConformingProvider:
    capabilities = {
        pn.REQUEST_SECURITY_API: True,
        pn.REQUEST_SECURITY_LOWER_TF_API: True,
    }

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> list[pn.OHLCVBar]:
        if symbol == "MISSING":
            raise pn.PyneInvalidSymbolError(symbol)
        width = int(timeframe)
        return [
            _bar(time, 100 + time, width=width)
            for time in range(0, 7, width)
            if start <= time <= end
        ]

    def get_request_metadata(self, symbol: str, timeframe: str) -> pn.RequestMetadata:
        return {
            "syminfo": {"ticker": symbol, "tickerid": symbol, "mintick": 0.1},
            "timeframe": timeframe,
            "session": {"ismarket": True},
        }


def _chart() -> list[dict[str, Any]]:
    return [_bar(time, 10 + time, width=2) for time in (0, 2, 4)]


def test_reusable_provider_conformance_kit_covers_full_contract() -> None:
    report = pn.assert_data_provider_conformance(
        ConformingProvider(),
        chart_ohlcv=_chart(),
        symbol="BTCUSDT",
        timeframe="2",
        lower_timeframe="1",
        invalid_symbol="MISSING",
    )

    assert report.ok
    assert not report.failures
    assert all(check.status == "passed" for check in report.checks)
    assert report.to_dict()["ok"] is True


def test_conformance_kit_reports_untyped_invalid_symbol_failure() -> None:
    class UntypedInvalidSymbolProvider(ConformingProvider):
        def get_ohlcv(
            self,
            symbol: str,
            timeframe: str,
            start: int,
            end: int,
        ) -> list[pn.OHLCVBar]:
            if symbol == "MISSING":
                raise KeyError(symbol)
            return super().get_ohlcv(symbol, timeframe, start, end)

    report = pn.run_data_provider_conformance(
        UntypedInvalidSymbolProvider(),
        chart_ohlcv=_chart(),
        symbol="BTCUSDT",
        timeframe="2",
        invalid_symbol="MISSING",
    )

    assert not report.ok
    assert report.failures[0].name == "typed.invalid_symbol.request.security"
    assert "PyneInvalidSymbolError" in report.failures[0].detail


def test_typed_provider_data_error_keeps_machine_category() -> None:
    class OfflineProvider(ConformingProvider):
        def get_ohlcv(
            self,
            symbol: str,
            timeframe: str,
            start: int,
            end: int,
        ) -> list[pn.OHLCVBar]:
            raise pn.PyneProviderDataError("market data is offline")

    result = pn.run(
        'indicator("typed")\nplot(request.security("BTCUSDT", "2", close), "Close")',
        _chart(),
        data_provider=OfflineProvider(),
        executor_mode="inline",
    )

    assert not result.ok
    assert result.error_detail is not None
    assert result.error_detail["requestProviderCategory"] == (
        pn.RequestProviderErrorCategory.PROVIDER_FAILURE.value
    )
    assert result.error == "market data is offline"
