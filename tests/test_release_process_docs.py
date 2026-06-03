from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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
    ):
        assert required in body


def test_release_process_links_to_contract_docs() -> None:
    body = RELEASE_DOC.read_text(encoding="utf-8")

    for required in (
        "../api/public_api.md",
        "pine_like_api_matrix.md",
        "schema_migrations.md",
    ):
        assert f"]({required})" in body
