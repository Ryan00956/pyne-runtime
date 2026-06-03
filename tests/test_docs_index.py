from __future__ import annotations

import re
from pathlib import Path


DOCS_ROOT = Path(__file__).resolve().parents[1] / "docs"
INDEX = DOCS_ROOT / "index.md"
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")
PUBLIC_DOC_DIRS = ("api", "concepts", "reference", "tutorials")


def test_docs_index_links_exist() -> None:
    body = INDEX.read_text(encoding="utf-8")
    missing: list[str] = []

    for raw_target in LINK_RE.findall(body):
        if "://" in raw_target:
            continue
        target = (INDEX.parent / raw_target).resolve()
        if not target.exists():
            missing.append(raw_target)

    assert missing == []


def test_docs_index_covers_key_user_paths() -> None:
    body = INDEX.read_text(encoding="utf-8")

    for required in (
        "quickstart.md",
        "tutorials/host_integration_guide.md",
        "tutorials/pine_to_pyne_cookbook.md",
        "api/public_api.md",
        "api/request.md",
        "reference/output_schema.md",
        "reference/schema_migrations.md",
        "../CHANGELOG.md",
        "reference/release_process.md",
        "development/quality_gates.md",
    ):
        assert f"({required})" in body


def test_docs_index_covers_public_documentation_pages() -> None:
    body = INDEX.read_text(encoding="utf-8")

    for directory in PUBLIC_DOC_DIRS:
        for path in sorted((DOCS_ROOT / directory).glob("*.md")):
            target = path.relative_to(DOCS_ROOT).as_posix()
            assert f"({target})" in body
