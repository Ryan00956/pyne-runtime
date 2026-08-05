"""Pinned adapters for external Pine libraries that Pyne implements explicitly."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .context import PyneContext
from .request import LowerTimeframeSeries, PyneRequestError, RequestModule
from .series import PyneSeries
from .values import is_na_value


TRADINGVIEW_TA_10 = "TradingView/ta/10"


@dataclass(frozen=True)
class PineLibraryDescriptor:
    """Machine-readable declaration for one pinned, locally implemented library."""

    identifier: str
    members: tuple[str, ...]
    data_requirements: tuple[str, ...]


SUPPORTED_PINE_LIBRARIES = (
    PineLibraryDescriptor(
        identifier=TRADINGVIEW_TA_10,
        members=("requestUpAndDownVolume",),
        data_requirements=("request.security_lower_tf",),
    ),
)


class TradingViewTa10Library:
    """The project-used subset of TradingView's public ``ta`` library v10."""

    def __init__(self, ctx: PyneContext, request: RequestModule) -> None:
        self._ctx = ctx
        self._request = request

    def requestUpAndDownVolume(
        self,
        lowerTimeframe: str,
    ) -> tuple[PyneSeries, PyneSeries, PyneSeries]:
        """Return up volume, negative down volume, and their delta per chart bar.

        This v10 adapter deliberately uses host-provided lower-timeframe OHLCV.
        It never estimates intrabars from the chart bars.
        """
        symbol = self._ctx.syminfo.tickerid or self._ctx.syminfo.ticker
        if not symbol:
            raise PyneRequestError(
                "TradingView/ta/10 requires syminfo.tickerid for lower-timeframe data",
                code="PYNE_INVALID_INPUT",
            )
        requested = self._request.security_lower_tf(
            symbol,
            str(lowerTimeframe),
            lambda requested_ctx: (
                requested_ctx.open,
                requested_ctx.close,
                requested_ctx.volume,
            ),
        )
        if not isinstance(requested, tuple) or len(requested) != 3 or not all(
            isinstance(item, LowerTimeframeSeries) for item in requested
        ):
            raise PyneRequestError(
                "TradingView/ta/10 received an invalid lower-timeframe result",
                code="PYNE_RUNTIME_ERROR",
            )

        up_values: list[float] = []
        down_values: list[float] = []
        delta_values: list[float] = []
        for opens, closes, volumes in zip(
            requested[0].groups,
            requested[1].groups,
            requested[2].groups,
        ):
            up = 0.0
            down = 0.0
            seen = False
            for open_value, close_value, volume_value in zip(opens, closes, volumes):
                if any(is_na_value(value) for value in (open_value, close_value, volume_value)):
                    continue
                seen = True
                volume = abs(float(volume_value))
                if float(close_value) > float(open_value):
                    up += volume
                elif float(close_value) < float(open_value):
                    down -= volume
            if not seen:
                up_values.append(np.nan)
                down_values.append(np.nan)
                delta_values.append(np.nan)
            else:
                up_values.append(up)
                down_values.append(down)
                delta_values.append(up + down)
        return (
            PyneSeries(np.asarray(up_values), name="ta10.upVolume"),
            PyneSeries(np.asarray(down_values), name="ta10.downVolume"),
            PyneSeries(np.asarray(delta_values), name="ta10.volumeDelta"),
        )

    request_up_and_down_volume = requestUpAndDownVolume


class PineLibraryRegistry:
    """Execution-bound allowlist for external Pine library adapters."""

    def __init__(self, ctx: PyneContext, request: RequestModule) -> None:
        self._ctx = ctx
        self._request = request

    def load(self, identifier: str) -> Any:
        normalized = str(identifier).strip()
        if normalized == TRADINGVIEW_TA_10:
            return TradingViewTa10Library(self._ctx, self._request)
        raise PyneRequestError(
            f"External Pine library '{normalized}' is not implemented by this runtime",
            code="PYNE_UNSUPPORTED_FEATURE",
        )

    def supported(self) -> list[dict[str, Any]]:
        return [
            {
                "identifier": item.identifier,
                "members": list(item.members),
                "dataRequirements": list(item.data_requirements),
            }
            for item in SUPPORTED_PINE_LIBRARIES
        ]

    __call__ = load
