"""Import TradingView plot exports into a strategy pine-equivalent fixture."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


IGNORED_CSV_COLUMNS = {
    "",
    "time",
    "timestamp",
    "date",
    "datetime",
    "bar_index",
    "bar index",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import TradingView exported plot values into a strategy fixture.",
    )
    parser.add_argument("fixture", type=Path, help="Path to a strategy fixture JSON file.")
    parser.add_argument("--case", required=True, help="Fixture case name to update.")
    parser.add_argument("--values", required=True, type=Path, help="Path to exported JSON or CSV.")
    parser.add_argument(
        "--format",
        choices=["auto", "json", "csv"],
        default="auto",
        help="Input format for --values.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.0,
        help="Absolute tolerance used by the golden test.",
    )
    parser.add_argument(
        "--note",
        action="append",
        default=[],
        help="Optional capture note. May be repeated.",
    )
    args = parser.parse_args(argv)

    values = load_values(args.values, args.format)
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    case = find_case(fixture, args.case)
    plot_titles = set(case.get("values", {}))
    unknown_titles = sorted(set(values) - plot_titles)
    if unknown_titles:
        raise SystemExit(
            "export contains plot title(s) not present in fixture values: "
            + ", ".join(unknown_titles)
        )

    case["external_capture"] = {
        "provider": "tradingview",
        "status": "captured",
        "tolerance": args.tolerance,
        "values": values,
    }
    if args.note:
        case["external_capture"]["notes"] = args.note

    args.fixture.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"updated {args.fixture}::{args.case} with {len(values)} captured plot(s)")
    return 0


def load_values(path: Path, format_name: str) -> dict[str, list[float | None]]:
    resolved_format = detect_format(path, format_name)
    if resolved_format == "json":
        return load_json_values(path)
    if resolved_format == "csv":
        return load_csv_values(path)
    raise ValueError(f"unsupported values format: {resolved_format}")


def detect_format(path: Path, format_name: str) -> str:
    if format_name != "auto":
        return format_name
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".csv":
        return "csv"
    raise SystemExit("--format is required when --values is not .json or .csv")


def load_json_values(path: Path) -> dict[str, list[float | None]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("values", payload) if isinstance(payload, dict) else None
    if not isinstance(values, dict):
        raise SystemExit("JSON export must be an object or contain a values object")
    return normalize_values(values)


def load_csv_values(path: Path) -> dict[str, list[float | None]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit("CSV export must contain a header row")
        columns = [
            column
            for column in reader.fieldnames
            if column is not None and column.strip().lower() not in IGNORED_CSV_COLUMNS
        ]
        values: dict[str, list[float | None]] = {column: [] for column in columns}
        for row in reader:
            for column in columns:
                values[column].append(parse_scalar(row.get(column, "")))
    return values


def normalize_values(raw_values: dict[str, Any]) -> dict[str, list[float | None]]:
    values: dict[str, list[float | None]] = {}
    for title, series in raw_values.items():
        if not isinstance(title, str):
            raise SystemExit("plot titles must be strings")
        if not isinstance(series, list):
            raise SystemExit(f"plot {title!r} must be a list")
        values[title] = [parse_scalar(value) for value in series]
    return values


def parse_scalar(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    raw = str(value).strip()
    if raw == "" or raw.lower() in {"na", "nan", "null"}:
        return None
    return float(raw)


def find_case(fixture: dict[str, Any], case_name: str) -> dict[str, Any]:
    for case in fixture.get("cases", []):
        if case.get("name") == case_name:
            return case
    raise SystemExit(f"case not found: {case_name}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
