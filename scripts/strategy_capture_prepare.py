"""Prepare TradingView Pine scripts and a capture manifest for strategy fixtures."""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any

from strategy_capture_status import (
    DEFAULT_GOLDEN_DIR,
    PRIORITY_FIXTURES,
    STRATEGY_FIXTURE_GLOB,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write Pine scripts and a manifest for TradingView strategy capture.",
    )
    parser.add_argument(
        "--golden-dir",
        type=Path,
        default=DEFAULT_GOLDEN_DIR,
        help="Directory containing golden fixture JSON files.",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="Directory where Pine scripts and manifest files are written.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include all strategy pine-equivalent cases instead of priority cases only.",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Only include a named case. May be repeated.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove the output directory before writing new files.",
    )
    args = parser.parse_args(argv)

    if args.clean and args.out_dir.exists():
        ensure_safe_clean_target(args.out_dir, args.golden_dir)
        shutil.rmtree(args.out_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    entries = prepare_capture_files(
        golden_dir=args.golden_dir,
        out_dir=args.out_dir,
        include_all=args.all,
        case_filter=set(args.case),
    )
    manifest = {
        "default_scope": "all" if args.all else "priority",
        "case_count": len(entries),
        "entries": entries,
    }
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.out_dir / "README.md").write_text(render_readme(entries), encoding="utf-8")
    print(f"prepared {len(entries)} capture script(s) in {args.out_dir}")
    return 0


def prepare_capture_files(
    *,
    golden_dir: Path,
    out_dir: Path,
    include_all: bool,
    case_filter: set[str],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    fixture_paths = sorted(golden_dir.glob(STRATEGY_FIXTURE_GLOB), key=fixture_sort_key)
    for fixture_path in fixture_paths:
        if not include_all and fixture_path.name not in PRIORITY_FIXTURES:
            continue
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        for case in fixture.get("cases", []):
            case_name = case["name"]
            if case_filter and case_name not in case_filter:
                continue
            entry = build_entry(fixture_path, case, len(entries) + 1)
            pine_path = out_dir / entry["pine_file"]
            pine_path.parent.mkdir(parents=True, exist_ok=True)
            pine_path.write_text(case["pine_equivalent"].rstrip() + "\n", encoding="utf-8")
            write_bars_csv(out_dir / entry["bars_file"], case.get("bars", []))
            entries.append(entry)
    return entries


def build_entry(fixture_path: Path, case: dict[str, Any], index: int) -> dict[str, Any]:
    fixture_name = fixture_path.name
    case_name = case["name"]
    capture = case.get("external_capture", {})
    pine_file = f"{index:02d}_{slugify(fixture_path.stem)}__{slugify(case_name)}.pine"
    bars_file = f"{Path(pine_file).stem}_bars.csv"
    export_file = f"{Path(pine_file).stem}.csv"
    return {
        "fixture": fixture_name,
        "case": case_name,
        "priority": fixture_name in PRIORITY_FIXTURES,
        "status": capture.get("status", "missing"),
        "pine_file": pine_file,
        "bars_file": bars_file,
        "expected_export_file": export_file,
        "bar_count": len(case.get("bars", [])),
        "plot_titles": list(case.get("values", {})),
        "import_command": (
            "python scripts/strategy_capture_import.py "
            f"tests/golden/{fixture_name} "
            f"--case {case_name} "
            f"--values <export-dir>/{export_file} "
            '--tolerance 1e-9 --note "TradingView export YYYY-MM-DD"'
        ),
        "diff_command": (
            f"python scripts/strategy_capture_diff.py tests/golden/{fixture_name} "
            f"--case {case_name}"
        ),
    }


def render_readme(entries: list[dict[str, Any]]) -> str:
    lines = [
        "# TradingView Strategy Capture Export Pack",
        "",
        "Copy each `.pine` file into TradingView Pine Editor, align the chart data with",
        "the matching `_bars.csv`, export the declared plots, then import the CSV/JSON",
        "back into the matching fixture.",
        "",
        "## Cases",
        "",
        "| # | Fixture | Case | Pine file | Bars file | Plots | Bars |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, entry in enumerate(entries, start=1):
        plots = ", ".join(f"`{title}`" for title in entry["plot_titles"])
        lines.append(
            f"| {index} | `{entry['fixture']}` | `{entry['case']}` | "
            f"`{entry['pine_file']}` | `{entry['bars_file']}` | "
            f"{plots} | {entry['bar_count']} |"
        )
    lines.extend(
        [
            "",
            "## Next Task",
            "",
            "To see the next pending capture task and its commands, run:",
            "",
            "```powershell",
            "python scripts/strategy_capture_next.py --manifest <pack-dir>/manifest.json",
            "python scripts/strategy_capture_next.py --manifest <pack-dir>/manifest.json --json",
            "```",
            "",
            "## Preflight",
            "",
            "After placing TradingView exports next to this manifest, run:",
            "",
            "```powershell",
            "python scripts/strategy_capture_preflight.py <pack-dir>/manifest.json",
            "```",
            "",
            "## Import Pattern",
            "",
            "```powershell",
            "python scripts/strategy_capture_import.py `",
            "  tests/golden/<fixture>.json `",
            "  --case <case_name> `",
            "  --values <export.csv> `",
            "  --tolerance 1e-9 `",
            '  --note "TradingView export YYYY-MM-DD, symbol/timeframe/source"',
            "```",
            "",
            "After importing, run:",
            "",
            "```powershell",
            "python scripts/strategy_capture_diff.py",
            "python -m pytest tests/test_golden_strategy.py -q",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def fixture_sort_key(path: Path) -> tuple[int, str]:
    try:
        priority = PRIORITY_FIXTURES.index(path.name)
    except ValueError:
        priority = len(PRIORITY_FIXTURES)
    return priority, path.name


def write_bars_csv(path: Path, bars: list[dict[str, Any]]) -> None:
    fieldnames = ["time", "open", "high", "low", "close", "volume"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for bar in bars:
            writer.writerow({field: bar.get(field, "") for field in fieldnames})


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return slug or "case"


def ensure_safe_clean_target(out_dir: Path, golden_dir: Path) -> None:
    target = out_dir.resolve()
    cwd = Path.cwd().resolve()
    protected = {
        cwd,
        cwd.parent,
        golden_dir.resolve(),
        golden_dir.resolve().parent,
    }
    if target in protected:
        raise SystemExit(f"refusing to clean protected directory: {out_dir}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
