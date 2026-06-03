from __future__ import annotations

import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "package_smoke.py"


def test_package_smoke_help() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--dist-dir" in result.stdout
    assert "--repo-root" in result.stdout


def test_package_smoke_finds_built_wheel(tmp_path: Path) -> None:
    module = _load_package_smoke()
    old_wheel = tmp_path / "pyne_runtime-0.1.0-py3-none-any.whl"
    new_wheel = tmp_path / "pyne_runtime-0.2.0-py3-none-any.whl"
    old_wheel.write_text("", encoding="utf-8")
    new_wheel.write_text("", encoding="utf-8")

    assert module._find_wheel(tmp_path) == new_wheel


def _load_package_smoke() -> ModuleType:
    spec = spec_from_file_location("package_smoke", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
