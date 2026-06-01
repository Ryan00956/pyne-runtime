"""Prepare TradingView Pine scripts and a capture manifest for TA fixtures."""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any

from ta_capture_status import DEFAULT_GOLDEN_DIR, PRIORITY_FIXTURES, TA_FIXTURE_GLOB


CAPTURE_INDEX_TITLE = "Pyne Capture Index"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write Pine scripts and a manifest for TradingView TA capture.",
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
        help="Include all TA golden fixtures instead of priority fixtures only.",
    )
    parser.add_argument(
        "--fixture",
        action="append",
        default=[],
        help="Only include a named fixture file. May be repeated.",
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
        fixture_filter=set(args.fixture),
    )
    manifest = {
        "capture_type": "ta",
        "default_scope": "all" if args.all else "priority",
        "fixture_count": len(entries),
        "entries": entries,
    }
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.out_dir / "README.md").write_text(render_readme(entries), encoding="utf-8")
    print(f"prepared {len(entries)} TA capture script(s) in {args.out_dir}")
    return 0


def prepare_capture_files(
    *,
    golden_dir: Path,
    out_dir: Path,
    include_all: bool,
    fixture_filter: set[str],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    fixture_paths = sorted(golden_dir.glob(TA_FIXTURE_GLOB), key=fixture_sort_key)
    for fixture_path in fixture_paths:
        if not include_all and fixture_path.name not in PRIORITY_FIXTURES:
            continue
        if fixture_filter and fixture_path.name not in fixture_filter:
            continue
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        entry = build_entry(fixture_path, fixture, len(entries) + 1)
        (out_dir / entry["pine_file"]).write_text(
            render_capture_pine(fixture).rstrip() + "\n",
            encoding="utf-8",
        )
        write_bars_csv(out_dir / entry["bars_file"], fixture.get("chart_bars", []))
        entries.append(entry)
    return entries


def build_entry(fixture_path: Path, fixture: dict[str, Any], index: int) -> dict[str, Any]:
    fixture_name = fixture_path.name
    capture = fixture.get("external_capture", {})
    diff_assertion = capture_diff_assertion(capture)
    pine_file = f"{index:02d}_{slugify(fixture_path.stem)}.pine"
    bars_file = f"{Path(pine_file).stem}_bars.csv"
    export_file = f"{Path(pine_file).stem}.csv"
    return {
        "fixture": fixture_name,
        "name": fixture.get("name", fixture_path.stem),
        "priority": fixture_name in PRIORITY_FIXTURES,
        "status": capture.get("status", "missing"),
        "pine_file": pine_file,
        "bars_file": bars_file,
        "expected_export_file": export_file,
        "time_alignment_required": False,
        "bar_count": len(fixture.get("chart_bars", [])),
        "plot_titles": list(fixture.get("expected_series", {})),
        "capture_index_title": CAPTURE_INDEX_TITLE,
        "import_command": (
            "python scripts/ta_capture_import.py "
            f"tests/golden/{fixture_name} "
            f"--values <export-dir>/{export_file} "
            '--tolerance 1e-9 --note "TradingView export YYYY-MM-DD"'
        ),
        "diff_command": (
            "python scripts/ta_capture_diff.py "
            f"--assertion {diff_assertion} tests/golden/{fixture_name}"
        ),
    }


def capture_diff_assertion(capture: dict[str, Any]) -> str:
    if capture.get("status") == "captured":
        return capture.get("assertion", "parity")
    return "reference"


def render_capture_pine(fixture: dict[str, Any]) -> str:
    name = str(fixture.get("name", "TA Capture")).replace("_", " ").title()
    lines = [
        "//@version=5",
        f"_pyne_capture_bars = {len(fixture.get('chart_bars', []))}",
        '_pyne_capture_use_last_bars = input.bool(true, "Pyne capture: use last chart bars")',
        '_pyne_capture_start_time = input.int(1704067200000, "Pyne capture: start time (ms)")',
        "_pyne_capture_start_hit = time >= _pyne_capture_start_time and (na(time[1]) or time[1] < _pyne_capture_start_time)",
        "_pyne_capture_from_time = ta.barssince(_pyne_capture_start_hit)",
        "_pyne_capture_from_last = bar_index - (last_bar_index - _pyne_capture_bars)",
        "_pyne_capture_index = _pyne_capture_use_last_bars ? _pyne_capture_from_last : _pyne_capture_from_time",
        "_pyne_capture_active = _pyne_capture_index >= 0 and _pyne_capture_index < _pyne_capture_bars",
        f'indicator("Pyne TA Capture - {name}")',
        "_pyne_open = _pyne_capture_active ? open : na",
        "_pyne_high = _pyne_capture_active ? high : na",
        "_pyne_low = _pyne_capture_active ? low : na",
        "_pyne_close = _pyne_capture_active ? close : na",
        "_pyne_volume = _pyne_capture_active ? volume : na",
        f'plot(_pyne_capture_active ? _pyne_capture_index : na, "{CAPTURE_INDEX_TITLE}")',
    ]
    for line in fixture.get("script", "").splitlines():
        translated = translate_script_line(line)
        if translated:
            lines.append(translated)
    return "\n".join(lines)


def translate_script_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""
    plot = parse_plot_call(stripped, "plot")
    if plot is not None:
        expression, title = plot
        return f'plot(_pyne_capture_active ? ({replace_sources(expression)}) : na, "{title}")'
    bar = parse_plot_call(stripped, "bar")
    if bar is not None:
        expression, title = bar
        return (
            f'plot(_pyne_capture_active ? ({replace_sources(expression)}) : na, '
            f'"{title}", style=plot.style_columns)'
        )
    return translate_assignment(replace_sources(stripped))


def parse_plot_call(line: str, function_name: str) -> tuple[str, str] | None:
    match = re.fullmatch(rf'{function_name}\((.*),\s*"([^"]+)"\)', line)
    if match is None:
        return None
    return match.group(1).strip(), match.group(2)


def translate_assignment(line: str) -> str:
    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)+)\s*=", line)
    if match is None:
        return line
    names = ", ".join(part.strip() for part in match.group(1).split(","))
    return "[" + names + "]" + line[match.end(1):]


