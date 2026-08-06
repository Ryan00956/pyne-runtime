from __future__ import annotations

import pyne_runtime as pn
import pytest
from pyne_runtime.incremental.ta import IncrementalTaNamespace
from pyne_runtime.ta import TaModule


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
        {"time": 2, "open": 2, "high": 3, "low": 1.5, "close": 2.5, "volume": 20},
    ]


def test_runtime_capabilities_are_versioned_mode_aware_and_defensive() -> None:
    first = pn.runtime_capabilities()
    second = pn.runtime_capabilities()

    assert first["schemaVersion"] == pn.PYNE_RUNTIME_CAPABILITIES_SCHEMA_VERSION
    assert "wma" in first["modes"]["incremental"]["ta"]
    assert "hma" in first["modes"]["batch"]["ta"]
    assert "hma" not in first["modes"]["incremental"]["ta"]
    assert first["modes"]["incremental"]["portableSnapshot"] is True
    assert first["trace"]["bounded"] is True
    assert "entry_when" in first["modes"]["batch"]["strategy"]
    assert "entry_when" not in first["modes"]["incremental"]["strategy"]
    assert first["externalLibraries"][0]["modes"] == ["batch"]
    assert pn.schema()["runtimeCapabilities"] == second

    first["modes"]["incremental"]["ta"].clear()
    assert second["modes"]["incremental"]["ta"]


def test_ta_capability_lists_cover_the_actual_script_facing_namespaces() -> None:
    batch = {
        name
        for name in dir(TaModule)
        if not name.startswith("_")
        and name != "bind"
        and callable(getattr(TaModule, name))
    }
    incremental = {
        name
        for name in dir(IncrementalTaNamespace)
        if not name.startswith("_") and callable(getattr(IncrementalTaNamespace, name))
    }

    assert set(pn.BATCH_TA_CAPABILITIES) == batch
    assert set(pn.INCREMENTAL_TA_CAPABILITIES) == incremental


def test_validate_reports_unsupported_incremental_capability_at_call_site() -> None:
    script = """
indicator("Unsupported", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("HMA", ctx.ta.hma("hma", period=4).update(bar.close))
"""

    diagnostics = pn.validate(script)

    unsupported = [item for item in diagnostics if item["code"] == "PYNE_UNSUPPORTED_FEATURE"]
    assert len(unsupported) == 1
    assert unsupported[0]["line"] == 4
    assert unsupported[0]["column"] == 21
    assert "ta.hma()" in unsupported[0]["message"]


def test_incremental_execution_fails_before_running_unsupported_callback() -> None:
    script = """
indicator("Unsupported", mode="incremental")
def on_bar(ctx, bar):
    ctx.ta.hma("hma", period=4)
"""

    result = pn.run(script, _bars(), executor_mode="inline")

    assert not result.ok
    assert result.code == "PYNE_UNSUPPORTED_FEATURE"
    assert "ta.hma()" in str(result.error)


def test_validate_reports_unsupported_incremental_request_member() -> None:
    diagnostics = pn.validate(
        """
indicator("Unsupported Request", mode="incremental")
def on_bar(ctx, bar):
    ctx.request.financial("TEST", "revenue")
    request.economic("US", "GDP")
"""
    )

    unsupported = [item for item in diagnostics if item["code"] == "PYNE_UNSUPPORTED_FEATURE"]
    assert len(unsupported) == 2
    assert {item["message"] for item in unsupported} == {
        "Incremental runtime does not support request.financial()",
        "Incremental runtime does not support request.economic()",
    }


def test_explicit_batch_validation_does_not_apply_incremental_ta_contract() -> None:
    assert pn.validate("value = ctx.ta.hma('hma', period=4)", runtime_mode="batch") == []
    with pytest.raises(ValueError, match="runtime_mode"):
        pn.validate("plot(close)", runtime_mode="streaming")
