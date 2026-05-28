from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_strategy_capture_next_json_default_priority() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_next.py"),
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    task = json.loads(completed.stdout)
    assert task["status"] == "pending"
    assert task["fixture"] == "strategy_pine_equivalent_cost_allocation.json"
    assert task["case"] == "percent_commission_round_trip"
    assert task["priority"] is True
    assert "strategy_capture_prepare.py" in task["prepare_command"]
    assert "strategy_capture_preflight.py" in task["preflight_command"]
    assert "strategy_capture_import.py" in task["import_command"]
    assert "strategy_capture_diff.py" in task["diff_command"]


def test_strategy_capture_next_uses_manifest(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_prepare.py"),
            "--out-dir",
            str(pack_dir),
        ],
        check=True,
        cwd=ROOT,
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_next.py"),
            "--manifest",
            str(pack_dir / "manifest.json"),
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    task = json.loads(completed.stdout)
    assert task["pine_file"] == (
        "04_strategy_pine_equivalent_cost_allocation__percent_commission_round_trip.pine"
    )
    assert task["bars_file"] == (
        "04_strategy_pine_equivalent_cost_allocation__percent_commission_round_trip_bars.csv"
    )
    assert task["expected_export_file"] == (
        "04_strategy_pine_equivalent_cost_allocation__percent_commission_round_trip.csv"
    )
    assert task["bar_count"] == 2
    assert task["plot_titles"] == [
        "Position",
        "Equity",
        "Net Profit",
        "Open Profit",
        "Closed Trades",
        "Closed Profit",
        "Closed Commission",
        "Closed Net Profit",
    ]


def test_strategy_capture_next_text_output() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_next.py"),
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert "Next strategy TradingView capture task" in completed.stdout
    assert "percent_commission_round_trip" in completed.stdout
