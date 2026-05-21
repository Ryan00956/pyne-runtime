from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_strategy_capture_diff_json_matches_capture(tmp_path: Path) -> None:
    fixture = write_fixture(tmp_path, captured_values={"Position": [1.0]})

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_diff.py"),
            str(fixture),
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    report = json.loads(completed.stdout)
    assert report["counts"] == {
        "captured_cases": 1,
        "skipped_cases": 0,
        "plots": 1,
        "points": 1,
        "differences": 0,
        "runtime_errors": 0,
    }
    assert report["differences"] == []


def test_strategy_capture_diff_reports_value_mismatch(tmp_path: Path) -> None:
    fixture = write_fixture(tmp_path, captured_values={"Position": [2.0]})

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_diff.py"),
            str(fixture),
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert report["counts"]["differences"] == 1
    assert report["differences"][0] == {
        "fixture": "fixture.json",
        "case": "sample",
        "kind": "value_mismatch",
        "plot": "Position",
        "bar_index": 0,
        "tradingview": 2.0,
        "pyne": 1.0,
        "delta": -1.0,
        "tolerance": 0.0,
    }


def test_strategy_capture_diff_skips_not_captured_cases(tmp_path: Path) -> None:
    fixture = write_fixture(tmp_path, captured_values=None)

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_diff.py"),
            str(fixture),
            "--json",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    report = json.loads(completed.stdout)
    assert report["counts"]["captured_cases"] == 0
    assert report["counts"]["skipped_cases"] == 1


def write_fixture(
    tmp_path: Path,
    *,
    captured_values: dict[str, list[float]] | None,
) -> Path:
    capture = {
        "provider": "tradingview",
        "status": "not_captured",
        "notes": ["placeholder"],
    }
    if captured_values is not None:
        capture = {
            "provider": "tradingview",
            "status": "captured",
            "values": captured_values,
        }

    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "name": "sample",
                        "script": "\n".join(
                            [
                                'strategy("Sample", overlay=True, initial_capital=1000, pyramiding=0)',
                                'strategy.entry("Long", strategy.long, qty=1, when=bar_index == 0, price=close)',
                                'plot(strategy.position_size, "Position")',
                                "",
                            ]
                        ),
                        "bars": [
                            {
                                "time": 1,
                                "open": 10,
                                "high": 10,
                                "low": 10,
                                "close": 10,
                                "volume": 100,
                            }
                        ],
                        "values": {"Position": [1.0]},
                        "external_capture": capture,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return fixture
