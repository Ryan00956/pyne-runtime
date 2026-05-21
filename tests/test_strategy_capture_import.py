from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_strategy_capture_import_json_values(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "name": "sample",
                        "values": {
                            "Position": [0.0, 1.0],
                            "Net Profit": [0.0, 2.0],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    values = tmp_path / "values.json"
    values.write_text(
        json.dumps({"values": {"Position": [0, 1], "Net Profit": ["0", "2.5"]}}),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_import.py"),
            str(fixture),
            "--case",
            "sample",
            "--values",
            str(values),
            "--tolerance",
            "1e-9",
            "--note",
            "exported from TradingView",
        ],
        check=True,
        cwd=ROOT,
    )

    updated = json.loads(fixture.read_text(encoding="utf-8"))
    capture = updated["cases"][0]["external_capture"]
    assert capture == {
        "provider": "tradingview",
        "status": "captured",
        "tolerance": 1e-09,
        "values": {
            "Position": [0.0, 1.0],
            "Net Profit": [0.0, 2.5],
        },
        "notes": ["exported from TradingView"],
    }


def test_strategy_capture_import_csv_ignores_time_columns(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "name": "sample",
                        "values": {
                            "Position": [0.0, 1.0],
                            "Net Profit": [0.0, 2.0],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    values = tmp_path / "values.csv"
    values.write_text(
        "time,Position,Net Profit\n1,0,0\n2,1,2\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_import.py"),
            str(fixture),
            "--case",
            "sample",
            "--values",
            str(values),
        ],
        check=True,
        cwd=ROOT,
    )

    updated = json.loads(fixture.read_text(encoding="utf-8"))
    assert updated["cases"][0]["external_capture"]["values"] == {
        "Position": [0.0, 1.0],
        "Net Profit": [0.0, 2.0],
    }


def test_strategy_capture_import_rejects_unknown_plot(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps({"cases": [{"name": "sample", "values": {"Position": [0.0]}}]}),
        encoding="utf-8",
    )
    values = tmp_path / "values.json"
    values.write_text(json.dumps({"Unknown": [1]}), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "strategy_capture_import.py"),
            str(fixture),
            "--case",
            "sample",
            "--values",
            str(values),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "not present in fixture values" in completed.stderr
