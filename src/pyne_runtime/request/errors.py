"""Request error types."""
from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any


class RequestProviderErrorCategory(str, Enum):
    """Stable, machine-readable request-provider failure categories."""

    MISSING_PROVIDER = "missingProvider"
    UNSUPPORTED_CAPABILITY = "unsupportedCapability"
    CAPABILITY_FAILURE = "capabilityFailure"
    INVALID_SYMBOL = "invalidSymbol"
    PROVIDER_FAILURE = "providerFailure"
    INVALID_RETURN_TYPE = "invalidReturnType"
    INVALID_BAR_SHAPE = "invalidBarShape"
    INVALID_METADATA = "invalidMetadata"
    METADATA_FAILURE = "metadataFailure"
    EXPRESSION_FAILURE = "expressionFailure"


def _category_value(category: RequestProviderErrorCategory | str | None) -> str | None:
    if isinstance(category, RequestProviderErrorCategory):
        return category.value
    return category


class PyneRequestError(Exception):
    """Stable runtime error raised by host-backed request helpers."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "PYNE_UNSUPPORTED_FEATURE",
        category: RequestProviderErrorCategory | str | None = None,
        request_context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.category = _category_value(category)
        self.request_context = dict(request_context or {})

    def with_request_context(self, **context: Any) -> "PyneRequestError":
        self.request_context = {**context, **self.request_context}
        return self


class PyneProviderError(Exception):
    """Typed signal raised by host provider adapters."""

    category = RequestProviderErrorCategory.PROVIDER_FAILURE
    code = "PYNE_RUNTIME_ERROR"


class PyneProviderCapabilityError(PyneProviderError):
    """Provider failed while declaring request capabilities."""

    category = RequestProviderErrorCategory.CAPABILITY_FAILURE


class PyneProviderMetadataError(PyneProviderError):
    """Provider failed while resolving requested-context metadata."""

    category = RequestProviderErrorCategory.METADATA_FAILURE


class PyneProviderDataError(PyneProviderError):
    """Provider failed while retrieving market data."""


class PyneInvalidSymbolError(PyneProviderError):
    """Provider-side signal for Pine-like invalid symbol handling."""

    category = RequestProviderErrorCategory.INVALID_SYMBOL
    code = "PYNE_INVALID_SYMBOL"

    def __init__(self, symbol: str, *, message: str | None = None) -> None:
        super().__init__(message or str(symbol))
        self.symbol = str(symbol)
