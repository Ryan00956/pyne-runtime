from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_strategy_capture_next_json_default_priority() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_next.py"),
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    task = json.loads(completed.stdout)
    assert task == {"status": "complete", "message": "no pending capture task"}


def test_strategy_capture_next_uses_manifest(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_prepare.py"),
            "--out-dir",
            str(pack_dir),
        ],
        check=True,
        cwd=ROOT,
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_next.py"),
            "--manifest",
            str(pack_dir / "manifest.json"),
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    task = json.loads(completed.stdout)
    assert task == {"status": "complete", "message": "no pending capture task"}


def test_strategy_capture_next_text_output() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_next.py"),
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "no pending capture task"


def test_strategy_capture_next_all_reports_complete_when_all_cases_are_captured() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_next.py"),
            "--all",
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    task = json.loads(completed.stdout)
    assert task == {"status": "complete", "message": "no pending capture task"}


def test_strategy_capture_next_uses_custom_manifest_parent_in_commands(
    tmp_path: Path,
) -> None:
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    (golden_dir / "strategy_pine_equivalent_smoke.json").write_text(
        json.dumps({"cases": [{"name": "pending_case"}]}),
        encoding="utf-8",
    )
    pack_dir = tmp_path / "custom capture pack"
    pack_dir.mkdir()
    manifest = pack_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "capture_type": "strategy",
                "entries": [
                    {
                        "fixture": "strategy_pine_equivalent_smoke.json",
                        "case": "pending_case",
                        "pine_file": "case.pine",
                        "bars_file": "bars.csv",
                        "expected_export_file": "export.csv",
                        "plot_titles": ["Position"],
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
            str(ROOT / "scripts" / "strategy_capture_next.py"),
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
