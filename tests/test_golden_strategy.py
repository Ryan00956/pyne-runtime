from __future__ import annotations

import json
from pathlib import Path

import pytest

import pyne_runtime as pn


GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.mark.parametrize(
    "case",
    json.loads((GOLDEN_DIR / "strategy_same_bar_priority.json").read_text())["cases"],
    ids=lambda case: case["name"],
)
def test_strategy_same_bar_priority_golden(case: dict) -> None:
    result = pn.run(case["script"], case["bars"], executor_mode="inline")

    assert result.ok, result.error
    assert result.output["strategy"]["orders"] == case["orders"]
    assert (
        result.output["strategy"]["summary"]["same_bar_fill_priority"]
        == case["same_bar_fill_priority"]
    )
    assert result.output["strategy"]["summary"]["intrabar_path"] == case["intrabar_path"]


@pytest.mark.parametrize(
    "case",
    json.loads((GOLDEN_DIR / "strategy_lifecycle.json").read_text())["cases"],
    ids=lambda case: case["name"],
)
def test_strategy_lifecycle_golden(case: dict) -> None:
    result = pn.run(case["script"], case["bars"], executor_mode="inline")

    assert result.ok, result.error
    assert result.output["strategy"]["orders"] == case["orders"]
    assert result.output["strategy"]["lifecycle"] == case["lifecycle"]
    assert result.values("Position") == case["position"]
    assert result.output["strategy"]["summary"] == case["summary"]
    assert result.output["strategy"]["risk"] == case["risk"]


@pytest.mark.parametrize(
    "case",
    json.loads((GOLDEN_DIR / "strategy_risk_lock.json").read_text())["cases"],
    ids=lambda case: case["name"],
)
def test_strategy_risk_lock_golden(case: dict) -> None:
    result = pn.run(case["script"], case["bars"], executor_mode="inline")

    assert result.ok, result.error
    assert result.output["strategy"]["orders"] == case["orders"]
    assert result.output["strategy"]["lifecycle"] == case["lifecycle"]
    assert result.values("Position") == case["position"]
    assert result.values("Equity") == case["equity"]
    assert result.output["strategy"]["summary"] == case["summary"]
    assert result.output["strategy"]["risk"] == case["risk"]
