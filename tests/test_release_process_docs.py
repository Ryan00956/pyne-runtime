from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
PYPROJECT = ROOT / "pyproject.toml"
RELEASE_DOC = ROOT / "docs" / "reference" / "release_process.md"


def test_release_process_documents_version_policy_and_gates() -> None:
    body = RELEASE_DOC.read_text(encoding="utf-8")

    for required in (
        "Patch releases should not break public root imports",
        "Minor releases may add public APIs",
        "Any breaking change must include",
        "scripts/check.ps1",
        "scripts/check.sh",
        "pyne_runtime/py.typed",
        "python -m pyne_runtime schema",
        "CHANGELOG.md",
    ):
        assert required in body


def test_release_process_links_to_contract_docs() -> None:
    body = RELEASE_DOC.read_text(encoding="utf-8")

    for required in (
        "../api/public_api.md",
        "pine_like_api_matrix.md",
        "schema_migrations.md",
        "../../CHANGELOG.md",
    ):
        assert f"]({required})" in body


def test_changelog_tracks_unreleased_and_current_project_version() -> None:
    changelog = CHANGELOG.read_text(encoding="utf-8")
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    version = project["project"]["version"]

    assert "## Unreleased" in changelog
    assert f"## {version}" in changelog


def test_changelog_records_package_maturity_contracts() -> None:
    changelog = CHANGELOG.read_text(encoding="utf-8")

    for required in (
        "schema contracts",
        "schema migration policy",
        "release process guidance",
        "host integration guide",
        "package smoke coverage",
        "py.typed",
    ):
        assert required in changelog
