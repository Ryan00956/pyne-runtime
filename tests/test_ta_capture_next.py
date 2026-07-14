from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ta_capture_next_json_default_priority_is_complete() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ta_capture_next.py"),
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    task = json.loads(completed.stdout)
    assert task == {"status": "complete", "message": "no pending TA capture task"}


def test_ta_capture_next_uses_manifest_for_all_scope(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ta_capture_prepare.py"),
            "--out-dir",
            str(pack_dir),
            "--all",
        ],
        check=True,
        cwd=ROOT,
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ta_capture_next.py"),
            "--manifest",
            str(pack_dir / "manifest.json"),
            "--all",
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    task = json.loads(completed.stdout)
    assert task == {"status": "complete", "message": "no pending TA capture task"}


def test_ta_capture_next_text_output() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ta_capture_next.py"),
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "no pending TA capture task"


def test_ta_capture_next_uses_custom_manifest_parent_in_commands(tmp_path: Path) -> None:
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    (golden_dir / "ta_core_indicators.json").write_text(
        json.dumps({"name": "pending_ta"}),
        encoding="utf-8",
    )
    pack_dir = tmp_path / "custom capture pack"
    pack_dir.mkdir()
    manifest = pack_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "capture_type": "ta",
                "entries": [
                    {
                        "fixture": "ta_core_indicators.json",
                        "pine_file": "ta.pine",
                        "bars_file": "bars.csv",
                        "expected_export_file": "export.csv",
                        "plot_titles": ["Close"],
                        "capture_index_title": "Pyne Capture Index",
                        "bar_count": 1,
                        "import_command": (
                            "python import.py --values <export-dir>/export.csv"
                        ),
                        "diff_command": "python diff.py",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ta_capture_next.py"),
            "--golden-dir",
            str(golden_dir),
            "--manifest",
            str(manifest),
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    task = json.loads(completed.stdout)
    pack_text = pack_dir.as_posix()
    assert f'--out-dir "{pack_text}" --clean' in task["prepare_command"]
    assert f'"{pack_text}/manifest.json"' in task["preflight_command"]
    assert f'"{pack_text}/export.csv"' in task["import_command"]
