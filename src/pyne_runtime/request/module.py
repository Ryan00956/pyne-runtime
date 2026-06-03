"""Pine-like request namespace facade."""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from ..context import PyneContext
from ..series import PyneSeries
from ..ta import TaModule
from .alignment import (
    _GAPS_ALIASES,
    _LOOKAHEAD_ALIASES,
    _align_request_values,
    _normalize_request_option,
)
from .errors import PyneInvalidSymbolError, PyneRequestError
from .eval import (
    RequestEvalContext,
    RequestValues,
    _values_from_expression_result,
    _values_from_field_expression,
)
from .lower_tf import LowerTimeframeSeries, _group_lower_timeframe_values
from .provider import (
    REQUEST_SECURITY_API,
    REQUEST_SECURITY_CAPABILITY_ALIASES,
    REQUEST_SECURITY_LOWER_TF_API,
    REQUEST_SECURITY_LOWER_TF_CAPABILITY_ALIASES,
    DataProvider,
    _default_request_metadata,
    _provider_supports,
    _request_metadata,
)


class RequestModule:
    """Pine-like ``request`` namespace bound to one execution context."""

    def __init__(
        self,
        context: PyneContext,
        provider: DataProvider | None = None,
    ) -> None:
        self._context = context
        self._provider = provider
        self._evaluating = False
        self._requested_context_cache: dict[
            tuple[str, str, int, int],
            tuple[list[dict[str, Any]], PyneContext],
        ] = {}
        self._diagnostics: list[dict[str, Any]] = []

    @property
    def diagnostics(self) -> list[dict[str, Any]]:
        """Return host-facing diagnostics for request.* calls in this run."""
        return [dict(item) for item in self._diagnostics]

    def security(
        self,
        symbol: str,
        timeframe: str,
        expression: PyneSeries
        | str
        | tuple[Any, ...]
        | list[Any]
        | Callable[[RequestEvalContext], Any],
        *,
        gaps: str = "off",
        lookahead: str = "off",
        ignore_invalid_symbol: bool = False,
    ) -> PyneSeries | tuple[PyneSeries, ...]:
        """Return a requested symbol/timeframe field aligned to chart bars.

        Field-like expressions such as ``close``, ``close[1]``, or ``"close"``
        remain supported. Callable thunks are evaluated in the requested
        symbol/timeframe context.
        """
        symbol_text = str(symbol)
        timeframe_text = str(timeframe)
        start, end = self._context.times[0], self._context.times[-1]
        request_context = self._request_context_payload(
            REQUEST_SECURITY_API,
            symbol_text,
            timeframe_text,
            start,
            end,
        )
        if self._provider is None:
            raise PyneRequestError(
                "request.security() requires a host data provider",
                code="PYNE_UNSUPPORTED_FEATURE",
                category="missingProvider",
                request_context=request_context,
            )
        try:
            supports_request = _provider_supports(
                self._provider,
                REQUEST_SECURITY_CAPABILITY_ALIASES,
            )
        except PyneRequestError as exc:
            raise exc.with_request_context(**request_context) from exc
        if not supports_request:
            raise PyneRequestError(
                "request.security() requires provider capability 'request.security'",
                code="PYNE_UNSUPPORTED_FEATURE",
                category="unsupportedCapability",
                request_context=request_context,
            )
        if self._evaluating:
            raise PyneRequestError(
                "Nested request.security() expressions are not supported",
                code="PYNE_UNSUPPORTED_FEATURE",
            )
        normalized_gaps = _normalize_request_option(
            gaps,
            name="gaps",
            aliases=_GAPS_ALIASES,
        )
        normalized_lookahead = _normalize_request_option(
            lookahead,
            name="lookahead",
            aliases=_LOOKAHEAD_ALIASES,
        )

        requested, requested_ctx, cache_hit, ignored_invalid_symbol = self._requested_context(
            REQUEST_SECURITY_API,
            symbol_text,
            timeframe_text,
            start,
            end,
            ignore_invalid_symbol=ignore_invalid_symbol,
        )
        self._record_diagnostic(
            api=REQUEST_SECURITY_API,
            symbol=symbol_text,
            timeframe=timeframe_text,
            start=start,
            end=end,
            requested=requested,
            cache_hit=cache_hit,
            ignore_invalid_symbol=ignore_invalid_symbol,
            ignored_invalid_symbol=ignored_invalid_symbol,
        )
        if not requested:
            return PyneSeries(
                np.full(self._context.bar_count, np.nan, dtype=np.float64),
                name=f"request.security({symbol},{timeframe})",
            )

        requested_times = requested_ctx.times
        if callable(expression):
            requested_values, expression_name = self._evaluate_expression_thunk(
                expression,
                symbol=symbol_text,
                timeframe=timeframe_text,
                requested_ctx=requested_ctx,
                request_context=request_context,
            )
        else:
            requested_values, expression_name = _values_from_field_expression(
                expression,
                requested,
                requested_ctx,
            )

        return _align_request_values(
            symbol=symbol_text,
            timeframe=timeframe_text,
            expression_name=expression_name,
            chart_times=self._context.times,
            requested_times=requested_times,
            requested_values=requested_values,
            gaps=normalized_gaps,
            lookahead=normalized_lookahead,
        )

    def security_lower_tf(
        self,
        symbol: str,
        timeframe: str,
        expression: PyneSeries
        | str
        | tuple[Any, ...]
        | list[Any]
        | Callable[[RequestEvalContext], Any],
        *,
        ignore_invalid_symbol: bool = False,
    ) -> LowerTimeframeSeries | tuple[LowerTimeframeSeries, ...]:
        """Return lower-timeframe arrays grouped by chart bar.

        The provider supplies lower-timeframe OHLCV. Pyne evaluates the
        expression in that requested context, then groups requested values into
        ``[chart_time, next_chart_time)`` buckets.
        """
        symbol_text = str(symbol)
        timeframe_text = str(timeframe)
        start, end = self._context.times[0], self._context.times[-1]
        request_context = self._request_context_payload(
            REQUEST_SECURITY_LOWER_TF_API,
            symbol_text,
            timeframe_text,
            start,
            end,
        )
        if self._provider is None:
            raise PyneRequestError(
                "request.security_lower_tf() requires a host data provider",
                code="PYNE_UNSUPPORTED_FEATURE",
                category="missingProvider",
                request_context=request_context,
            )
        try:
            supports_request = _provider_supports(
                self._provider,
                REQUEST_SECURITY_LOWER_TF_CAPABILITY_ALIASES,
            )
        except PyneRequestError as exc:
            raise exc.with_request_context(**request_context) from exc
        if not supports_request:
            raise PyneRequestError(
                "request.security_lower_tf() requires provider capability "
                "'request.security_lower_tf'",
                code="PYNE_UNSUPPORTED_FEATURE",
                category="unsupportedCapability",
                request_context=request_context,
            )
        if self._evaluating:
            raise PyneRequestError(
                "Nested request.security_lower_tf() expressions are not supported",
                code="PYNE_UNSUPPORTED_FEATURE",
            )

        requested, requested_ctx, cache_hit, ignored_invalid_symbol = self._requested_context(
            REQUEST_SECURITY_LOWER_TF_API,
            symbol_text,
            timeframe_text,
            start,
            end,
            ignore_invalid_symbol=ignore_invalid_symbol,
        )
        self._record_diagnostic(
            api=REQUEST_SECURITY_LOWER_TF_API,
            symbol=symbol_text,
            timeframe=timeframe_text,
            start=start,
            end=end,
            requested=requested,
            cache_hit=cache_hit,
            ignore_invalid_symbol=ignore_invalid_symbol,
            ignored_invalid_symbol=ignored_invalid_symbol,
        )
        if callable(expression):
            requested_values, expression_name = self._evaluate_expression_thunk(
                expression,
                symbol=symbol_text,
                timeframe=timeframe_text,
                requested_ctx=requested_ctx,
                request_context=request_context,
            )
        else:
            requested_values, expression_name = _values_from_field_expression(
                expression,
                requested,
                requested_ctx,
            )

        return _group_lower_timeframe_values(
            symbol=symbol_text,
            timeframe=timeframe_text,
            expression_name=expression_name,
            chart_times=self._context.times,
            requested_times=requested_ctx.times,
            requested_values=requested_values,
        )

    def _requested_context(
        self,
        api: str,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
        *,
        ignore_invalid_symbol: bool,
    ) -> tuple[list[dict[str, Any]], PyneContext, bool, bool]:
        request_context = self._request_context_payload(api, symbol, timeframe, start, end)
        if self._provider is None:
            raise PyneRequestError(
                "request context requires a host data provider",
                code="PYNE_UNSUPPORTED_FEATURE",
                category="missingProvider",
                request_context=request_context,
            )

        key = (symbol, timeframe, int(start), int(end))
        cached = self._requested_context_cache.get(key)
        if cached is not None:
            requested, requested_ctx = cached
            return requested, requested_ctx, True, False

        ignored_invalid_symbol = False
        try:
            requested = self._provider.get_ohlcv(symbol, timeframe, start, end)
        except PyneInvalidSymbolError as exc:
            if not ignore_invalid_symbol:
                raise PyneRequestError(
                    f"Invalid symbol for request.security(): {symbol}",
                    code="PYNE_INVALID_SYMBOL",
                    category="invalidSymbol",
                    request_context=request_context,
                ) from exc
            requested = []
            ignored_invalid_symbol = True
        except PyneRequestError as exc:
            raise exc.with_request_context(**request_context) from exc
        except Exception as exc:
            raise PyneRequestError(
                f"request data provider failed: {exc}",
                code="PYNE_RUNTIME_ERROR",
                category="providerFailure",
                request_context=request_context,
            ) from exc
        if requested is None:
            if not ignore_invalid_symbol:
                raise PyneRequestError(
                    "request data provider must return a list of OHLCV bars",
                    code="PYNE_RUNTIME_ERROR",
                    category="invalidReturnType",
                    request_context=request_context,
                )
            requested = []
            ignored_invalid_symbol = True
        if not isinstance(requested, list):
            raise PyneRequestError(
                "request data provider must return a list of OHLCV bars",
                code="PYNE_RUNTIME_ERROR",
                category="invalidReturnType",
                request_context=request_context,
            )
        for index, item in enumerate(requested):
            if not isinstance(item, dict):
                raise PyneRequestError(
                    f"request data provider returned non-mapping bar at row {index}",
                    code="PYNE_RUNTIME_ERROR",
                    category="invalidBarShape",
                    request_context=request_context,
                )
            if "time" not in item:
                raise PyneRequestError(
                    f"request data provider returned OHLCV bar without time at row {index}",
                    code="PYNE_RUNTIME_ERROR",
                    category="invalidBarShape",
                    request_context=request_context,
                )
        requested = sorted(requested, key=lambda item: int(item.get("time", 0)))
        if ignored_invalid_symbol:
            request_metadata = _default_request_metadata(symbol, timeframe)
        else:
            try:
                request_metadata = _request_metadata(self._provider, symbol, timeframe)
            except PyneRequestError as exc:
                raise exc.with_request_context(**request_context) from exc
        try:
            requested_ctx = PyneContext.from_ohlcv(
                requested,
                syminfo=request_metadata["syminfo"],
                timeframe=request_metadata["timeframe"],
                session=request_metadata["session"],
                allow_empty=True,
                require_unique_times=False,
            )
        except (TypeError, ValueError) as exc:
            raise PyneRequestError(
                f"request data provider returned invalid OHLCV: {exc}",
                code="PYNE_RUNTIME_ERROR",
                category="invalidBarShape",
                request_context=request_context,
            ) from exc
        cached = (requested, requested_ctx)
        if not ignored_invalid_symbol:
            self._requested_context_cache[key] = cached
        return requested, requested_ctx, False, ignored_invalid_symbol

    def _record_diagnostic(
        self,
        *,
        api: str,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
        requested: list[dict[str, Any]],
        cache_hit: bool,
        ignore_invalid_symbol: bool,
        ignored_invalid_symbol: bool,
    ) -> None:
        self._diagnostics.append({
            "api": api,
            "symbol": symbol,
            "timeframe": timeframe,
            "start": int(start),
            "end": int(end),
            "bars": len(requested),
            "cacheHit": cache_hit,
            "ignoreInvalidSymbol": ignore_invalid_symbol,
            "status": "ignoredInvalidSymbol" if ignored_invalid_symbol else "ok",
        })

    def _request_context_payload(
        self,
        api: str,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> dict[str, Any]:
        return {
            "api": api,
            "symbol": symbol,
            "timeframe": timeframe,
            "start": int(start),
            "end": int(end),
        }

    def _evaluate_expression_thunk(
        self,
        expression: Callable[[RequestEvalContext], Any],
        *,
        symbol: str,
        timeframe: str,
        requested_ctx: PyneContext,
        request_context: dict[str, Any],
    ) -> tuple[RequestValues, str]:
        requested_ta = TaModule(requested_ctx)
        eval_ctx = RequestEvalContext(
            symbol=symbol,
            timeframe=timeframe,
            context=requested_ctx,
            ta=requested_ta,
        )
        try:
            self._evaluating = True
            result = expression(eval_ctx)
        except PyneRequestError:
            raise
        except Exception as exc:
            raise PyneRequestError(
                f"request.security() expression failed: {exc}",
                code="PYNE_RUNTIME_ERROR",
                category="expressionFailure",
                request_context=request_context,
            ) from exc
        finally:
            self._evaluating = False

        return _values_from_expression_result(result, requested_ctx), "expression"
