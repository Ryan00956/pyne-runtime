from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "project_status.py"


def test_committed_project_status_is_current() -> None:
    completed = _run("--check")

    assert completed.returncode == 0, completed.stderr
    assert "Project status is current" in completed.stdout


def test_write_and_check_use_dynamic_build_reports(tmp_path: Path) -> None:
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    _write_minimal_capture_fixtures(golden_dir)
    project_file = tmp_path / "pyproject.toml"
    project_file.write_text('[project]\nversion = "9.8.7"\n', encoding="utf-8")
    document = tmp_path / "current_status.md"
    document.write_text(
        "# Current\n\n"
        "<!-- BEGIN GENERATED PROJECT STATUS -->\n"
        "stale\n"
        "<!-- END GENERATED PROJECT STATUS -->\n\n"
        "Hand-written boundary.\n",
        encoding="utf-8",
    )

    written = _run(
        "--write",
        "--document",
        str(document),
        "--golden-dir",
        str(golden_dir),
        "--project-file",
        str(project_file),
    )

    assert written.returncode == 0, written.stderr
    rendered = document.read_text(encoding="utf-8")
    assert "Package version from `pyproject.toml`: **9.8.7**" in rendered
    assert "| Request | 1/1 | 0 | 0 | 1/1 | 1/1 |" in rendered
    assert "| Strategy | 1/1 | 0 | 0 | 1/1 | 1/1 |" in rendered
    assert "| TA | 1/1 | 0 | 0 | 1/1 | 1/1 |" in rendered
    assert "Hand-written boundary." in rendered

    checked = _run(
        "--check",
        "--document",
        str(document),
        "--golden-dir",
        str(golden_dir),
        "--project-file",
        str(project_file),
    )

    assert checked.returncode == 0, checked.stderr


def test_check_reports_document_drift(tmp_path: Path) -> None:
    document = tmp_path / "current_status.md"
    source = (ROOT / "docs" / "reference" / "current_status.md").read_text(
        encoding="utf-8"
    )
    document.write_text(source.replace("| Request | 21/21", "| Request | 20/21"), encoding="utf-8")

    completed = _run("--check", "--document", str(document))

    assert completed.returncode == 1
    assert "generated block is stale" in completed.stderr
    assert "--write" in completed.stderr


def test_check_rejects_non_parity_capture_even_after_write(tmp_path: Path) -> None:
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    _write_minimal_capture_fixtures(golden_dir, request_assertion="reference")
    document = tmp_path / "current_status.md"
    document.write_text(
        "<!-- BEGIN GENERATED PROJECT STATUS -->\n"
        "stale\n"
        "<!-- END GENERATED PROJECT STATUS -->\n",
        encoding="utf-8",
    )

    written = _run(
        "--write",
        "--document",
        str(document),
        "--golden-dir",
        str(golden_dir),
    )
    assert written.returncode == 0, written.stderr

    checked = _run(
        "--check",
        "--document",
        str(document),
        "--golden-dir",
        str(golden_dir),
    )

    assert checked.returncode == 1
    assert "Request parity assertions are 0/1" in checked.stderr
    assert "request_security_htf_capture.json" in checked.stderr


def test_check_rejects_empty_capture_family_even_after_write(tmp_path: Path) -> None:
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    _write_minimal_capture_fixtures(golden_dir, include_request=False)
    document = _write_marker_document(tmp_path)

    written = _run(
        "--write",
        "--document",
        str(document),
        "--golden-dir",
        str(golden_dir),
    )
    assert written.returncode == 0, written.stderr

    checked = _run(
        "--check",
        "--document",
        str(document),
        "--golden-dir",
        str(golden_dir),
    )

    assert checked.returncode == 1
    assert "Request capture family has no records" in checked.stderr


def test_check_rejects_family_without_priority_records(tmp_path: Path) -> None:
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    _write_minimal_capture_fixtures(
        golden_dir,
        request_filename="request_security_non_priority_capture.json",
    )
    document = _write_marker_document(tmp_path)

    written = _run(
        "--write",
        "--document",
        str(document),
        "--golden-dir",
        str(golden_dir),
    )
    assert written.returncode == 0, written.stderr

    checked = _run(
        "--check",
        "--document",
        str(document),
        "--golden-dir",
        str(golden_dir),
    )

    assert checked.returncode == 1
    assert "Request capture family has no priority records" in checked.stderr


def test_check_rejects_reversed_generated_markers(tmp_path: Path) -> None:
    document = tmp_path / "current_status.md"
    document.write_text(
        "<!-- END GENERATED PROJECT STATUS -->\n"
        "stale\n"
        "<!-- BEGIN GENERATED PROJECT STATUS -->\n",
        encoding="utf-8",
    )

    checked = _run("--check", "--document", str(document))

    assert checked.returncode == 2
    assert "generated marker order is invalid" in checked.stderr
    assert "END must appear after START" in checked.stderr


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_minimal_capture_fixtures(
    golden_dir: Path,
    *,
    request_assertion: str = "parity",
    include_request: bool = True,
    request_filename: str = "request_security_htf_capture.json",
) -> None:
    request = {
        "name": "request",
        "external_capture": {
            "provider": "tradingview",
            "status": "captured",
            "assertion": request_assertion,
            "series": {"close": [1.0]},
        },
    }
    strategy = {
        "cases": [
            {
                "name": "strategy",
                "external_capture": {
                    "provider": "tradingview",
                    "status": "captured",
                    "assertion": "parity",
                    "values": {"position": [0.0]},
                },
            }
        ]
    }
    ta = {
        "name": "ta",
        "external_capture": {
            "provider": "tradingview",
            "status": "captured",
            "assertion": "parity",
            "series": {"sma": [1.0]},
        },
    }
    fixtures = {
        "strategy_pine_equivalent_smoke.json": strategy,
        "ta_core_indicators.json": ta,
    }
    if include_request:
        fixtures[request_filename] = request
    for name, payload in fixtures.items():
        (golden_dir / name).write_text(json.dumps(payload), encoding="utf-8")


def _write_marker_document(tmp_path: Path) -> Path:
    document = tmp_path / "current_status.md"
    document.write_text(
        "<!-- BEGIN GENERATED PROJECT STATUS -->\n"
        "stale\n"
        "<!-- END GENERATED PROJECT STATUS -->\n",
        encoding="utf-8",
    )
    return document
