from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_request_capture_status_json_report() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "request_capture_status.py"),
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    report = json.loads(completed.stdout)

    assert report["counts"] == {
        "total": 1,
        "captured": 0,
        "not_captured": 1,
        "missing": 0,
        "priority_total": 1,
        "priority_captured": 0,
    }
    first = report["fixtures"][0]
    assert first["fixture"] == "request_security_htf_capture.json"
    assert first["priority"] is True
    assert first["status"] == "not_captured"
    assert first["assertion"] == "reference"
