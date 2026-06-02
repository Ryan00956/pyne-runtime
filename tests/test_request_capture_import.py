from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_request_capture_import_rebuilds_provider_bars(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path)
    csv_path = tmp_path / "export.csv"
    csv_path.write_text(
        "time,open,high,low,close,HTF Close,HTF Time,HTF Open,HTF High,HTF Low,HTF Provider Close,HTF Volume,Pyne Capture Index,Volume\n"
        "1,10,11,9,10,100,1000,90,110,80,100,5000,0,100\n"
        "2,11,12,10,11,100,,,,,,5000,1,200\n"
        "3,12,13,11,12,200,2000,190,210,180,200,6000,2,300\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "request_capture_import.py"),
            str(fixture),
            "--values",
            str(csv_path),
            "--tolerance",
            "1e-9",
            "--assertion",
            "parity",
            "--note",
            "unit test capture",
        ],
        check=True,
        cwd=ROOT,
    )

    updated = json.loads(fixture.read_text(encoding="utf-8"))
    capture = updated["external_capture"]
    assert capture["status"] == "captured"
    assert capture["assertion"] == "parity"
    assert capture["series"]["HTF Close"] == [
        {"time": 1, "value": 100.0},
        {"time": 2, "value": 100.0},
        {"time": 3, "value": 200.0},
    ]
    assert capture["provider_bars"] == [
        {"time": 1000, "open": 90.0, "high": 110.0, "low": 80.0, "close": 100.0, "volume": 5000.0},
        {"time": 2000, "open": 190.0, "high": 210.0, "low": 180.0, "close": 200.0, "volume": 6000.0},
    ]


def _write_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "request_security_sample_capture.json"
    fixture.write_text(
        json.dumps(
            {
                "name": "request_security_sample_capture",
                "chart_bars": [
                    {"time": 1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
                    {"time": 2, "open": 11, "high": 12, "low": 10, "close": 11, "volume": 200},
                    {"time": 3, "open": 12, "high": 13, "low": 11, "close": 12, "volume": 300},
                ],
                "script": "",
                "expected_series": {
                    "HTF Close": [],
                    "HTF Time": [],
                    "HTF Open": [],
                    "HTF High": [],
                    "HTF Low": [],
                    "HTF Provider Close": [],
                    "HTF Volume": [],
                },
                "external_capture": {
                    "provider": "tradingview",
                    "status": "not_captured",
                    "assertion": "reference",
                    "provider_bar_plots": {
                        "time": "HTF Time",
                        "open": "HTF Open",
                        "high": "HTF High",
                        "low": "HTF Low",
                        "close": "HTF Provider Close",
                        "volume": "HTF Volume",
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return fixture
