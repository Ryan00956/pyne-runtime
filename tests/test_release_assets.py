from __future__ import annotations

import hashlib
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_assets.py"


def test_release_assets_accepts_exact_non_empty_artifacts_and_writes_hashes(
    tmp_path: Path,
) -> None:
    module = _load_release_assets()
    wheel = tmp_path / "pyne_runtime-0.2.0rc1-py3-none-any.whl"
    sdist = tmp_path / "pyne_runtime-0.2.0rc1.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")

    artifacts = module._validate_artifacts(tmp_path, "0.2.0rc1")
    checksums = module._write_checksums(tmp_path, artifacts)

    assert artifacts == (wheel, sdist)
    assert checksums.read_text(encoding="utf-8").splitlines() == [
        f"{hashlib.sha256(wheel.read_bytes()).hexdigest()}  {wheel.name}",
        f"{hashlib.sha256(sdist.read_bytes()).hexdigest()}  {sdist.name}",
    ]


def test_release_assets_rejects_tag_version_mismatch() -> None:
    module = _load_release_assets()

    with pytest.raises(RuntimeError, match="does not match package version"):
        module._validate_tag("v0.2.0", "0.2.0rc1")


def test_release_assets_rejects_missing_unexpected_or_empty_files(tmp_path: Path) -> None:
    module = _load_release_assets()
    wheel = tmp_path / "pyne_runtime-0.2.0rc1-py3-none-any.whl"
    wheel.write_bytes(b"")
    (tmp_path / "old.whl").write_bytes(b"old")

    with pytest.raises(RuntimeError, match=r"missing: .*tar.gz; unexpected: old.whl"):
        module._validate_artifacts(tmp_path, "0.2.0rc1")

    (tmp_path / "old.whl").unlink()
    (tmp_path / "pyne_runtime-0.2.0rc1.tar.gz").write_bytes(b"sdist")
    with pytest.raises(RuntimeError, match="must not be empty"):
        module._validate_artifacts(tmp_path, "0.2.0rc1")


def test_release_assets_extracts_only_matching_changelog_section(tmp_path: Path) -> None:
    module = _load_release_assets()
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n"
        "## Unreleased\n\n"
        "## 0.2.0rc1 - 2026-07-20\n\n"
        "- Release candidate.\n\n"
        "## 0.1.0\n\n"
        "- Initial release.\n",
        encoding="utf-8",
    )

    assert module._release_notes(changelog, "0.2.0rc1") == "- Release candidate.\n"


def _load_release_assets() -> ModuleType:
    spec = spec_from_file_location("release_assets", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
