"""Import TradingView plot exports into a request.security golden fixture."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from request_capture_prepare import CAPTURE_INDEX_TITLE
from strategy_capture_import import parse_scalar


CHART_CSV_COLUMNS = {
    "",
    "time",
    "timestamp",
    "date",
    "datetime",
    "bar_index",
    "bar index",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "Volume",
}
PROVIDER_FIELDS = ("time", "open", "high", "low", "close", "volume")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import TradingView exported plot values into a request fixture.",
    )
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--values", required=True, type=Path)
    parser.add_argument("--tolerance", type=float, default=0.0)
    parser.add_argument("--assertion", choices=["reference", "parity"], default="reference")
    parser.add_argument("--note", action="append", default=[])
    args = parser.parse_args(argv)

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    export = load_csv_capture(args.values, fixture)
    validate_capture_series(fixture, export["series"])

    previous_capture = fixture.get("external_capture", {})
    capture = {
        "provider": "tradingview",
        "status": "captured",
        "assertion": args.assertion,
        "tolerance": args.tolerance,
        "series": export["series"],
        "bars": export["bars"],
        "provider_bars": export["provider_bars"],
    }
    if "provider_bar_plots" in previous_capture:
        capture["provider_bar_plots"] = previous_capture["provider_bar_plots"]
    if args.note:
        capture["notes"] = args.note
    fixture["external_capture"] = capture

    args.fixture.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"updated {args.fixture} with {len(export['series'])} captured plot(s) "
        f"and {len(export['provider_bars'])} provider bar(s)"
    )
    return 0


def load_csv_capture(path: Path, fixture: dict[str, Any]) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise SystemExit("CSV export must contain a header row")
        fieldnames = [field for field in reader.fieldnames if field is not None]
        if CAPTURE_INDEX_TITLE not in fieldnames:
            raise SystemExit(f"CSV export missing capture index column: {CAPTURE_INDEX_TITLE}")
        plot_titles = list(fixture.get("expected_series", {}))
        missing_titles = sorted(set(plot_titles) - set(fieldnames))
        if missing_titles:
            raise SystemExit("CSV export missing plot title(s): " + ", ".join(missing_titles))
        unknown_titles = sorted(
            set(field for field in fieldnames if not is_chart_csv_column(field))
            - set(plot_titles)
            - {CAPTURE_INDEX_TITLE}
        )
        if unknown_titles:
            raise SystemExit("CSV export contains unknown plot title(s): " + ", ".join(unknown_titles))
        rows = [
            row for row in reader
            if (row.get(CAPTURE_INDEX_TITLE, "") or "").strip()
        ]

    expected_length = len(fixture.get("chart_bars", []))
    if len(rows) != expected_length:
        raise SystemExit(
            f"capture index row count must match fixture bar count {expected_length}; got {len(rows)}"
        )

    bars = [parse_chart_bar(row) for row in rows]
    series: dict[str, list[dict[str, Any]]] = {title: [] for title in plot_titles}
    for row, bar in zip(rows, bars):
        for title in plot_titles:
            value = parse_scalar(row.get(title, ""))
            if value is not None:
                series[title].append({"time": bar["time"], "value": value})
    return {
        "series": series,
        "bars": bars,
        "provider_bars": build_provider_bars(fixture, series),
    }


def parse_chart_bar(row: dict[str, str]) -> dict[str, Any]:
    required = ["time", "open", "high", "low", "close"]
    missing = [field for field in required if not (row.get(field, "") or "").strip()]
    if missing:
        raise SystemExit("CSV export missing chart column(s): " + ", ".join(missing))
    return {
        "time": int(float(row["time"])),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row.get("Volume") or row.get("volume") or 0.0),
    }


def build_provider_bars(
    fixture: dict[str, Any],
    series: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    mapping = fixture.get("external_capture", {}).get("provider_bar_plots", {})
    missing_fields = [field for field in PROVIDER_FIELDS if field not in mapping]
    if missing_fields:
        raise SystemExit(
            "request fixture missing provider_bar_plots field(s): "
            + ", ".join(missing_fields)
        )

    by_chart_time = {
        field: {point["time"]: point["value"] for point in series.get(mapping[field], [])}
        for field in PROVIDER_FIELDS
    }
    provider_bars: list[dict[str, Any]] = []
    seen_provider_times: set[int] = set()
    for chart_time in sorted(by_chart_time["time"]):
        provider_time = normalize_provider_time(
            float(by_chart_time["time"][chart_time]),
            chart_time,
        )
        if provider_time in seen_provider_times:
            continue
        missing = [
            field for field in PROVIDER_FIELDS if chart_time not in by_chart_time[field]
        ]
        if missing:
            raise SystemExit(
                "provider bar plot values missing field(s) at chart time "
                f"{chart_time}: " + ", ".join(missing)
            )
        seen_provider_times.add(provider_time)
        provider_bars.append(
            {
                "time": provider_time,
                "open": float(by_chart_time["open"][chart_time]),
                "high": float(by_chart_time["high"][chart_time]),
                "low": float(by_chart_time["low"][chart_time]),
                "close": float(by_chart_time["close"][chart_time]),
                "volume": float(by_chart_time["volume"][chart_time]),
            }
        )
    return provider_bars


def normalize_provider_time(raw_provider_time: float, chart_time: int) -> int:
    provider_time = int(raw_provider_time)
    if abs(provider_time) >= 100_000_000_000 and abs(chart_time) < 100_000_000_000:
        return int(provider_time / 1000)
    return provider_time


def validate_capture_series(
    fixture: dict[str, Any],
    series: dict[str, list[dict[str, Any]]],
) -> None:
    expected_titles = set(fixture.get("expected_series", {}))
    unknown_titles = sorted(set(series) - expected_titles)
    if unknown_titles:
        raise SystemExit(
            "capture contains plot title(s) not present in expected_series: "
            + ", ".join(unknown_titles)
        )
    missing_titles = sorted(expected_titles - set(series))
    if missing_titles:
        raise SystemExit("capture missing plot title(s): " + ", ".join(missing_titles))


def is_chart_csv_column(column: str) -> bool:
    return column.strip() in CHART_CSV_COLUMNS


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
