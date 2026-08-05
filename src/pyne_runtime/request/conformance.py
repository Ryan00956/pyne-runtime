"""Reusable, test-runner-independent checks for host data providers."""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from .errors import RequestProviderErrorCategory
from .provider import (
    REQUEST_SECURITY_API,
    REQUEST_SECURITY_CAPABILITY_ALIASES,
    REQUEST_SECURITY_LOWER_TF_API,
    REQUEST_SECURITY_LOWER_TF_CAPABILITY_ALIASES,
    DataProvider,
    _provider_supports,
    _request_metadata,
)


_REQUIRED_BAR_FIELDS = frozenset({"time", "open", "high", "low", "close", "volume"})
_DIAGNOSTIC_FIELDS = frozenset(
    {
        "api",
        "symbol",
        "timeframe",
        "start",
        "end",
        "bars",
        "cacheHit",
        "ignoreInvalidSymbol",
        "status",
    }
)


@dataclass(frozen=True)
class ProviderConformanceCheck:
    """One named conformance result."""

    name: str
    status: Literal["passed", "failed", "skipped"]
    detail: str


@dataclass(frozen=True)
class ProviderConformanceReport:
    """Structured report suitable for pytest, unittest, CLI, or CI adapters."""

    checks: tuple[ProviderConformanceCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.status != "failed" for check in self.checks)

    @property
    def failures(self) -> tuple[ProviderConformanceCheck, ...]:
        return tuple(check for check in self.checks if check.status == "failed")

    def assert_ok(self) -> None:
        if self.ok:
            return
        details = "; ".join(f"{check.name}: {check.detail}" for check in self.failures)
        raise AssertionError(f"Data provider conformance failed: {details}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": [
                {"name": check.name, "status": check.status, "detail": check.detail}
                for check in self.checks
            ],
        }


def run_data_provider_conformance(
    provider: DataProvider,
    *,
    chart_ohlcv: list[dict[str, Any]],
    symbol: str,
    timeframe: str,
    lower_timeframe: str | None = None,
    invalid_symbol: str | None = None,
) -> ProviderConformanceReport:
    """Exercise the public provider contract without depending on pytest.

    ``invalid_symbol`` enables the typed invalid-symbol and ignore-path checks.
    ``lower_timeframe`` enables the lower-timeframe capability, result-shape,
    diagnostics, and invalid-symbol checks.
    """

    if not chart_ohlcv:
        raise ValueError("chart_ohlcv must contain at least one bar")
    checks: list[ProviderConformanceCheck] = []

    def record(name: str, func: Any) -> None:
        try:
            detail = func()
        except Exception as exc:
            checks.append(ProviderConformanceCheck(name, "failed", str(exc)))
        else:
            checks.append(ProviderConformanceCheck(name, "passed", detail or "ok"))

    record(
        "capability.request.security",
        lambda: _assert_capability(provider, REQUEST_SECURITY_CAPABILITY_ALIASES),
    )
    if lower_timeframe is not None:
        record(
            "capability.request.security_lower_tf",
            lambda: _assert_capability(
                provider,
                REQUEST_SECURITY_LOWER_TF_CAPABILITY_ALIASES,
            ),
        )

    start, end = _chart_range(chart_ohlcv)
    record(
        "get_ohlcv.result",
        lambda: _assert_ohlcv(provider.get_ohlcv(symbol, timeframe, start, end)),
    )
    record(
        "metadata.result",
        lambda: _assert_metadata(_request_metadata(provider, symbol, timeframe)),
    )
    record(
        "runtime.request.security",
        lambda: _assert_runtime_request(
            provider,
            chart_ohlcv,
            api=REQUEST_SECURITY_API,
            symbol=symbol,
            timeframe=timeframe,
        ),
    )
    if lower_timeframe is not None:
        record(
            "runtime.request.security_lower_tf",
            lambda: _assert_runtime_request(
                provider,
                chart_ohlcv,
                api=REQUEST_SECURITY_LOWER_TF_API,
                symbol=symbol,
                timeframe=lower_timeframe,
            ),
        )

    apis = [(REQUEST_SECURITY_API, timeframe)]
    if lower_timeframe is not None:
        apis.append((REQUEST_SECURITY_LOWER_TF_API, lower_timeframe))
    if invalid_symbol is None:
        checks.append(
            ProviderConformanceCheck(
                "typed.invalid_symbol",
                "skipped",
                "pass invalid_symbol to verify typed invalid-symbol handling",
            )
        )
    else:
        for api, request_timeframe in apis:
            record(
                f"typed.invalid_symbol.{api}",
                lambda api=api, request_timeframe=request_timeframe: _assert_invalid_symbol(
                    provider,
                    chart_ohlcv,
                    api=api,
                    symbol=invalid_symbol,
                    timeframe=request_timeframe,
                ),
            )

    return ProviderConformanceReport(tuple(checks))


def assert_data_provider_conformance(
    provider: DataProvider,
    **kwargs: Any,
) -> ProviderConformanceReport:
    """Run the conformance kit and raise one compact assertion on failure."""

    report = run_data_provider_conformance(provider, **kwargs)
    report.assert_ok()
    return report


