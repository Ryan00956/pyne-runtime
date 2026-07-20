from __future__ import annotations

import re
from pathlib import Path

import pyne_runtime as pn


DOCS_ROOT = Path(__file__).resolve().parents[1] / "docs"
ROOT = DOCS_ROOT.parent
INDEX = DOCS_ROOT / "index.md"
README = ROOT / "README.md"
PUBLIC_API_DOC = DOCS_ROOT / "api" / "public_api.md"
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)")
ROOT_EXPORT_RE = re.compile(r"\bpn\.([A-Za-z_][A-Za-z0-9_]*)\b")
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
        "reference/current_status.md",
        "../examples/README.md",
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


def test_readme_and_historical_plans_route_to_current_status() -> None:
    assert "(docs/reference/current_status.md)" in README.read_text(encoding="utf-8")

    historical_pages = (
        "architecture_execution_plan_zh.md",
        "code_review_execution_plan_zh.md",
        "non_strategy_capture_plan_zh.md",
        "pine_like_phase_execution_plan_zh.md",
        "pine_like_semantics_progress_zh.md",
        "pine_semantics_execution_plan_zh.md",
        "request_security_expression_thunks_plan_zh.md",
        "tradingview_capture_next_phase_zh.md",
        "tradingview_strategy_parity_execution_zh.md",
    )
    for filename in historical_pages:
        body = (DOCS_ROOT / "development" / filename).read_text(encoding="utf-8")
        assert "../reference/current_status.md" in body
        assert "历史" in body


def test_docs_index_covers_public_documentation_pages() -> None:
    body = INDEX.read_text(encoding="utf-8")

    for directory in PUBLIC_DOC_DIRS:
        for path in sorted((DOCS_ROOT / directory).glob("*.md")):
            target = path.relative_to(DOCS_ROOT).as_posix()
            assert f"({target})" in body


def test_public_api_doc_covers_root_exports() -> None:
    body = PUBLIC_API_DOC.read_text(encoding="utf-8")
    documented_exports = set(ROOT_EXPORT_RE.findall(body))

    missing = sorted(set(pn.__all__) - documented_exports)

    assert missing == []
