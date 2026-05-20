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


@pytest.mark.parametrize(
    "case",
    json.loads((GOLDEN_DIR / "strategy_lot_matching.json").read_text())["cases"],
    ids=lambda case: case["name"],
)
def test_strategy_lot_matching_golden(case: dict) -> None:
    result = pn.run(case["script"], case["bars"], executor_mode="inline")

    assert result.ok, result.error
    assert result.output["strategy"]["orders"] == case["orders"]
    assert result.output["strategy"]["lifecycle"] == case["lifecycle"]
    assert result.output["strategy"]["closedtrades"] == case["closedtrades"]
    assert result.output["strategy"]["opentrades"] == case["opentrades"]
    assert result.values("Position") == case["position"]
    assert result.output["strategy"]["summary"] == case["summary"]
    assert result.output["strategy"]["risk"] == case["risk"]


@pytest.mark.parametrize(
    "case",
    json.loads((GOLDEN_DIR / "strategy_intraday_risk_reset.json").read_text())[
        "cases"
    ],
    ids=lambda case: case["name"],
)
def test_strategy_intraday_risk_reset_golden(case: dict) -> None:
    result = pn.run(case["script"], case["bars"], executor_mode="inline")

    assert result.ok, result.error
    assert result.output["strategy"]["orders"] == case["orders"]
    assert result.output["strategy"]["lifecycle"] == case["lifecycle"]
    assert result.values("Position") == case["position"]
    if "equity" in case:
        assert result.values("Equity") == case["equity"]
    assert result.output["strategy"]["summary"] == case["summary"]
    assert result.output["strategy"]["risk"] == case["risk"]


@pytest.mark.parametrize(
    "case",
    json.loads((GOLDEN_DIR / "strategy_pending_risk_lock.json").read_text())[
        "cases"
    ],
    ids=lambda case: case["name"],
)
def test_strategy_pending_risk_lock_golden(case: dict) -> None:
    result = pn.run(case["script"], case["bars"], executor_mode="inline")

    assert result.ok, result.error
    assert result.output["strategy"]["orders"] == case["orders"]
    assert result.output["strategy"]["lifecycle"] == case["lifecycle"]
    assert result.values("Position") == case["position"]
    assert result.values("Equity") == case["equity"]
    assert result.output["strategy"]["summary"] == case["summary"]
    assert result.output["strategy"]["risk"] == case["risk"]


@pytest.mark.parametrize(
    "case",
    json.loads((GOLDEN_DIR / "strategy_oca_lifecycle.json").read_text())[
        "cases"
    ],
    ids=lambda case: case["name"],
)
def test_strategy_oca_lifecycle_golden(case: dict) -> None:
    result = pn.run(case["script"], case["bars"], executor_mode="inline")

    assert result.ok, result.error
    assert result.output["strategy"]["orders"] == case["orders"]
    assert result.output["strategy"]["lifecycle"] == case["lifecycle"]
    assert result.values("Position") == case["position"]
    assert result.output["strategy"]["summary"] == case["summary"]
    assert result.output["strategy"]["risk"] == case["risk"]


@pytest.mark.parametrize(
    "case",
    json.loads((GOLDEN_DIR / "strategy_cost_model.json").read_text())[
        "cases"
    ],
    ids=lambda case: case["name"],
)
def test_strategy_cost_model_golden(case: dict) -> None:
    result = pn.run(case["script"], case["bars"], executor_mode="inline")

    assert result.ok, result.error
    assert result.output["strategy"]["orders"] == case["orders"]
    assert result.output["strategy"]["lifecycle"] == case["lifecycle"]
    assert result.output["strategy"]["closedtrades"] == case["closedtrades"]
    assert result.output["strategy"]["opentrades"] == case["opentrades"]
    assert result.values("Position") == case["position"]
    assert result.values("Equity") == case["equity"]
    assert result.values("Net Profit") == case["netprofit"]
    if "closed_commission" in case:
        assert result.values("Closed Commission") == case["closed_commission"]
    if "first_closed_commission" in case:
        assert (
            result.values("First Closed Commission")
            == case["first_closed_commission"]
        )
    if "last_closed_commission" in case:
        assert (
            result.values("Last Closed Commission")
            == case["last_closed_commission"]
        )
    assert result.output["strategy"]["summary"] == case["summary"]
    assert result.output["strategy"]["risk"] == case["risk"]


@pytest.mark.parametrize(
    "case",
    json.loads((GOLDEN_DIR / "strategy_limit_verification_costs.json").read_text())[
        "cases"
    ],
    ids=lambda case: case["name"],
)
def test_strategy_limit_verification_costs_golden(case: dict) -> None:
    result = pn.run(case["script"], case["bars"], executor_mode="inline")

    assert result.ok, result.error
    assert result.output["strategy"]["orders"] == case["orders"]
    assert result.output["strategy"]["lifecycle"] == case["lifecycle"]
    assert result.output["strategy"]["closedtrades"] == case["closedtrades"]
    assert result.output["strategy"]["opentrades"] == case["opentrades"]
    assert result.values("Position") == case["position"]
    assert result.values("Equity") == case["equity"]
    assert result.values("Net Profit") == case["netprofit"]
    if "closed_commission" in case:
        assert result.values("Closed Commission") == case["closed_commission"]
    assert result.output["strategy"]["summary"] == case["summary"]
    assert result.output["strategy"]["risk"] == case["risk"]


@pytest.mark.parametrize(
    "case",
    json.loads((GOLDEN_DIR / "strategy_bracket_stop_limit_costs.json").read_text())[
        "cases"
    ],
    ids=lambda case: case["name"],
)
def test_strategy_bracket_stop_limit_costs_golden(case: dict) -> None:
    result = pn.run(case["script"], case["bars"], executor_mode="inline")

    assert result.ok, result.error
    assert result.output["strategy"]["orders"] == case["orders"]
    assert result.output["strategy"]["lifecycle"] == case["lifecycle"]
    assert result.output["strategy"]["closedtrades"] == case["closedtrades"]
    assert result.output["strategy"]["opentrades"] == case["opentrades"]
    assert result.values("Position") == case["position"]
    assert result.values("Equity") == case["equity"]
    assert result.values("Net Profit") == case["netprofit"]
    assert result.values("Closed Commission") == case["closed_commission"]
    assert result.output["strategy"]["summary"] == case["summary"]
    assert result.output["strategy"]["risk"] == case["risk"]
