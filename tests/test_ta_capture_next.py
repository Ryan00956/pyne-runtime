from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ta_capture_next_json_default_priority_is_complete() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ta_capture_next.py"),
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    task = json.loads(completed.stdout)
    assert task == {"status": "complete", "message": "no pending TA capture task"}


def test_ta_capture_next_uses_manifest_for_all_scope(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ta_capture_prepare.py"),
            "--out-dir",
            str(pack_dir),
            "--all",
        ],
        check=True,
        cwd=ROOT,
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ta_capture_next.py"),
            "--manifest",
            str(pack_dir / "manifest.json"),
            "--all",
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    task = json.loads(completed.stdout)
    assert task == {
        "status": "pending",
        "fixture": "ta_oscillator_edges_indicators.json",
        "name": "ta_oscillator_edges_indicators",
        "priority": False,
        "capture_status": "not_captured",
        "prepare_command": "python scripts/ta_capture_prepare.py --out-dir .tmp/tradingview-ta --clean --all",
        "preflight_command": (
            "python scripts/ta_capture_preflight.py "
            ".tmp/tradingview-ta/manifest.json --fixture ta_oscillator_edges_indicators.json"
        ),
        "import_command": (
            "python scripts/ta_capture_import.py tests/golden/ta_oscillator_edges_indicators.json "
            "--values .tmp/tradingview-ta/04_ta_oscillator_edges_indicators.csv "
            "--tolerance 1e-9 --note \"TradingView export YYYY-MM-DD\""
        ),
        "diff_command": "python scripts/ta_capture_diff.py --assertion reference tests/golden/ta_oscillator_edges_indicators.json",
        "pine_file": "04_ta_oscillator_edges_indicators.pine",
        "bars_file": "04_ta_oscillator_edges_indicators_bars.csv",
        "expected_export_file": "04_ta_oscillator_edges_indicators.csv",
        "plot_titles": [
            "Stoch 3",
            "Stoch 6",
            "MFI 3",
            "MFI 6",
            "WPR 3",
            "WPR 6",
            "CMO 3",
            "CMO 6",
            "RSI 3",
            "CCI 5",
        ],
        "capture_index_title": "Pyne Capture Index",
        "bar_count": 18,
    }


def test_ta_capture_next_text_output() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ta_capture_next.py"),
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "no pending TA capture task"
