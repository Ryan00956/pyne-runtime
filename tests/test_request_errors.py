from __future__ import annotations

import pyne_runtime as pn
from pyne_runtime import request


def test_request_error_metadata_is_public() -> None:
    err = pn.PyneRequestError(
        "provider failed",
        code="PYNE_RUNTIME_ERROR",
        category="providerFailure",
        request_context={"api": "request.security", "symbol": "BTCUSDT"},
    )

    assert str(err) == "provider failed"
    assert err.code == "PYNE_RUNTIME_ERROR"
    assert err.category == "providerFailure"
    assert err.request_context == {
        "api": "request.security",
        "symbol": "BTCUSDT",
    }
    assert request.PyneRequestError is pn.PyneRequestError


def test_request_error_context_merge_preserves_existing_keys() -> None:
    err = pn.PyneRequestError(
        "provider failed",
        request_context={"api": "request.security"},
    )

    returned = err.with_request_context(
        api="request.security_lower_tf",
        symbol="ETHUSDT",
        timeframe="5",
    )

    assert returned is err
    assert err.request_context == {
        "api": "request.security",
        "symbol": "ETHUSDT",
        "timeframe": "5",
    }


def test_invalid_symbol_error_exposes_symbol() -> None:
    err = pn.PyneInvalidSymbolError("MISSING")

    assert str(err) == "MISSING"
    assert err.symbol == "MISSING"
    assert request.PyneInvalidSymbolError is pn.PyneInvalidSymbolError


def test_invalid_symbol_error_allows_custom_message() -> None:
    err = pn.PyneInvalidSymbolError("MISSING", message="symbol is not routed")

    assert str(err) == "symbol is not routed"
    assert err.symbol == "MISSING"


def test_provider_error_categories_are_typed_but_serialize_as_strings() -> None:
    err = pn.PyneRequestError(
        "offline",
        category=pn.RequestProviderErrorCategory.PROVIDER_FAILURE,
    )

    assert err.category == "providerFailure"
    assert issubclass(pn.PyneProviderDataError, pn.PyneProviderError)
    assert pn.PyneProviderMetadataError.category.value == "metadataFailure"
    assert pn.PyneProviderCapabilityError.category.value == "capabilityFailure"
