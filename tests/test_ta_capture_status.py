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
    assert report["counts"]["captured"] == 4
    assert report["counts"]["not_captured"] == 0
    assert report["counts"]["missing"] == 0
    assert report["counts"]["priority_total"] == 1
    assert report["counts"]["priority_captured"] == 1
    first = report["fixtures"][0]
    assert first["fixture"] == "ta_core_indicators.json"
    assert first["priority"] is True
    assert first["status"] == "captured"
    assert first["assertion"] == "parity"
    second = report["fixtures"][1]
    assert second["fixture"] == "ta_advanced_indicators.json"
    assert second["priority"] is False
    assert second["status"] == "captured"
    assert second["assertion"] == "parity"
    third = report["fixtures"][2]
    assert third["fixture"] == "ta_context_indicators.json"
    assert third["priority"] is False
    assert third["status"] == "captured"
    assert third["assertion"] == "reference"
    fourth = report["fixtures"][3]
    assert fourth["fixture"] == "ta_remaining_indicators.json"
    assert fourth["priority"] is False
    assert fourth["status"] == "captured"
    assert fourth["assertion"] == "reference"
