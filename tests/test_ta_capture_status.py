from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ta_capture_status_json_report() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ta_capture_status.py"),
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    report = json.loads(completed.stdout)

    assert report["counts"]["total"] == 4
    assert report["counts"]["captured"] == 1
    assert report["counts"]["missing"] == 3
    assert report["counts"]["priority_total"] == 1
    assert report["counts"]["priority_captured"] == 1
    first = report["fixtures"][0]
    assert first["fixture"] == "ta_core_indicators.json"
    assert first["priority"] is True
    assert first["status"] == "captured"
    assert first["assertion"] == "reference"
