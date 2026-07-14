from __future__ import annotations

import json
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "capture_clean.py"


@pytest.mark.parametrize(
    "relative_target",
    [
        ".git",
        "docs",
        "scripts",
        "src",
        "src/pyne_runtime",
        "tests",
        "tests/golden",
    ],
)
def test_capture_clean_guard_rejects_critical_repo_paths(relative_target: str) -> None:
    module = _load_capture_clean()

    with pytest.raises(SystemExit, match="refusing to clean protected directory"):
        module.ensure_safe_capture_clean_target(
            ROOT / relative_target,
            ROOT / "tests" / "golden",
            capture_type="request",
        )


@pytest.mark.parametrize("target", [ROOT, ROOT.parent])
def test_capture_clean_guard_rejects_repo_and_ancestor(target: Path) -> None:
    module = _load_capture_clean()

    with pytest.raises(SystemExit, match="refusing to clean protected directory"):
        module.ensure_safe_capture_clean_target(
            target,
            ROOT / "tests" / "golden",
            capture_type="ta",
        )


def test_capture_clean_guard_rejects_unmarked_nonempty_directory(tmp_path: Path) -> None:
    module = _load_capture_clean()
    output = tmp_path / "not-a-capture-pack"
    output.mkdir()
    keep = output / "keep.txt"
    keep.write_text("keep", encoding="utf-8")

    with pytest.raises(SystemExit, match="no readable capture manifest"):
        module.ensure_safe_capture_clean_target(
            output,
            ROOT / "tests" / "golden",
            capture_type="strategy",
        )

    assert keep.read_text(encoding="utf-8") == "keep"


def test_capture_clean_guard_accepts_matching_output_manifest(tmp_path: Path) -> None:
    module = _load_capture_clean()
    output = tmp_path / "capture-pack"
    output.mkdir()
    (output / "manifest.json").write_text(
        json.dumps({"capture_type": "request", "entries": []}),
        encoding="utf-8",
    )

    assert module.ensure_safe_capture_clean_target(
        output,
        ROOT / "tests" / "golden",
        capture_type="request",
    ) is True


def test_capture_clean_guard_preserves_empty_directory(tmp_path: Path) -> None:
    module = _load_capture_clean()
    output = tmp_path / "empty-capture-pack"
    output.mkdir()

    assert module.ensure_safe_capture_clean_target(
        output,
        ROOT / "tests" / "golden",
        capture_type="request",
    ) is False
    assert output.is_dir()


def test_capture_clean_guard_rejects_different_capture_pack_type(
    tmp_path: Path,
) -> None:
    module = _load_capture_clean()
    output = tmp_path / "request-capture-pack"
    output.mkdir()
    manifest = output / "manifest.json"
    manifest.write_text(
        json.dumps({"capture_type": "request", "entries": []}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="not a 'ta' output pack"):
        module.ensure_safe_capture_clean_target(
            output,
            ROOT / "tests" / "golden",
            capture_type="ta",
        )

    assert manifest.exists()


@pytest.mark.parametrize(
    "prepare_script",
    [
        "request_capture_prepare.py",
        "ta_capture_prepare.py",
        "strategy_capture_prepare.py",
    ],
)
def test_all_capture_prepare_commands_refuse_repo_root(prepare_script: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / prepare_script),
            "--out-dir",
            str(ROOT),
            "--clean",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "refusing to clean protected directory" in completed.stderr


@pytest.mark.parametrize(
    ("prepare_script", "capture_type"),
    [
        ("request_capture_prepare.py", "request"),
        ("ta_capture_prepare.py", "ta"),
        ("strategy_capture_prepare.py", "strategy"),
    ],
)
def test_capture_prepare_cleans_its_own_temp_output_pack(
    tmp_path: Path,
    prepare_script: str,
    capture_type: str,
) -> None:
    output = tmp_path / f"{capture_type}-capture-pack"
    command = [
        sys.executable,
        str(ROOT / "scripts" / prepare_script),
        "--out-dir",
        str(output),
    ]
    subprocess.run(command, check=True, cwd=ROOT, capture_output=True, text=True)
    stale = output / "stale.txt"
    stale.write_text("remove me", encoding="utf-8")

    subprocess.run(
        [*command, "--clean"],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["capture_type"] == capture_type
    assert not stale.exists()


@pytest.mark.parametrize(
    ("prepare_script", "capture_type"),
    [
        ("request_capture_prepare.py", "request"),
        ("ta_capture_prepare.py", "ta"),
        ("strategy_capture_prepare.py", "strategy"),
    ],
)
def test_capture_prepare_reuses_existing_empty_output_directory(
    tmp_path: Path,
    prepare_script: str,
    capture_type: str,
) -> None:
    output = tmp_path / f"empty-{capture_type}-capture-pack"
    output.mkdir()
    original_inode = output.stat().st_ino

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / prepare_script),
            "--out-dir",
            str(output),
            "--clean",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["capture_type"] == capture_type
    assert output.stat().st_ino == original_inode


def _load_capture_clean() -> ModuleType:
    spec = spec_from_file_location("capture_clean", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