def _assert_capability(provider: DataProvider, aliases: tuple[str, ...]) -> str:
    if not _provider_supports(provider, aliases):
        raise AssertionError(f"provider does not declare any supported alias: {aliases}")
    return "supported"


def _chart_range(chart_ohlcv: list[dict[str, Any]]) -> tuple[int, int]:
    times = [int(item["time"]) for item in chart_ohlcv]
    return min(times), max(times)


def _assert_ohlcv(rows: Any) -> str:
    if not isinstance(rows, list):
        raise AssertionError(f"get_ohlcv must return list, got {type(rows).__name__}")
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise AssertionError(f"row {index} is not a mapping")
        missing = sorted(_REQUIRED_BAR_FIELDS - row.keys())
        if missing:
            raise AssertionError(f"row {index} is missing fields: {', '.join(missing)}")
        try:
            int(row["time"])
            for field in ("open", "high", "low", "close", "volume"):
                float(row[field])
        except (TypeError, ValueError) as exc:
            raise AssertionError(f"row {index} contains a non-numeric OHLCV value") from exc
    return f"{len(rows)} bars"


def _assert_metadata(metadata: Any) -> str:
    if not isinstance(metadata, Mapping):
        raise AssertionError("normalized request metadata is not a mapping")
    missing = {"syminfo", "timeframe", "session"} - metadata.keys()
    if missing:
        raise AssertionError(f"normalized metadata is missing: {', '.join(sorted(missing))}")
    return "normalized"


def _request_script(
    *,
    api: str,
    symbol: str,
    timeframe: str,
    ignore_invalid_symbol: bool = False,
) -> str:
    symbol_literal = json.dumps(symbol)
    timeframe_literal = json.dumps(timeframe)
    ignored = "True" if ignore_invalid_symbol else "False"
    if api == REQUEST_SECURITY_API:
        call = (
            f"request.security({symbol_literal}, {timeframe_literal}, close, "
            f"ignore_invalid_symbol={ignored})"
        )
    else:
        call = (
            f"request.security_lower_tf({symbol_literal}, {timeframe_literal}, close, "
            f"ignore_invalid_symbol={ignored}).last()"
        )
    return f'indicator("Provider conformance", overlay=True)\nplot({call}, "Requested")\n'


def _run_request(
    provider: DataProvider,
    chart_ohlcv: list[dict[str, Any]],
    *,
    api: str,
    symbol: str,
    timeframe: str,
    ignore_invalid_symbol: bool = False,
) -> Any:
    from ..api import run

    return run(
        _request_script(
            api=api,
            symbol=symbol,
            timeframe=timeframe,
            ignore_invalid_symbol=ignore_invalid_symbol,
        ),
        chart_ohlcv,
        data_provider=provider,
        executor_mode="inline",
    )


def _assert_runtime_request(
    provider: DataProvider,
    chart_ohlcv: list[dict[str, Any]],
    *,
    api: str,
    symbol: str,
    timeframe: str,
) -> str:
    result = _run_request(
        provider,
        chart_ohlcv,
        api=api,
        symbol=symbol,
        timeframe=timeframe,
    )
    if not result.ok:
        raise AssertionError(f"runtime request failed: {result.code}: {result.error}")
    if not result.lines or not isinstance(result.output, dict):
        raise AssertionError("runtime result does not expose lines and structured output")
    diagnostics = result.meta.get("requestDiagnostics", [])
    matching = [item for item in diagnostics if item.get("api") == api]
    if not matching:
        raise AssertionError("runtime result has no matching request diagnostic")
    missing = _DIAGNOSTIC_FIELDS - matching[-1].keys()
    if missing:
        raise AssertionError(f"request diagnostic is missing: {', '.join(sorted(missing))}")
    return "result shape and diagnostics valid"


def _assert_invalid_symbol(
    provider: DataProvider,
    chart_ohlcv: list[dict[str, Any]],
    *,
    api: str,
    symbol: str,
    timeframe: str,
) -> str:
    failed = _run_request(
        provider,
        chart_ohlcv,
        api=api,
        symbol=symbol,
        timeframe=timeframe,
    )
    expected = RequestProviderErrorCategory.INVALID_SYMBOL.value
    category = (failed.error_detail or {}).get("requestProviderCategory")
    if failed.ok or category != expected:
        raise AssertionError(
            "provider must raise PyneInvalidSymbolError; "
            f"serialized category was {category!r}"
        )
    ignored = _run_request(
        provider,
        chart_ohlcv,
        api=api,
        symbol=symbol,
        timeframe=timeframe,
        ignore_invalid_symbol=True,
    )
    if not ignored.ok:
        raise AssertionError(f"ignore_invalid_symbol path failed: {ignored.error}")
    diagnostics = ignored.meta.get("requestDiagnostics", [])
    if not any(item.get("status") == "ignoredInvalidSymbol" for item in diagnostics):
        raise AssertionError("ignored invalid symbol diagnostic is missing")
    return "typed failure and ignored path valid"
