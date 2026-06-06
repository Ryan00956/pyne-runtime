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
        "total": 11,
        "captured": 10,
        "not_captured": 1,
        "missing": 0,
        "priority_total": 8,
        "priority_captured": 8,
    }
    first = report["fixtures"][0]
    assert first["fixture"] == "request_security_htf_capture.json"
    assert first["priority"] is True
    assert first["status"] == "captured"
    assert first["assertion"] == "parity"
    second = report["fixtures"][1]
    assert second["fixture"] == "request_security_lower_tf_capture.json"
    assert second["priority"] is True
    assert second["status"] == "captured"
    assert second["assertion"] == "parity"
    assert second["plot_count"] == 20
    third = report["fixtures"][2]
    assert third["fixture"] == "request_security_time_close_capture.json"
    assert third["priority"] is True
    assert third["status"] == "captured"
    assert third["assertion"] == "parity"
    assert third["plot_count"] == 9
    fourth = report["fixtures"][3]
    assert fourth["fixture"] == "request_security_metadata_capture.json"
    assert fourth["priority"] is True
    assert fourth["status"] == "captured"
    assert fourth["assertion"] == "parity"
    assert fourth["plot_count"] == 11
    fifth = report["fixtures"][4]
    assert fifth["fixture"] == "request_security_gaps_lookahead_capture.json"
    assert fifth["priority"] is True
    assert fifth["status"] == "captured"
    assert fifth["assertion"] == "parity"
    assert fifth["plot_count"] == 10
    sixth = report["fixtures"][5]
    assert sixth["fixture"] == "request_security_daily_context_capture.json"
    assert sixth["priority"] is True
    assert sixth["status"] == "captured"
    assert sixth["assertion"] == "parity"
    assert sixth["plot_count"] == 13
    seventh = report["fixtures"][6]
    assert seventh["fixture"] == "request_security_session_flags_capture.json"
    assert seventh["priority"] is True
    assert seventh["status"] == "captured"
    assert seventh["assertion"] == "parity"
    assert seventh["plot_count"] == 9
    eighth = report["fixtures"][7]
    assert eighth["fixture"] == "request_security_timezone_capture.json"
    assert eighth["priority"] is True
    assert eighth["status"] == "captured"
    assert eighth["assertion"] == "parity"
    assert eighth["plot_count"] == 10
    ninth = report["fixtures"][8]
    assert ninth["fixture"] == "request_security_expression_context_capture.json"
    assert ninth["priority"] is False
    assert ninth["status"] == "not_captured"
    assert ninth["assertion"] == "parity"
    assert ninth["plot_count"] == 0
    tenth = report["fixtures"][9]
    assert tenth["fixture"] == "request_security_invalid_symbol_ignore_capture.json"
    assert tenth["priority"] is False
    assert tenth["status"] == "captured"
    assert tenth["assertion"] == "parity"
    assert tenth["plot_count"] == 9
    eleventh = report["fixtures"][10]
    assert eleventh["fixture"] == "request_security_lower_tf_invalid_symbol_ignore_capture.json"
    assert eleventh["priority"] is False
    assert eleventh["status"] == "captured"
    assert eleventh["assertion"] == "parity"
    assert eleventh["plot_count"] == 6
