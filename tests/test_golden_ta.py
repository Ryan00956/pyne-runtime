from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyne_runtime as pn


GOLDEN_DIR = Path(__file__).parent / "golden"


def test_ta_core_indicators_golden() -> None:
    fixture = _load_fixture("ta_core_indicators.json")

    result = pn.run(
        fixture["script"],
        fixture["chart_bars"],
        executor_mode="inline",
    )

    assert result.ok, result.error
    for name, expected in fixture["expected_series"].items():
        assert result.get_series(name) == expected


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))