def replace_sources(expression: str) -> str:
    replacements = {
        "open": "_pyne_open",
        "high": "_pyne_high",
        "low": "_pyne_low",
        "close": "_pyne_close",
        "volume": "_pyne_volume",
    }
    updated = expression
    for source, replacement in replacements.items():
        updated = re.sub(rf"\b{source}\b", replacement, updated)
    return updated


def write_bars_csv(path: Path, bars: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["time", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        for bar in bars:
            writer.writerow(
                {
                    "time": bar["time"],
                    "open": bar["open"],
                    "high": bar["high"],
                    "low": bar["low"],
                    "close": bar["close"],
                    "volume": bar.get("volume", 0.0),
                }
            )


def render_readme(entries: list[dict[str, Any]]) -> str:
    lines = [
        "# TradingView TA Capture Export Pack",
        "",
        "Copy each `.pine` file into TradingView Pine Editor, export the declared plots,",
        "then import the CSV back into the matching TA golden fixture.",
        "",
        f"Keep the `{CAPTURE_INDEX_TITLE}` plot in the export. It marks the capture window",
        "so early TA warm-up bars that have no indicator value are still imported as bars.",
        "",
        "## Fixtures",
        "",
        "| # | Fixture | Pine file | Bars file | Plots | Bars |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for index, entry in enumerate(entries, start=1):
        plots = ", ".join(f"`{title}`" for title in entry["plot_titles"])
        lines.append(
            f"| {index} | `{entry['fixture']}` | `{entry['pine_file']}` | "
            f"`{entry['bars_file']}` | {plots} | {entry['bar_count']} |"
        )
    lines.extend(
        [
            "",
            "## Next Task",
            "",
            "```powershell",
            "python scripts/ta_capture_next.py --manifest <pack-dir>/manifest.json",
            "python scripts/ta_capture_next.py --manifest <pack-dir>/manifest.json --json",
            "```",
            "",
            "## Preflight / Import / Diff",
            "",
            "```powershell",
            "python scripts/ta_capture_preflight.py <pack-dir>/manifest.json",
            "python scripts/ta_capture_import.py tests/golden/<fixture>.json --values <export.csv> --tolerance 1e-9 --note \"TradingView export YYYY-MM-DD\"",
            "python scripts/ta_capture_diff.py --assertion reference tests/golden/<fixture>.json",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def ensure_safe_clean_target(out_dir: Path, golden_dir: Path) -> None:
    resolved_out = out_dir.resolve()
    resolved_golden = golden_dir.resolve()
    if resolved_out == resolved_golden or resolved_golden in resolved_out.parents:
        raise SystemExit(f"refusing to clean golden fixture directory: {out_dir}")


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return slug or "capture"


def fixture_sort_key(path: Path) -> tuple[int, str]:
    try:
        priority = PRIORITY_FIXTURES.index(path.name)
    except ValueError:
        priority = len(PRIORITY_FIXTURES)
    return priority, path.name


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
