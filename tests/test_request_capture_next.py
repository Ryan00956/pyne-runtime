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
    assert task == {"status": "complete", "message": "no pending request capture task"}
