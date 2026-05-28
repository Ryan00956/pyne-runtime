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
    _REQUEST_LOWER_TF_CAPABILITIES,
    _REQUEST_SECURITY_CAPABILITIES,
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
        if self._provider is None:
            raise PyneRequestError(
                "request.security() requires a host data provider",
                code="PYNE_UNSUPPORTED_FEATURE",
            )
        if not _provider_supports(self._provider, _REQUEST_SECURITY_CAPABILITIES):
            raise PyneRequestError(
                "request.security() requires provider capability 'request.security'",
                code="PYNE_UNSUPPORTED_FEATURE",
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

        start, end = self._context.times[0], self._context.times[-1]
        requested, requested_ctx = self._requested_context(
            str(symbol),
            str(timeframe),
            start,
            end,
            ignore_invalid_symbol=ignore_invalid_symbol,
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
                symbol=str(symbol),
                timeframe=str(timeframe),
                requested_ctx=requested_ctx,
            )
        else:
            requested_values, expression_name = _values_from_field_expression(
                expression,
                requested,
                requested_ctx,
            )

        return _align_request_values(
            symbol=str(symbol),
            timeframe=str(timeframe),
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
        if self._provider is None:
            raise PyneRequestError(
                "request.security_lower_tf() requires a host data provider",
                code="PYNE_UNSUPPORTED_FEATURE",
            )
        if not _provider_supports(self._provider, _REQUEST_LOWER_TF_CAPABILITIES):
            raise PyneRequestError(
                "request.security_lower_tf() requires provider capability "
                "'request.security_lower_tf'",
                code="PYNE_UNSUPPORTED_FEATURE",
            )
        if self._evaluating:
            raise PyneRequestError(
                "Nested request.security_lower_tf() expressions are not supported",
                code="PYNE_UNSUPPORTED_FEATURE",
            )

        start, end = self._context.times[0], self._context.times[-1]
        requested, requested_ctx = self._requested_context(
            str(symbol),
            str(timeframe),
            start,
            end,
            ignore_invalid_symbol=ignore_invalid_symbol,
        )
        if callable(expression):
            requested_values, expression_name = self._evaluate_expression_thunk(
                expression,
                symbol=str(symbol),
                timeframe=str(timeframe),
                requested_ctx=requested_ctx,
            )
        else:
            requested_values, expression_name = _values_from_field_expression(
                expression,
                requested,
                requested_ctx,
            )

        return _group_lower_timeframe_values(
            symbol=str(symbol),
            timeframe=str(timeframe),
            expression_name=expression_name,
            chart_times=self._context.times,
            requested_times=requested_ctx.times,
            requested_values=requested_values,
        )

    def _requested_context(
        self,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
        *,
        ignore_invalid_symbol: bool,
    ) -> tuple[list[dict[str, Any]], PyneContext]:
        if self._provider is None:
            raise PyneRequestError(
                "request context requires a host data provider",
                code="PYNE_UNSUPPORTED_FEATURE",
            )

        key = (symbol, timeframe, int(start), int(end))
        cached = self._requested_context_cache.get(key)
        if cached is not None:
            return cached

        ignored_invalid_symbol = False
        try:
            requested = self._provider.get_ohlcv(symbol, timeframe, start, end)
        except PyneInvalidSymbolError as exc:
            if not ignore_invalid_symbol:
                raise PyneRequestError(
                    f"Invalid symbol for request.security(): {symbol}",
                    code="PYNE_INVALID_SYMBOL",
                ) from exc
            requested = []
            ignored_invalid_symbol = True
        if requested is None:
            if not ignore_invalid_symbol:
                raise PyneRequestError(
                    "request data provider must return a list of OHLCV bars",
                    code="PYNE_RUNTIME_ERROR",
                )
            requested = []
            ignored_invalid_symbol = True
        requested = sorted(requested, key=lambda item: int(item.get("time", 0)))
        request_metadata = (
            _default_request_metadata(symbol, timeframe)
            if ignored_invalid_symbol
            else _request_metadata(self._provider, symbol, timeframe)
        )
        requested_ctx = PyneContext.from_ohlcv(
            requested,
            syminfo=request_metadata["syminfo"],
            timeframe=request_metadata["timeframe"],
            session=request_metadata["session"],
        )
        cached = (requested, requested_ctx)
        if not ignored_invalid_symbol:
            self._requested_context_cache[key] = cached
        return cached

    def _evaluate_expression_thunk(
        self,
        expression: Callable[[RequestEvalContext], Any],
        *,
        symbol: str,
        timeframe: str,
        requested_ctx: PyneContext,
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
            ) from exc
        finally:
            self._evaluating = False

        return _values_from_expression_result(result, requested_ctx), "expression"
