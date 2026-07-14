from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_request_capture_preflight_rejects_unknown_fixture_filter(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "capture_type": "request",
                "entries": [
                    {
                        "fixture": "request_sample.json",
                        "expected_export_file": "sample.csv",
                        "bar_count": 1,
                        "plot_titles": ["Close"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "request_capture_preflight.py"),
            str(manifest),
            "--fixture",
            "typo.json",
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert report["counts"] == {"fixtures": 0, "ok": 0, "issues": 1}
    assert report["issues"][0]["kind"] == "unknown_fixture_filter"
