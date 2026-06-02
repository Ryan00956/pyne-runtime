"""Provider protocol and metadata helpers for host-backed requests."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from .errors import PyneRequestError

_REQUEST_SECURITY_CAPABILITIES = ("request.security", "security", "ohlcv")
_REQUEST_LOWER_TF_CAPABILITIES = ("request.security_lower_tf", "security_lower_tf", "lower_tf")
_MISSING = object()

class DataProvider(Protocol):
    """Host interface used by ``request.security()``.

    Pyne defines alignment semantics, but the host owns market data retrieval.
    """

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> list[dict[str, Any]]:
        """Return OHLCV bars for ``symbol`` and ``timeframe`` in ``[start, end]``."""


def _provider_supports(provider: DataProvider, capability_names: tuple[str, ...]) -> bool:
    declared_capabilities = getattr(provider, "capabilities", _MISSING)
    if declared_capabilities is _MISSING:
        return True
    if callable(declared_capabilities):
        declared_capabilities = declared_capabilities()
    if declared_capabilities is None:
        return False
    if isinstance(declared_capabilities, dict):
        for capability in capability_names:
            if capability in declared_capabilities:
                return bool(declared_capabilities[capability])
        return False
    if isinstance(declared_capabilities, (set, list, tuple)):
        declared = set(declared_capabilities)
        return any(capability in declared for capability in capability_names)
    return bool(declared_capabilities)

def _request_metadata(provider: DataProvider, symbol: str, timeframe: str) -> dict[str, Any]:
    declared_metadata = getattr(provider, "get_request_metadata", None)
    if callable(declared_metadata):
        try:
            declared_metadata = declared_metadata(symbol, timeframe)
        except PyneRequestError:
            raise
        except Exception as exc:
            raise PyneRequestError(
                f"request metadata provider failed: {exc}",
                code="PYNE_RUNTIME_ERROR",
            ) from exc
    else:
        declared_metadata = getattr(provider, "request_metadata", None)
        if callable(declared_metadata):
            try:
                declared_metadata = declared_metadata(symbol, timeframe)
            except PyneRequestError:
                raise
            except Exception as exc:
                raise PyneRequestError(
                    f"request metadata provider failed: {exc}",
                    code="PYNE_RUNTIME_ERROR",
                ) from exc

    if declared_metadata is None:
        declared_metadata = {}
    if not isinstance(declared_metadata, Mapping):
        raise PyneRequestError(
            "request metadata must be a mapping with optional syminfo, timeframe, and session keys",
            code="PYNE_RUNTIME_ERROR",
        )

    syminfo = declared_metadata.get("syminfo", declared_metadata.get("symbol_info"))
    timeframe_info = declared_metadata.get(
        "timeframe",
        declared_metadata.get("timeframe_info", timeframe),
    )
    session = declared_metadata.get("session", declared_metadata.get("session_info"))
    return {
        "syminfo": _symbol_metadata_with_defaults(symbol, syminfo),
        "timeframe": timeframe_info,
        "session": session,
    }

def _default_request_metadata(symbol: str, timeframe: str) -> dict[str, Any]:
    return {
        "syminfo": _symbol_metadata_with_defaults(symbol, None),
        "timeframe": timeframe,
        "session": None,
    }

def _symbol_metadata_with_defaults(symbol: str, syminfo: Any) -> Any:
    defaults = {"tickerid": symbol, "ticker": symbol}
    if syminfo is None:
        return defaults
    if isinstance(syminfo, Mapping):
        return {**defaults, **syminfo}
    return syminfo
