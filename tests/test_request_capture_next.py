from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_request_capture_next_uses_manifest(tmp_path: Path) -> None:
    out_dir = tmp_path / "capture-pack"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "request_capture_prepare.py"),
            "--out-dir",
            str(out_dir),
        ],
        check=True,
        cwd=ROOT,
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "request_capture_next.py"),
            "--manifest",
            str(out_dir / "manifest.json"),
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    task = json.loads(completed.stdout)
    assert task["status"] == "pending"
    assert task["fixture"] == "request_security_htf_capture.json"
    assert task["pine_file"] == "01_request_security_htf_capture.pine"
    assert task["bars_file"] == "01_request_security_htf_capture_bars.csv"
    assert task["expected_export_file"] == "01_request_security_htf_capture.csv"
    assert task["capture_index_title"] == "Pyne Capture Index"
    assert task["bar_count"] == 12
    assert "request_capture_import.py" in task["import_command"]
    assert "request_capture_diff.py" in task["diff_command"]
