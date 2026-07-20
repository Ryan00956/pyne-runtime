"""Keep the generated evidence block in the current project status document fresh."""
from __future__ import annotations

import argparse
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from request_capture_status import build_report as build_request_report
from strategy_capture_status import build_report as build_strategy_report
from ta_capture_status import build_report as build_ta_report


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCUMENT = ROOT / "docs" / "reference" / "current_status.md"
DEFAULT_GOLDEN_DIR = ROOT / "tests" / "golden"
DEFAULT_PROJECT_FILE = ROOT / "pyproject.toml"
GENERATED_START = "<!-- BEGIN GENERATED PROJECT STATUS -->"
GENERATED_END = "<!-- END GENERATED PROJECT STATUS -->"

ReportBuilder = Callable[[Path], dict[str, Any]]
REPORT_SOURCES: tuple[tuple[str, ReportBuilder, str], ...] = (
    ("Request", build_request_report, "fixtures"),
    ("Strategy", build_strategy_report, "cases"),
    ("TA", build_ta_report, "fixtures"),
)


class ProjectStatusError(ValueError):
    """Raised when the status document or project metadata cannot be updated safely."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify the current project status evidence block.",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--check",
        action="store_true",
        help="Fail when the committed generated block is stale or capture evidence is incomplete.",
    )
    action.add_argument(
        "--write",
        action="store_true",
        help="Replace the generated block with the current repository evidence.",
    )
    parser.add_argument(
        "--document",
        type=Path,
        default=DEFAULT_DOCUMENT,
        help="Status Markdown document containing the generated markers.",
    )
    parser.add_argument(
        "--golden-dir",
        type=Path,
        default=DEFAULT_GOLDEN_DIR,
        help="Directory containing request, strategy, and TA capture fixtures.",
    )
    parser.add_argument(
        "--project-file",
        type=Path,
        default=DEFAULT_PROJECT_FILE,
        help="pyproject.toml used as the package-version source of truth.",
    )
    args = parser.parse_args(argv)

    try:
        summary = build_capture_summary(args.golden_dir)
        version = read_project_version(args.project_file)
        generated_block = render_generated_block(version, summary)

        if not args.check and not args.write:
            print(generated_block)
            return 0

        current_document = read_status_document(args.document)
        expected_document = replace_generated_block(current_document, generated_block)

        if args.write:
            if current_document == expected_document:
                print(f"Project status is already current: {args.document}")
            else:
                args.document.write_text(expected_document, encoding="utf-8")
                print(f"Updated project status: {args.document}")
            return 0

        problems: list[str] = []
        if current_document != expected_document:
            problems.append(
                f"generated block is stale; run `{format_write_command(args.document)}`"
            )
        problems.extend(capture_contract_problems(summary))
        if problems:
            for problem in problems:
                print(f"project status check failed: {problem}", file=sys.stderr)
            return 1

        print(f"Project status is current: {args.document}")
        return 0
    except (OSError, ProjectStatusError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        print(f"project status error: {exc}", file=sys.stderr)
        return 2


def build_capture_summary(golden_dir: Path) -> list[dict[str, Any]]:
    """Build one normalized row from each authoritative capture status report."""
    summary: list[dict[str, Any]] = []
    for name, builder, records_key in REPORT_SOURCES:
        report = builder(golden_dir)
        counts = report["counts"]
        records = report[records_key]
        summary.append(
            {
                "name": name,
                "total": counts["total"],
                "captured": counts["captured"],
                "not_captured": counts["not_captured"],
                "missing": counts["missing"],
                "priority_total": counts["priority_total"],
                "priority_captured": counts["priority_captured"],
                "parity_assertions": sum(
                    record.get("assertion") == "parity" for record in records
                ),
                "non_parity_records": [
                    _record_label(record)
                    for record in records
                    if record.get("assertion") != "parity"
                ],
            }
        )
    return summary


def read_project_version(project_file: Path) -> str:
    """Read the package version from pyproject.toml rather than installed metadata."""
    with project_file.open("rb") as handle:
        project = tomllib.load(handle).get("project")
    if not isinstance(project, dict):
        raise ProjectStatusError(f"missing [project] table in {project_file}")
    version = project.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ProjectStatusError(f"missing project.version in {project_file}")
    return version


def render_generated_block(version: str, summary: list[dict[str, Any]]) -> str:
    """Render the deterministic Markdown block owned by this script."""
    rows = [
        GENERATED_START,
        "<!-- Generated by scripts/project_status.py; do not edit this block by hand. -->",
        "",
        f"Package version from `pyproject.toml`: **{version}**",
        "",
        "| Capture family | Captured | Not captured | Missing | Parity assertions | "
        "Priority captured |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summary:
        rows.append(
            f"| {item['name']} | {item['captured']}/{item['total']} | "
            f"{item['not_captured']} | {item['missing']} | "
            f"{item['parity_assertions']}/{item['total']} | "
            f"{item['priority_captured']}/{item['priority_total']} |"
        )

    total = _sum_summary(summary, "total")
    rows.extend(
        [
            f"| **Total** | **{_sum_summary(summary, 'captured')}/{total}** | "
            f"**{_sum_summary(summary, 'not_captured')}** | "
            f"**{_sum_summary(summary, 'missing')}** | "
            f"**{_sum_summary(summary, 'parity_assertions')}/{total}** | "
            f"**{_sum_summary(summary, 'priority_captured')}/"
            f"{_sum_summary(summary, 'priority_total')}** |",
            "",
            "These counts come directly from the request, strategy, and TA status "
            "`build_report()` functions. `Captured` means checked-in TradingView capture "
            "metadata exists; `parity assertions` means those records are configured for "
            "parity comparison. Numeric comparison is performed by the separate capture-diff "
            "quality gates, so this table does not extend compatibility claims beyond the "
            "listed fixtures and cases.",
            "",
            GENERATED_END,
        ]
    )
    return "\n".join(rows)


def read_status_document(document: Path) -> str:
    if not document.is_file():
        raise ProjectStatusError(f"status document does not exist: {document}")
    return document.read_text(encoding="utf-8")


def replace_generated_block(document: str, generated_block: str) -> str:
    """Replace exactly one complete marker block without touching hand-written prose."""
    if document.count(GENERATED_START) != 1 or document.count(GENERATED_END) != 1:
        raise ProjectStatusError(
            "status document must contain exactly one complete generated marker block"
        )
    start = document.index(GENERATED_START)
    end = document.index(GENERATED_END)
    if end < start:
        raise ProjectStatusError(
            "generated marker order is invalid: END must appear after START"
        )
    end += len(GENERATED_END)
    return f"{document[:start]}{generated_block}{document[end:]}"


def capture_contract_problems(summary: list[dict[str, Any]]) -> list[str]:
    """Return release-gate failures hidden by a captured/total headline alone."""
    problems: list[str] = []
    for item in summary:
        if item["total"] <= 0:
            problems.append(f"{item['name']} capture family has no records")
        if item["priority_total"] <= 0:
            problems.append(f"{item['name']} capture family has no priority records")
        if item["captured"] != item["total"]:
            problems.append(
                f"{item['name']} capture coverage is "
                f"{item['captured']}/{item['total']} (expected complete coverage)"
            )
        if item["parity_assertions"] != item["total"]:
            labels = ", ".join(item["non_parity_records"])
            problems.append(
                f"{item['name']} parity assertions are "
                f"{item['parity_assertions']}/{item['total']}; non-parity records: {labels}"
            )
    return problems


def format_write_command(document: Path) -> str:
    if document.resolve() == DEFAULT_DOCUMENT.resolve():
        return "python scripts/project_status.py --write"
    return f"python scripts/project_status.py --write --document {document}"


def _record_label(record: dict[str, Any]) -> str:
    case = record.get("case")
    if case is not None:
        return f"{record.get('fixture', '<unknown>')}::{case}"
    return str(record.get("fixture", record.get("name", "<unknown>")))


def _sum_summary(summary: list[dict[str, Any]], key: str) -> int:
    return sum(int(item[key]) for item in summary)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
