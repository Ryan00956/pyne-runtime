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
        "fixture": "ta_tuple_outputs_indicators.json",
        "name": "ta_tuple_outputs_indicators",
        "priority": False,
        "capture_status": "not_captured",
        "prepare_command": "python scripts/ta_capture_prepare.py --out-dir .tmp/tradingview-ta --clean --all",
        "preflight_command": (
            "python scripts/ta_capture_preflight.py "
            ".tmp/tradingview-ta/manifest.json --fixture ta_tuple_outputs_indicators.json"
        ),
        "import_command": (
            "python scripts/ta_capture_import.py tests/golden/ta_tuple_outputs_indicators.json "
            "--values .tmp/tradingview-ta/08_ta_tuple_outputs_indicators.csv "
            "--tolerance 1e-9 --note \"TradingView export YYYY-MM-DD\""
        ),
        "diff_command": "python scripts/ta_capture_diff.py --assertion reference tests/golden/ta_tuple_outputs_indicators.json",
        "pine_file": "08_ta_tuple_outputs_indicators.pine",
        "bars_file": "08_ta_tuple_outputs_indicators_bars.csv",
        "expected_export_file": "08_ta_tuple_outputs_indicators.csv",
        "plot_titles": [
            "MACD 4 8 Line",
            "MACD 4 8 Signal",
            "MACD 4 8 Hist",
            "MACD Line Minus Signal",
            "BB 5 Mid",
            "BB 5 Upper",
            "BB 5 Lower",
            "BB 5 Width",
            "BB 5 Relative",
            "Plus DI 5",
            "Minus DI 5",
            "ADX 5 4",
            "DI Spread 5",
        ],
        "capture_index_title": "Pyne Capture Index",
        "bar_count": 24,
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
