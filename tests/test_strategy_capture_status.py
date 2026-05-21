from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_strategy_capture_status_json_report() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_status.py"),
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    report = json.loads(completed.stdout)

    assert report["counts"]["total"] == 27
    assert report["counts"]["captured"] == 0
    assert report["counts"]["not_captured"] == 1
    assert report["counts"]["missing"] == 26
    assert report["counts"]["priority_total"] == 10
    smoke = report["cases"][0]
    assert smoke["fixture"] == "strategy_pine_equivalent_smoke.json"
    assert smoke["case"] == "market_round_trip_process_on_close"
    assert smoke["priority"] is True
    assert smoke["provider"] == "tradingview"
    assert smoke["status"] == "not_captured"


def test_strategy_capture_status_missing_only() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_status.py"),
            "--json",
            "--missing-only",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    report = json.loads(completed.stdout)

    assert all(case["status"] != "captured" for case in report["cases"])
    expected_missing = report["counts"]["not_captured"] + report["counts"]["missing"]
    assert len(report["cases"]) == expected_missing
