from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import pyne_runtime as pn


GOLDEN_DIR = Path(__file__).parent / "golden"


class GoldenProvider:
    def __init__(self, bars: list[dict[str, Any]] | dict[str, list[dict[str, Any]]]) -> None:
        self.calls: list[tuple[str, str, int, int]] = []
        self._bars = bars
        self.capabilities = {
            "request.security": True,
            "request.security_lower_tf": True,
        }

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> list[dict[str, Any]]:
        self.calls.append((symbol, timeframe, start, end))
        if isinstance(self._bars, dict):
            return self._bars.get(f"{symbol}|{timeframe}", self._bars.get(timeframe, []))
        return self._bars


def test_golden_request_security_lower_tf_alignment() -> None:
    fixture = _load_fixture("request_security_lower_tf_alignment.json")
    provider = GoldenProvider(fixture["provider_bars"])

    result = pn.run(
        fixture["script"],
        fixture["chart_bars"],
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert [list(call) for call in provider.calls] == fixture["expected_provider_calls"]
    for name, expected in fixture["expected_series"].items():
        _assert_series_matches(result.get_series(name), expected)


def test_golden_request_security_alignment() -> None:
    fixture = _load_fixture("request_security_alignment.json")
    provider = GoldenProvider(fixture["provider_bars"])

    result = pn.run(
        fixture["script"],
        fixture["chart_bars"],
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert [list(call) for call in provider.calls] == fixture["expected_provider_calls"]
    for name, expected in fixture["expected_series"].items():
        _assert_series_matches(result.get_series(name), expected)


def test_golden_request_security_edge_cases() -> None:
    fixture = _load_fixture("request_security_edge_cases.json")
    provider = GoldenProvider(fixture["provider_bars"])

    result = pn.run(
        fixture["script"],
        fixture["chart_bars"],
        data_provider=provider,
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert [list(call) for call in provider.calls] == fixture["expected_provider_calls"]
    for name, expected in fixture["expected_series"].items():
        _assert_series_matches(result.get_series(name), expected)


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))


def _assert_series_matches(actual: list[dict[str, Any]], expected: list[dict[str, Any]]) -> None:
    assert len(actual) == len(expected)
    for actual_point, expected_point in zip(actual, expected):
        assert actual_point.keys() == expected_point.keys()
        for key, expected_value in expected_point.items():
            actual_value = actual_point[key]
            if key == "value" and isinstance(expected_value, (int, float)):
                assert actual_value == pytest.approx(expected_value, abs=1e-9)
            else:
                assert actual_value == expected_value
