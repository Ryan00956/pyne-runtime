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

    assert report["counts"]["total"] == 10
    assert report["counts"]["captured"] == 10
    assert report["counts"]["not_captured"] == 0
    assert report["counts"]["missing"] == 0
    assert report["counts"]["priority_total"] == 1
    assert report["counts"]["priority_captured"] == 1
    fixtures = report["fixtures"]
    assert [item["fixture"] for item in fixtures] == [
        "ta_core_indicators.json",
        "ta_advanced_indicators.json",
        "ta_context_indicators.json",
        "ta_external_library_indicators.json",
        "ta_oscillator_edges_indicators.json",
        "ta_remaining_indicators.json",
        "ta_statistics_edges_indicators.json",
        "ta_trend_switch_indicators.json",
        "ta_tuple_outputs_indicators.json",
        "ta_warmup_boundaries_indicators.json",
    ]
    assert fixtures[0]["priority"] is True
    assert all(item["status"] == "captured" for item in fixtures)
    assert all(item["assertion"] == "parity" for item in fixtures)
