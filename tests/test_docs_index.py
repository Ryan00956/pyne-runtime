from __future__ import annotations

import re
from pathlib import Path


DOCS_ROOT = Path(__file__).resolve().parents[1] / "docs"
INDEX = DOCS_ROOT / "index.md"
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")


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
        "tutorials/pine_to_pyne_cookbook.md",
        "api/public_api.md",
        "api/request.md",
        "reference/output_schema.md",
        "reference/schema_migrations.md",
        "development/quality_gates.md",
    ):
        assert f"({required})" in body
