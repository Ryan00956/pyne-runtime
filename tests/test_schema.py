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
    request_diagnostics = schema["requestProvider"]["diagnostics"]
    assert request_diagnostics["resultLocation"] == "meta.requestDiagnostics"
    assert request_diagnostics["entryRequired"] == [
        "api",
        "symbol",
        "timeframe",
        "start",
        "end",
        "bars",
        "cacheHit",
        "ignoreInvalidSymbol",
        "status",
    ]
    assert request_diagnostics["apiValues"] == [
        "request.security",
        "request.security_lower_tf",
    ]
    assert request_diagnostics["statusValues"] == ["ok", "ignoredInvalidSymbol"]
    assert schema["requestProvider"]["errors"]["capabilityFailure"] == "PYNE_RUNTIME_ERROR"
    request_errors = schema["requestProvider"]["errorCategories"]
    assert request_errors["missingProvider"]["code"] == "PYNE_UNSUPPORTED_FEATURE"
    assert request_errors["missingProvider"]["beforeGetOhlcv"] is True
    assert request_errors["unsupportedCapability"]["beforeGetOhlcv"] is True
    assert request_errors["capabilityFailure"]["messageContains"] == (
        "request capability provider failed"
    )
    assert request_errors["invalidSymbol"]["code"] == "PYNE_INVALID_SYMBOL"
    assert "request.security_lower_tf" in request_errors["invalidSymbol"]["appliesTo"]
    assert "empty groups" in request_errors["invalidSymbol"]["ignoreInvalidSymbol"]
    assert request_errors["providerFailure"]["code"] == "PYNE_RUNTIME_ERROR"
    assert request_errors["invalidReturnType"]["messageContains"] == (
        "must return a list of OHLCV bars"
    )
    assert request_errors["invalidBarShape"]["messageContains"] == (
        "request data provider returned"
    )
    assert request_errors["invalidMetadata"]["messageContains"] == (
        "request metadata must be a mapping"
    )
    assert request_errors["metadataFailure"]["messageContains"] == (
        "request metadata provider failed"
    )
    assert request_errors["expressionFailure"]["messageContains"] == (
        "request.security() expression failed"
    )
    assert schema["requestProvider"]["migration"]["currentVersion"] == (
        pn.PYNE_REQUEST_PROVIDER_SCHEMA_VERSION
    )
    assert schema["requestProvider"]["migration"]["versions"][0]["version"] == (
        pn.PYNE_REQUEST_PROVIDER_SCHEMA_VERSION
    )
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
    script_namespace = schema["scriptNamespace"]
    assert "editor autocomplete" in script_namespace["purpose"]
    assert "close" in script_namespace["categories"]["data"]
    assert "request" in script_namespace["categories"]["modules"]
    assert "plotshape" in script_namespace["categories"]["plot"]
    assert "when" in script_namespace["categories"]["utility"]
    assert "params" in script_namespace["categories"]["compat"]
    assert "security_mode" in script_namespace["categories"]["builtins"]
    assert "plot" in script_namespace["names"]
    assert "barmerge" in script_namespace["names"]
    assert len(script_namespace["names"]) == len(set(script_namespace["names"]))
