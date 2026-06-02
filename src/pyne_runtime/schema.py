"""Pyne input and output schema helpers."""
from __future__ import annotations

from typing import Any


PYNE_INPUT_SCHEMA_VERSION = 1
PYNE_OUTPUT_SCHEMA_VERSION = 1
PYNE_PARAM_SCHEMA_VERSION = 1
PYNE_REQUEST_PROVIDER_SCHEMA_VERSION = 1

OHLCV_FIELDS = ("time", "open", "high", "low", "close", "volume")
OUTPUT_KEYS = (
    "lines",
    "histograms",
    "markers",
    "hlines",
    "fills",
    "bgcolors",
    "barcolors",
    "signals",
    "strategy",
    "objects",
    "object_events",
)


def input_schema() -> dict[str, Any]:
    """Return the stable Pyne OHLCV input contract."""
    return {
        "schemaVersion": PYNE_INPUT_SCHEMA_VERSION,
        "type": "ohlcv",
        "required": list(OHLCV_FIELDS),
        "timeUnit": "seconds",
        "bar": {
            "time": "Unix timestamp in seconds",
            "open": "Open price as float",
            "high": "High price as float",
            "low": "Low price as float",
            "close": "Close price as float",
            "volume": "Volume as float",
        },
    }


def output_schema() -> dict[str, Any]:
    """Return the stable Pyne result/output contract."""
    return {
        "schemaVersion": PYNE_OUTPUT_SCHEMA_VERSION,
        "result": {
            "ok": "Whether execution succeeded",
            "error": "Error message when execution failed",
            "code": "Stable error code when execution failed",
            "errorDetail": "Structured error detail when execution failed",
            "lines": "Backward-compatible flat plotted series",
            "output": "Structured output collections",
            "param_schema": "Input parameter declarations collected from scripts",
            "paramSchemaVersion": "Parameter schema version for param_schema entries",
            "meta": "Indicator metadata collected from indicator()",
        },
        "outputKeys": list(OUTPUT_KEYS),
        "point": {
            "time": "Unix timestamp in seconds",
            "value": "Numeric point value",
        },
        "paneValues": ["main", "separate"],
    }


def param_schema() -> dict[str, Any]:
    """Return the stable Pyne script parameter schema contract."""
    return {
        "schemaVersion": PYNE_PARAM_SCHEMA_VERSION,
        "entry": {
            "id": "Stable parameter id; currently matches key",
            "key": "Override key; by default this is the input title",
            "type": "Parameter type",
            "default": "Declared default value",
            "current": "Value used for the current run",
            "title": "Display title",
            "tooltip": "Optional UI tooltip",
            "group": "Optional UI group",
            "inline": "Optional same-line UI grouping hint",
            "confirm": "Whether a host should require explicit confirmation",
            "options": "Optional enumerated choices",
            "minval": "Optional numeric lower bound",
            "maxval": "Optional numeric upper bound",
            "step": "Optional numeric increment",
        },
        "types": [
            "int",
            "float",
            "bool",
            "string",
            "color",
            "source",
            "timeframe",
            "symbol",
            "session",
            "time",
        ],
    }


def request_provider_schema() -> dict[str, Any]:
    """Return the stable host data-provider contract for request.* calls."""
    return {
        "schemaVersion": PYNE_REQUEST_PROVIDER_SCHEMA_VERSION,
        "method": "get_ohlcv(symbol, timeframe, start, end) -> list[OHLCV bar]",
        "requiredBarFields": list(OHLCV_FIELDS),
        "range": {
            "start": "Chart start time as Unix seconds",
            "end": "Chart end time as Unix seconds",
            "semantics": "Provider should return bars relevant to [start, end]",
        },
        "capabilities": {
            "declaredBy": "optional capabilities attribute or capabilities() method",
            "securityAliases": ["request.security", "security", "ohlcv"],
            "lowerTimeframeAliases": [
                "request.security_lower_tf",
                "security_lower_tf",
                "lower_tf",
            ],
            "missingDeclaration": "supported",
            "dictSemantics": "at least one matching alias must be present and truthy",
            "sequenceSemantics": "at least one matching alias must be present",
        },
        "metadata": {
            "declaredBy": (
                "optional get_request_metadata(symbol, timeframe), "
                "request_metadata(symbol, timeframe), or request_metadata mapping"
            ),
            "acceptedKeys": {
                "syminfo": ["syminfo", "symbol_info"],
                "timeframe": ["timeframe", "timeframe_info"],
                "session": ["session", "session_info"],
            },
            "defaults": (
                "requested symbol is used for syminfo ticker/tickerid; requested "
                "timeframe is used for timeframe.period; session defaults are inferred"
            ),
        },
        "errors": {
            "invalidSymbol": "raise PyneInvalidSymbolError to support ignore_invalid_symbol",
            "unsupportedCapability": "PYNE_UNSUPPORTED_FEATURE before get_ohlcv is called",
            "invalidOhlcv": "PYNE_RUNTIME_ERROR",
            "providerFailure": "PYNE_RUNTIME_ERROR",
        },
    }


def schema() -> dict[str, Any]:
    """Return the public Pyne input/output schema bundle."""
    return {
        "input": input_schema(),
        "output": output_schema(),
        "params": param_schema(),
        "requestProvider": request_provider_schema(),
    }

