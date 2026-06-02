from __future__ import annotations

import pyne_runtime as pn


def test_schema_bundle_exposes_versions_and_contracts() -> None:
    schema = pn.schema()

    assert schema["input"]["schemaVersion"] == pn.PYNE_INPUT_SCHEMA_VERSION
    assert schema["output"]["schemaVersion"] == pn.PYNE_OUTPUT_SCHEMA_VERSION
    assert schema["params"]["schemaVersion"] == pn.PYNE_PARAM_SCHEMA_VERSION
    assert schema["requestProvider"]["schemaVersion"] == pn.PYNE_REQUEST_PROVIDER_SCHEMA_VERSION
    assert schema["input"]["required"] == ["time", "open", "high", "low", "close", "volume"]
    assert "lines" in schema["output"]["outputKeys"]
    assert "timeframe" in schema["params"]["types"]
    assert schema["params"]["entry"]["id"]
    assert "get_ohlcv" in schema["requestProvider"]["method"]
    assert "request.security" in schema["requestProvider"]["capabilities"]["securityAliases"]
    assert schema["requestProvider"]["cache"]["key"] == ["symbol", "timeframe", "start", "end"]
    assert "request.security_lower_tf" in schema["requestProvider"]["cache"]["reusedFor"]
    assert schema["requestProvider"]["errors"]["capabilityFailure"] == "PYNE_RUNTIME_ERROR"
