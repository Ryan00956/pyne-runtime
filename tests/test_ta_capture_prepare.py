from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ta_capture_prepare_priority_manifest(tmp_path: Path) -> None:
    out_dir = tmp_path / "capture-pack"

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ta_capture_prepare.py"),
            "--out-dir",
            str(out_dir),
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert "prepared 1 TA capture script(s)" in completed.stdout
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["capture_type"] == "ta"
    assert manifest["default_scope"] == "priority"
    assert manifest["fixture_count"] == 1
    first = manifest["entries"][0]
    assert first["fixture"] == "ta_core_indicators.json"
    assert first["priority"] is True
    assert first["status"] == "captured"
    assert first["bar_count"] == 10
    assert first["capture_index_title"] == "Pyne Capture Index"
    assert "--assertion parity" in first["diff_command"]

    pine_text = (out_dir / first["pine_file"]).read_text(encoding="utf-8")
    assert pine_text.startswith("//@version=5\n_pyne_capture_bars = 10\n")
    assert 'plot(_pyne_capture_active ? _pyne_capture_index : na, "Pyne Capture Index")' in pine_text
    assert "ta.sma(_pyne_close, 3)" in pine_text
    assert "condition = _pyne_close > 14" in pine_text
    assert "mintick=" not in pine_text
    assert (out_dir / first["bars_file"]).read_text(encoding="utf-8").startswith(
        "time,open,high,low,close,volume\n"
    )


def test_ta_capture_prepare_all_fixtures(tmp_path: Path) -> None:
    out_dir = tmp_path / "capture-pack"

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ta_capture_prepare.py"),
            "--out-dir",
            str(out_dir),
            "--all",
        ],
        check=True,
        cwd=ROOT,
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["default_scope"] == "all"
    assert manifest["fixture_count"] == 4
    statuses = {entry["fixture"]: entry["status"] for entry in manifest["entries"]}
    assert statuses["ta_core_indicators.json"] == "captured"
    assert sum(status == "missing" for status in statuses.values()) == 3
