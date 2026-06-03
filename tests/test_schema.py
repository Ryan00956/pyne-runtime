from __future__ import annotations

import pyne_runtime as pn


def test_schema_bundle_exposes_versions_and_contracts() -> None:
    schema = pn.schema()

    assert schema["input"]["schemaVersion"] == pn.PYNE_INPUT_SCHEMA_VERSION
    assert schema["output"]["schemaVersion"] == pn.PYNE_OUTPUT_SCHEMA_VERSION
    assert schema["params"]["schemaVersion"] == pn.PYNE_PARAM_SCHEMA_VERSION
    assert schema["requestProvider"]["schemaVersion"] == pn.PYNE_REQUEST_PROVIDER_SCHEMA_VERSION
    assert schema["strategyReport"]["schemaVersion"] == pn.PYNE_STRATEGY_REPORT_SCHEMA_VERSION
    assert schema["input"]["required"] == ["time", "open", "high", "low", "close", "volume"]
    assert "lines" in schema["output"]["outputKeys"]
    assert "labels" in schema["output"]["outputKeys"]
    assert schema["output"]["renderables"]["lines"]["required"] == [
        "id",
        "title",
        "color",
        "linewidth",
        "style",
        "pane",
        "data",
    ]
    assert schema["output"]["renderables"]["lines"]["pointOptional"] == ["color"]
    assert "payload" in schema["output"]["renderables"]["signals"]["pointOptional"]
    assert schema["output"]["renderables"]["labels"]["status"].startswith("legacy")
    assert schema["output"]["objects"]["groups"] == ["lines", "labels", "boxes", "tables"]
    assert schema["output"]["objects"]["tables"]["cellRequired"] == [
        "column",
        "row",
        "text",
        "text_color",
        "bgcolor",
        "width",
        "height",
        "text_halign",
        "text_valign",
    ]
    assert schema["output"]["objectEvents"]["actions"] == ["create", "update", "delete"]
    assert schema["output"]["objectEvents"]["kinds"] == ["line", "label", "box", "table"]
    assert schema["output"]["migration"]["currentVersion"] == pn.PYNE_OUTPUT_SCHEMA_VERSION
    assert "migration note" in schema["output"]["migration"]["breakingChangeRequires"]
    assert "contract test" in schema["output"]["migration"]["breakingChangeRequires"]
    assert schema["output"]["migration"]["versions"][0]["version"] == 1
    assert schema["output"]["migration"]["versions"][0]["breakingChanges"] == []
    assert any(
        "output.labels" in note
        for note in schema["output"]["migration"]["versions"][0]["notes"]
    )
    assert "timeframe" in schema["params"]["types"]
    assert schema["params"]["entry"]["id"]
    assert "get_ohlcv" in schema["requestProvider"]["method"]
    assert "request.security" in schema["requestProvider"]["capabilities"]["securityAliases"]
    assert schema["requestProvider"]["cache"]["key"] == ["symbol", "timeframe", "start", "end"]
    assert "request.security_lower_tf" in schema["requestProvider"]["cache"]["reusedFor"]
    assert schema["requestProvider"]["errors"]["capabilityFailure"] == "PYNE_RUNTIME_ERROR"
    assert schema["strategyReport"]["outputKey"] == "strategy"
    assert "closedtrades" in schema["strategyReport"]["sections"]
    assert "netprofit" in schema["strategyReport"]["summary"]["required"]
    assert "net_profit" in schema["strategyReport"]["trades"]["closedRequired"]
    assert schema["strategyReport"]["lifecycle"]["statusValues"] == [
        "pending",
        "filled",
        "canceled",
        "rejected",
        "submitted",
    ]
