from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_request_capture_prepare_priority_manifest(tmp_path: Path) -> None:
    out_dir = tmp_path / "capture-pack"

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "request_capture_prepare.py"),
            "--out-dir",
            str(out_dir),
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert "prepared 1 request capture script(s)" in completed.stdout
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["capture_type"] == "request"
    assert manifest["default_scope"] == "priority"
    assert manifest["fixture_count"] == 1
    first = manifest["entries"][0]
    assert first["fixture"] == "request_security_htf_capture.json"
    assert first["priority"] is True
    assert first["status"] == "captured"
    assert first["bar_count"] == 12
    assert first["capture_index_title"] == "Pyne Capture Index"
    assert first["plot_titles"] == [
        "HTF Close",
        "HTF Close Gapped",
        "HTF Close Lookahead",
        "HTF Previous Close",
        "HTF Requested Open",
        "HTF Requested High",
        "HTF Requested Low",
        "HTF Time",
        "HTF Open",
        "HTF High",
        "HTF Low",
        "HTF Provider Close",
        "HTF Volume",
    ]

    pine_text = (out_dir / first["pine_file"]).read_text(encoding="utf-8")
    assert pine_text.startswith("//@version=5\n_pyne_capture_bars = 12\n")
    assert 'indicator("Pyne Request Capture - HTF Alignment", overlay=true)' in pine_text
    assert 'request.security(syminfo.tickerid, "240", close' in pine_text
    assert '"HTF Time"' in pine_text
    assert (out_dir / first["bars_file"]).read_text(encoding="utf-8").startswith(
        "time,open,high,low,close,volume\n"
    )
