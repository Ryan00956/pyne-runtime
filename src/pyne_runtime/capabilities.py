"""Versioned, mode-aware runtime capability discovery and validation."""
from __future__ import annotations

import ast
import copy
from typing import Any

from .errors import error_detail


PYNE_RUNTIME_CAPABILITIES_SCHEMA_VERSION = 1

BATCH_TA_CAPABILITIES = (
    "adx",
    "alma",
    "atr",
    "barssince",
    "bb",
    "cci",
    "change",
    "cmo",
    "correlation",
    "cross",
    "crossover",
    "crossunder",
    "cum",
    "dev",
    "dmi",
    "donchian",
    "ema",
    "falling",
    "highest",
    "highestbars",
    "hma",
    "keltner",
    "linreg",
    "lowest",
    "lowestbars",
    "macd",
    "mfi",
    "mom",
    "nz",
    "obv",
    "percentile_linear_interpolation",
    "percentile_nearest_rank",
    "pivot_point_levels",
    "pivothigh",
    "pivotlow",
    "rising",
    "rma",
    "roc",
    "rsi",
    "sar",
    "shift",
    "sma",
    "stdev",
    "stoch",
    "supertrend",
    "swma",
    "tr",
    "tsi",
    "valuewhen",
    "variance",
    "volume_sma",
    "vwap",
    "vwma",
    "wma",
    "wpr",
)

INCREMENTAL_TA_CAPABILITIES = (
    "adx",
    "atr",
    "barssince",
    "boll",
    "cci",
    "cross",
    "crossover",
    "crossunder",
    "dmi",
    "ema",
    "highest",
    "hma",
    "lowest",
    "macd",
    "mfi",
    "rma",
    "rsi",
    "sar",
    "sma",
    "stdev",
    "stoch",
    "supertrend",
    "valuewhen",
    "variance",
    "vwap",
    "vwma",
    "wma",
)

REQUEST_CAPABILITIES = ("security", "security_lower_tf")
DRAWING_CAPABILITIES = (
    "box",
    "label",
    "line",
    "linefill",
    "polyline",
    "table",
)
BATCH_STRATEGY_CAPABILITIES = (
    "cancel",
    "cancel_all",
    "close",
    "close_all",
    "close_when",
    "entry",
    "entry_when",
    "exit",
    "oca",
    "order",
    "order_when",
    "risk",
    "trade_ledger",
)

INCREMENTAL_STRATEGY_CAPABILITIES = tuple(
    item
    for item in BATCH_STRATEGY_CAPABILITIES
    if item not in {"close_when", "entry_when", "order_when"}
)


def runtime_capabilities() -> dict[str, Any]:
    """Return a defensive copy of the public runtime capability contract."""
    from .pine_libraries import SUPPORTED_PINE_LIBRARIES

    payload = {
        "schemaVersion": PYNE_RUNTIME_CAPABILITIES_SCHEMA_VERSION,
        "language": {
            "id": "pyne-python",
            "acceptsPineSource": False,
        },
        "modes": {
            "batch": {
                "callbacks": [],
                "ta": list(BATCH_TA_CAPABILITIES),
                "request": list(REQUEST_CAPABILITIES),
                "strategy": list(BATCH_STRATEGY_CAPABILITIES),
                "drawings": list(DRAWING_CAPABILITIES),
                "preview": False,
                "portableSnapshot": False,
            },
            "incremental": {
                "callbacks": ["init", "on_bar", "on_preview"],
                "ta": list(INCREMENTAL_TA_CAPABILITIES),
                "request": list(REQUEST_CAPABILITIES),
                "strategy": list(INCREMENTAL_STRATEGY_CAPABILITIES),
                "drawings": list(DRAWING_CAPABILITIES),
                "preview": True,
                "portableSnapshot": True,
                "portableSnapshotFormats": ["replay-v1", "typed-state-v2"],
            },
        },
        "externalLibraries": [
            {
                "identifier": item.identifier,
                "members": list(item.members),
                "dataRequirements": list(item.data_requirements),
                "memberDataRequirements": {
                    member: list(requirements)
                    for member, requirements in item.member_data_requirements
                },
                "modes": ["batch"],
            }
            for item in SUPPORTED_PINE_LIBRARIES
        ],
        "trace": {
            "schemaVersion": 2,
            "bounded": True,
            "defaultEnabled": False,
            "modes": ["batch", "incremental"],
            "timingSpans": True,
            "slowSpanSummary": True,
            "fieldRedaction": True,
        },
        "security": {
            "modes": ["safe", "research", "unsafe"],
            "multiTenantSandbox": False,
            "processTimeout": True,
        },
    }
    return copy.deepcopy(payload)


def capability_diagnostics(
    script: str,
    *,
    runtime_mode: str | None = None,
) -> list[dict[str, Any]]:
    """Report statically discoverable mode-specific unsupported calls."""
    try:
        tree = ast.parse(script)
    except SyntaxError:
        return []
    mode = _normalize_runtime_mode(runtime_mode) or _detect_runtime_mode(tree)
    if mode != "incremental":
        return []

    diagnostics: list[dict[str, Any]] = []
    supported_ta = set(INCREMENTAL_TA_CAPABILITIES)
    supported_request = set(REQUEST_CAPABILITIES)
    seen: set[tuple[str, int, int]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner = node.func.value
        if isinstance(owner, ast.Name) and owner.id == "request":
            namespace = "request"
        elif (
            isinstance(owner, ast.Attribute)
            and isinstance(owner.value, ast.Name)
            and owner.value.id == "ctx"
        ):
            namespace = owner.attr
        else:
            continue
        member = node.func.attr
        supported = supported_ta if namespace == "ta" else supported_request if namespace == "request" else None
        if supported is None or member in supported:
            continue
        key = (f"{namespace}.{member}", int(node.lineno), int(node.col_offset))
        if key in seen:
            continue
        seen.add(key)
        diagnostics.append(
            error_detail(
                "PYNE_UNSUPPORTED_FEATURE",
                f"Incremental runtime does not support {namespace}.{member}()",
                line=node.lineno,
                column=node.col_offset + 1,
                hint=(
                    f"Use one of the incremental {namespace} capabilities exposed by "
                    "pn.runtime_capabilities(), or run the script in batch mode."
                ),
            )
        )
    return diagnostics


def _normalize_runtime_mode(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized not in {"batch", "incremental"}:
        raise ValueError("runtime_mode must be 'batch' or 'incremental'")
    return normalized


def _detect_runtime_mode(tree: ast.AST) -> str:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "on_bar":
            return "incremental"
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else ""
        if name not in {"indicator", "strategy", "study"}:
            continue
        for keyword in node.keywords:
            if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                if str(keyword.value.value).strip().lower() == "incremental":
                    return "incremental"
    return "batch"
