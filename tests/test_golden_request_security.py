from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyne_runtime as pn


GOLDEN_DIR = Path(__file__).parent / "golden"


class GoldenProvider:
    def __init__(self, bars: list[dict[str, Any]]) -> None:
        self.calls: list[tuple[str, str, int, int]] = []
        self._bars = bars
        self.capabilities = {"security_lower_tf": True}

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> list[dict[str, Any]]:
        self.calls.append((symbol, timeframe, start, end))
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
        assert result.get_series(name) == expected


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))
