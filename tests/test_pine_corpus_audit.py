from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pine_corpus_audit.py"
SPEC = importlib.util.spec_from_file_location("pine_corpus_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
pine_corpus_audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pine_corpus_audit
SPEC.loader.exec_module(pine_corpus_audit)


def _write_corpus(tmp_path: Path) -> Path:
    corpus = tmp_path / "pine"
    corpus.mkdir()
    (corpus / "legacy").write_text(
        """
//@version=4
study("Legacy")
length = input(14)
value = sma(close, length)
plot(value)
""",
        encoding="utf-8",
    )
    (corpus / "modern").write_text(
        """
//@version=6
indicator("Modern", overlay=true)
import TradingView/ta/10
import Example/helpers/3 as helper
theme = chart.fg_color
point = chart.point.now(close)
items = array.from(close, open)
weighted = ta.vwap(hlc3)
pivots = ta.pivot_point_levels("Traditional", timeframe.change("1D"))
lines = line.all
boxes = box.all
table.merge_cells(na, 0, 0, 1, 0)
linefill.new(na, na)
rounded = floor(close)
session_time = time("1D")
alert("changed", alert.freq_once_per_bar)
[up_volume, down_volume, delta] = ta.requestUpAndDownVolume("1")
custom_value = helper.calculate(close)
value = close > open ? close : open
""",
        encoding="utf-8",
    )
    return corpus


def test_report_is_aggregate_only_and_never_claims_source_execution(tmp_path: Path) -> None:
    report = pine_corpus_audit.build_report(_write_corpus(tmp_path))

    assert report["schemaVersion"] == 2
    assert report["sourcePolicy"] == {
        "executesPine": False,
        "copiesSource": False,
        "claim": (
            "Feature coverage means a Pyne API analogue exists after a Python rewrite; "
            "it does not mean the Pine source is directly executable."
        ),
    }
    assert report["summary"]["fileCount"] == 2
    assert report["summary"]["versions"] == {"4": 1, "6": 1}
    assert report["summary"]["declarations"] == {"indicator": 1, "study": 1}
    serialized = json.dumps(report)
    assert 'study("Legacy")' not in serialized
    assert 'indicator("Modern"' not in serialized


def test_report_classifies_runtime_syntax_host_and_render_boundaries(tmp_path: Path) -> None:
    report = pine_corpus_audit.build_report(_write_corpus(tmp_path))
    features = {item["feature"]: item for item in report["features"]}
    source_features = {item["feature"]: item for item in report["sourceFeatures"]}

    assert features["ta.vwap"]["status"] == "api-covered"
    assert features["array.from"]["status"] == "syntax-rewrite"
    assert features["array.from"]["pyneTarget"] == "array.from_values"
    assert features["chart.fg_color"]["status"] == "host-gap"
    assert features["chart.point"]["status"] == "api-covered"
    assert features["ta.pivot_point_levels"]["status"] == "api-covered"
    assert features["line.all"]["status"] == "api-covered"
    assert features["box.all"]["status"] == "api-covered"
    assert features["table.merge_cells"]["status"] == "api-covered"
    assert features["linefill.new"]["status"] == "api-covered"
    assert features["sma"]["status"] == "api-covered"
    assert features["study"]["status"] == "api-covered"
    assert features["floor"]["status"] == "api-covered"
    assert features["alert"]["status"] == "syntax-rewrite"
    assert features["alert.freq_once_per_bar"]["status"] == "syntax-rewrite"
    assert features["alert.freq_once_per_bar"]["pyneTarget"] == (
        "emit_signal(...) + host alert policy"
    )
    imported_volume = features[
        "pine-library:TradingView/ta/10#requestUpAndDownVolume"
    ]
    assert imported_volume["status"] == "api-covered"
    assert imported_volume["pyneTarget"] == (
        'pine_library("TradingView/ta/10").requestUpAndDownVolume'
    )
    assert features["pine-library:Example/helpers/3#calculate"]["status"] == (
        "library-rewrite"
    )
    assert "ta.requestUpAndDownVolume" not in features
    assert features["time"]["status"] == "api-covered"
    assert source_features["pine.ternary"]["status"] == "syntax-rewrite"
    assert "runtime-gap" not in report["compatibility"]
    candidates = {
        item["member"]: item
        for item in report["capabilityDemand"]["incrementalTaCandidates"]
    }
    assert "vwap" not in candidates
    assert candidates["pivot_point_levels"]["occurrenceCount"] == 1
    assert report["capabilityDemand"]["externalLibraryCandidates"] == [
        {
            "identifier": "Example/helpers/3",
            "member": "calculate",
            "fileCount": 1,
            "occurrenceCount": 1,
            "examples": ["modern"],
        }
    ]


def test_cli_writes_machine_readable_json_without_source_text(tmp_path: Path) -> None:
    corpus = _write_corpus(tmp_path)
    output = tmp_path / "report.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(corpus),
            "--format",
            "json",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["summary"]["fileCount"] == 2
    assert report["sourcePolicy"]["executesPine"] is False
    rendered = output.read_text(encoding="utf-8")
    assert 'study("Legacy")' not in rendered
    assert 'indicator("Modern"' not in rendered
