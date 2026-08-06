"""Static, source-free script requirement inspection for hosts and tooling."""
from __future__ import annotations

import ast
import hashlib
from typing import Any

from .capabilities import (
    BATCH_STRATEGY_CAPABILITIES,
    BATCH_TA_CAPABILITIES,
    DRAWING_CAPABILITIES,
    INCREMENTAL_STRATEGY_CAPABILITIES,
    INCREMENTAL_TA_CAPABILITIES,
    REQUEST_CAPABILITIES,
    _detect_runtime_mode,
    capability_diagnostics,
)
from .errors import error_detail
from .pine_libraries import SUPPORTED_PINE_LIBRARIES


PYNE_SCRIPT_INSPECTION_SCHEMA_VERSION = 1
_DRAWING_NAMESPACES = frozenset(DRAWING_CAPABILITIES)
_KNOWN_DYNAMIC_NAMESPACES = frozenset({"ta", "request", "strategy", *_DRAWING_NAMESPACES})


def inspect_script(script: str, *, runtime_mode: str | None = None) -> dict[str, Any]:
    """Return a deterministic manifest of statically discoverable script requirements.

    The report never executes the script and never includes source text. Dynamic
    attribute construction is disclosed as an uncertainty instead of being
    treated as compatible.
    """
    source = str(script)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        diagnostics = [
            error_detail(
                "PYNE_SYNTAX_ERROR",
                str(exc.msg or exc),
                line=exc.lineno,
                column=exc.offset,
            )
        ]
        return {
            "schemaVersion": PYNE_SCRIPT_INSPECTION_SCHEMA_VERSION,
            "scriptSha256": digest,
            "runtimeMode": _normalize_mode(runtime_mode) or "unknown",
            "declaration": None,
            "callbacks": [],
            "requirements": _empty_requirements(),
            "compatibility": {
                "supported": False,
                "diagnostics": diagnostics,
                "dynamicAccesses": [],
            },
            "resourceHints": _resource_hints(ast.Module(body=[], type_ignores=[])),
        }

    mode = _normalize_mode(runtime_mode) or _detect_runtime_mode(tree)
    requirements: dict[str, set[str]] = {
        "ta": set(),
        "request": set(),
        "strategy": set(),
        "drawings": set(),
    }
    libraries: dict[str, set[str]] = {}
    dynamic_accesses: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        resolved = _resolve_call(node)
        if resolved is not None:
            namespace, member = resolved
            if namespace in requirements:
                requirements[namespace].add(member)
            elif namespace in _DRAWING_NAMESPACES:
                requirements["drawings"].add(namespace)
        library_call = _resolve_library_call(node)
        if library_call is not None:
            identifier, member = library_call
            libraries.setdefault(identifier, set()).add(member)
        dynamic = _dynamic_access(node)
        if dynamic is not None:
            dynamic_accesses.append(dynamic)

    supported = _mode_capabilities(mode)
    diagnostics = capability_diagnostics(source, runtime_mode=mode)
    diagnostics.extend(_requirement_diagnostics(requirements, supported, mode=mode))
    external_libraries = _library_requirements(libraries, mode=mode)
    for library in external_libraries:
        for member in library["unsupportedMembers"]:
            diagnostics.append(
                error_detail(
                    "PYNE_UNSUPPORTED_FEATURE",
                    f"Runtime mode {mode!r} does not support "
                    f"{library['identifier']}#{member}",
                    hint="Use a declared pinned adapter member or port the dependency explicitly.",
                )
            )

    host_requirements: set[str] = set()
    if requirements["request"]:
        host_requirements.add("dataProvider")
    if any(item["dataRequirements"] for item in external_libraries):
        host_requirements.add("dataProvider")
    hints = _resource_hints(tree)
    if hints["emitsSignals"]:
        host_requirements.add("signalDelivery")
    if hints["usesMarketMetadata"]:
        host_requirements.add("marketMetadata")

    return {
        "schemaVersion": PYNE_SCRIPT_INSPECTION_SCHEMA_VERSION,
        "scriptSha256": digest,
        "runtimeMode": mode,
        "declaration": _declaration(tree),
        "callbacks": sorted(
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in {"init", "on_bar", "on_preview"}
        ),
        "requirements": {
            "ta": sorted(requirements["ta"]),
            "request": sorted(requirements["request"]),
            "strategy": sorted(requirements["strategy"]),
            "drawings": sorted(requirements["drawings"]),
            "externalLibraries": external_libraries,
            "host": sorted(host_requirements),
        },
        "compatibility": {
            "supported": not diagnostics and not dynamic_accesses,
            "diagnostics": _unique_diagnostics(diagnostics),
            "dynamicAccesses": sorted(
                dynamic_accesses,
                key=lambda item: (item["line"], item["column"], item["namespace"]),
            ),
        },
        "resourceHints": hints,
    }


def _empty_requirements() -> dict[str, Any]:
    return {
        "ta": [],
        "request": [],
        "strategy": [],
        "drawings": [],
        "externalLibraries": [],
        "host": [],
    }


