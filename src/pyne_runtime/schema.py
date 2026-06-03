"""Pyne input and output schema helpers."""
from __future__ import annotations

from typing import Any


PYNE_INPUT_SCHEMA_VERSION = 1
PYNE_OUTPUT_SCHEMA_VERSION = 1
PYNE_PARAM_SCHEMA_VERSION = 1
PYNE_REQUEST_PROVIDER_SCHEMA_VERSION = 3
PYNE_STRATEGY_REPORT_SCHEMA_VERSION = 1

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
        "cache": {
            "scope": "one script run",
            "key": ["symbol", "timeframe", "start", "end"],
            "reusedFor": [
                "request.security",
                "request.security_lower_tf",
                "requested metadata",
            ],
            "separateRuns": "provider data is not cached across pn.run() executions",
            "ignoredInvalidSymbol": "ignore_invalid_symbol=True empty results are not cached",
        },
        "errors": {
            "invalidSymbol": "raise PyneInvalidSymbolError to support ignore_invalid_symbol",
            "unsupportedCapability": "PYNE_UNSUPPORTED_FEATURE before get_ohlcv is called",
            "capabilityFailure": "PYNE_RUNTIME_ERROR",
            "invalidOhlcv": "PYNE_RUNTIME_ERROR",
            "providerFailure": "PYNE_RUNTIME_ERROR",
        },
    }


def strategy_report_schema() -> dict[str, Any]:
    """Return the stable strategy report contract."""
    return {
        "schemaVersion": PYNE_STRATEGY_REPORT_SCHEMA_VERSION,
        "outputKey": "strategy",
        "sections": [
            "orders",
            "position",
            "summary",
            "risk",
            "closedtrades",
            "opentrades",
            "lifecycle",
        ],
        "orders": {
            "required": ["time", "id", "type", "side", "qty", "price", "position_after"],
            "optional": [
                "from_entry",
                "reason",
                "comment",
                "limit",
                "stop",
                "commission",
                "oca_name",
                "oca_type",
                "canceled",
            ],
        },
        "position": {
            "required": ["size", "side", "avg_price"],
            "sideValues": ["long", "short", "flat"],
        },
        "summary": {
            "required": [
                "initial_capital",
                "currency",
                "equity",
                "netprofit",
                "openprofit",
                "grossprofit",
                "grossloss",
                "commission",
                "backtest_fill_limits_assumption",
                "same_bar_fill_priority",
                "intrabar_path",
                "margin_long",
                "margin_short",
            ],
        },
        "risk": {
            "required": [
                "locked",
                "max_drawdown",
                "max_drawdown_type",
                "max_intraday_loss",
                "max_intraday_loss_type",
                "max_position_size",
                "max_intraday_filled_orders",
            ],
        },
        "trades": {
            "closedRequired": [
                "entry_time",
                "exit_time",
                "entry_id",
                "exit_id",
                "side",
                "qty",
                "entry_price",
                "exit_price",
                "profit",
                "commission",
                "net_profit",
            ],
            "openRequired": [
                "entry_time",
                "entry_id",
                "side",
                "qty",
                "entry_price",
                "profit",
            ],
            "openOptional": ["commission"],
            "privateFields": "Internal fields beginning with '_' are not part of the public report",
        },
        "lifecycle": {
            "required": [
                "id",
                "type",
                "status",
                "phase",
                "submitted_time",
                "filled_time",
                "canceled_time",
                "rejected_time",
            ],
            "optional": [
                "side",
                "qty",
                "price",
                "position_after",
                "reason",
                "comment",
                "commission",
                "from_entry",
                "target_qty",
                "requested_qty",
                "filled_qty",
                "qty_percent",
                "oca_name",
                "oca_type",
                "canceled",
                "rejected_reason",
            ],
            "statusValues": ["pending", "filled", "canceled", "rejected", "submitted"],
        },
    }


def schema() -> dict[str, Any]:
    """Return the public Pyne input/output schema bundle."""
    return {
        "input": input_schema(),
        "output": output_schema(),
        "params": param_schema(),
        "requestProvider": request_provider_schema(),
        "strategyReport": strategy_report_schema(),
    }

