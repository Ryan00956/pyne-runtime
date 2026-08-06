from __future__ import annotations

import json
from pathlib import Path

import pyne_runtime as pn

from pyne_runtime.cli import main


def test_inspect_script_reports_mode_requirements_and_host_contracts() -> None:
    source = """
indicator("Demand", mode="incremental")

def on_preview(ctx, bar):
    ctx.trace.emit("preview")

def on_bar(ctx, bar):
    total = ctx.state("total", 0.0)
    total.value += bar.close
    ctx.plot("Fast", ctx.ta.ema("fast", 3).update(bar.close))
    ctx.plot("Remote", ctx.request.security("TEST", "1D", "close"))
    ctx.strategy.entry("L", ctx.strategy.long, qty=1)
    ctx.line_new(bar.bar_index, bar.low, bar.bar_index, bar.high)
"""

    report = pn.inspect_script(source)

    assert report["schemaVersion"] == pn.PYNE_SCRIPT_INSPECTION_SCHEMA_VERSION
    assert report["runtimeMode"] == "incremental"
    assert report["declaration"] == {"kind": "indicator", "title": "Demand"}
    assert report["callbacks"] == ["on_bar", "on_preview"]
    assert report["requirements"]["ta"] == ["ema"]
    assert report["requirements"]["request"] == ["security"]
    assert report["requirements"]["strategy"] == ["entry"]
    assert report["requirements"]["drawings"] == ["line"]
    assert report["requirements"]["host"] == ["dataProvider"]
    assert report["resourceHints"]["usesState"] is True
    assert report["resourceHints"]["usesPreview"] is True
    assert report["resourceHints"]["usesTrace"] is True
    assert report["compatibility"]["supported"] is True
    assert source not in json.dumps(report)


def test_inspect_script_fails_closed_for_unsupported_and_dynamic_members() -> None:
    report = pn.inspect_script(
        """
indicator("Unsupported", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("ALMA", ctx.ta.alma("alma", 9).update(bar.close))
    helper = getattr(ctx.ta, params["helper"])
    ctx.plot("Dynamic", helper("x", 2).update(bar.close))
"""
    )

    assert report["compatibility"]["supported"] is False
    assert any("ta.alma" in item["message"] for item in report["compatibility"]["diagnostics"])
    assert report["compatibility"]["dynamicAccesses"] == [
        {
            "namespace": "ta",
            "line": 5,
            "column": 14,
            "reason": "dynamic-member-name",
        }
    ]


def test_inspect_script_reports_pinned_library_members_and_mode_boundary() -> None:
    source = """
indicator("Library")
plot(pine_library("TradingView/ta/10").changePercent(close, open), "Change")
plot(pine_library("TradingView/ta/10").missing(close), "Missing")
"""
    report = pn.inspect_script(source)
    library = report["requirements"]["externalLibraries"][0]

    assert library["identifier"] == "TradingView/ta/10"
    assert library["supportedMembers"] == ["changePercent"]
    assert library["unsupportedMembers"] == ["missing"]
    assert report["compatibility"]["supported"] is False


def test_inspect_script_only_reports_host_data_for_members_that_need_it() -> None:
    pure = pn.inspect_script(
        'plot(pine_library("TradingView/ta/10").ema2(close, 3), "EMA")'
    )
    requested = pn.inspect_script(
        'plot(pine_library("TradingView/ta/10").requestVolumeDelta("1", "D"), "CVD")'
    )

    assert pure["requirements"]["externalLibraries"][0]["dataRequirements"] == []
    assert requested["requirements"]["externalLibraries"][0]["dataRequirements"] == [
        "request.security_lower_tf"
    ]


def test_inspect_cli_prints_machine_readable_manifest(tmp_path: Path, capsys) -> None:
    script = tmp_path / "indicator.py"
    script.write_text('indicator("CLI")\nplot(ta.sma(close, 2), "SMA")\n', encoding="utf-8")

    exit_code = main(["inspect", str(script)])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["runtimeMode"] == "batch"
    assert payload["requirements"]["ta"] == ["sma"]