def _normalize_mode(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized not in {"batch", "incremental"}:
        raise ValueError("runtime_mode must be 'batch' or 'incremental'")
    return normalized


def _resolve_call(node: ast.Call) -> tuple[str, str] | None:
    if not isinstance(node.func, ast.Attribute):
        return None
    owner = node.func.value
    if isinstance(owner, ast.Name):
        if owner.id == "ctx":
            drawing = node.func.attr.split("_", 1)[0]
            if drawing in _DRAWING_NAMESPACES:
                return "drawings", drawing
        return owner.id, node.func.attr
    if (
        isinstance(owner, ast.Attribute)
        and isinstance(owner.value, ast.Name)
        and owner.value.id == "ctx"
    ):
        return owner.attr, node.func.attr
    return None


def _resolve_library_call(node: ast.Call) -> tuple[str, str] | None:
    if not isinstance(node.func, ast.Attribute):
        return None
    owner = node.func.value
    if not isinstance(owner, ast.Call) or not isinstance(owner.func, ast.Name):
        return None
    if owner.func.id != "pine_library" or not owner.args:
        return None
    identifier = owner.args[0]
    if not isinstance(identifier, ast.Constant) or not isinstance(identifier.value, str):
        return None
    return identifier.value, node.func.attr


def _dynamic_access(node: ast.Call) -> dict[str, Any] | None:
    if not isinstance(node.func, ast.Name) or node.func.id != "getattr" or len(node.args) < 2:
        return None
    namespace = _attribute_path(node.args[0])
    if namespace.startswith("ctx."):
        namespace = namespace.removeprefix("ctx.")
    if namespace not in _KNOWN_DYNAMIC_NAMESPACES:
        return None
    member = node.args[1]
    if isinstance(member, ast.Constant) and isinstance(member.value, str):
        return None
    return {
        "namespace": namespace,
        "line": int(node.lineno),
        "column": int(node.col_offset) + 1,
        "reason": "dynamic-member-name",
    }


def _attribute_path(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _attribute_path(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _mode_capabilities(mode: str) -> dict[str, set[str]]:
    return {
        "ta": set(INCREMENTAL_TA_CAPABILITIES if mode == "incremental" else BATCH_TA_CAPABILITIES),
        "request": set(REQUEST_CAPABILITIES),
        "strategy": set(
            INCREMENTAL_STRATEGY_CAPABILITIES
            if mode == "incremental"
            else BATCH_STRATEGY_CAPABILITIES
        ),
        "drawings": set(DRAWING_CAPABILITIES),
    }


def _requirement_diagnostics(
    requirements: dict[str, set[str]],
    supported: dict[str, set[str]],
    *,
    mode: str,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for namespace in ("ta", "request", "strategy", "drawings"):
        for member in sorted(requirements[namespace] - supported[namespace]):
            diagnostics.append(
                error_detail(
                    "PYNE_UNSUPPORTED_FEATURE",
                    f"Runtime mode {mode!r} does not support {namespace}.{member}()",
                    hint="Use pn.runtime_capabilities() to select a supported API or mode.",
                )
            )
    return diagnostics


def _unique_diagnostics(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in values:
        key = (item.get("code"), item.get("message"), item.get("line"), item.get("column"))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _library_requirements(
    libraries: dict[str, set[str]],
    *,
    mode: str,
) -> list[dict[str, Any]]:
    descriptors = {item.identifier: item for item in SUPPORTED_PINE_LIBRARIES}
    result: list[dict[str, Any]] = []
    for identifier, members in sorted(libraries.items()):
        descriptor = descriptors.get(identifier)
        supported_members = (
            set(descriptor.members) if descriptor is not None and mode == "batch" else set()
        )
        selected_supported = members & supported_members
        result.append(
            {
                "identifier": identifier,
                "members": sorted(members),
                "supportedMembers": sorted(selected_supported),
                "unsupportedMembers": sorted(members - supported_members),
                "dataRequirements": (
                    list(descriptor.requirements_for(selected_supported))
                    if descriptor is not None
                    else []
                ),
            }
        )
    return result


def _declaration(tree: ast.Module) -> dict[str, Any] | None:
    for node in tree.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Name) or call.func.id not in {"indicator", "strategy", "study"}:
            continue
        title = None
        if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
            title = call.args[0].value
        return {"kind": call.func.id, "title": title}
    return None


def _resource_hints(tree: ast.AST) -> dict[str, bool]:
    paths = {_attribute_path(node) for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    callbacks = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    return {
        "usesState": bool({"state", "var"} & names or any(path.endswith(".state") for path in paths)),
        "usesVarip": "varip" in names or any(path.endswith(".varip") for path in paths),
        "usesPreview": "on_preview" in callbacks,
        "usesTrace": "trace" in names or any(path.startswith("ctx.trace") for path in paths),
        "usesStrategy": "strategy" in names or any("strategy" in path.split(".") for path in paths),
        "emitsSignals": "emit_signal" in names,
        "usesMarketMetadata": bool({"syminfo", "timeframe", "session"} & names),
    }
