from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_strategy_capture_prepare_priority_manifest(tmp_path: Path) -> None:
    out_dir = tmp_path / "capture-pack"

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_prepare.py"),
            "--out-dir",
            str(out_dir),
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert "prepared 10 capture script(s)" in completed.stdout
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["default_scope"] == "priority"
    assert manifest["case_count"] == 10
    assert len(manifest["entries"]) == 10
    first = manifest["entries"][0]
    assert first["fixture"] == "strategy_pine_equivalent_smoke.json"
    assert first["case"] == "market_round_trip_process_on_close"
    assert first["priority"] is True
    assert first["status"] == "not_captured"
    assert first["bar_count"] == 4
    assert first["plot_titles"] == [
        "Position",
        "Equity",
        "Net Profit",
        "Open Profit",
        "Closed Trades",
    ]
    assert (out_dir / first["pine_file"]).read_text(encoding="utf-8").startswith(
        "//@version=5\nstrategy("
    )
    assert (out_dir / "README.md").read_text(encoding="utf-8").startswith(
        "# TradingView Strategy Capture Export Pack"
    )


def test_strategy_capture_prepare_all_cases(tmp_path: Path) -> None:
    out_dir = tmp_path / "capture-pack"

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_prepare.py"),
            "--out-dir",
            str(out_dir),
            "--all",
        ],
        check=True,
        cwd=ROOT,
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["default_scope"] == "all"
    assert manifest["case_count"] == 27


def test_strategy_capture_prepare_case_filter(tmp_path: Path) -> None:
    out_dir = tmp_path / "capture-pack"

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_prepare.py"),
            "--out-dir",
            str(out_dir),
            "--all",
            "--case",
            "bracket_stop_exit",
        ],
        check=True,
        cwd=ROOT,
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["case_count"] == 1
    assert manifest["entries"][0]["case"] == "bracket_stop_exit"


def test_strategy_capture_prepare_refuses_to_clean_repo_root() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_prepare.py"),
            "--out-dir",
            str(ROOT),
            "--clean",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert "refusing to clean protected directory" in completed.stderr
