from __future__ import annotations

from typing import Any

import pyne_runtime as pn


NAMES = ("RMA", "WMA", "VWMA", "Variance", "Stdev", "Stoch", "CCI", "Supertrend")


def _bars(count: int = 14) -> list[dict[str, float]]:
    closes = [10, 11, 10.5, 12, 11.25, 13, 12.5, 14, 13.5, 15, 14.25, 16, 15.5, 17]
    return [
        {
            "time": index + 1,
            "open": close - 0.25,
            "high": close + 1.0 + (index % 2) * 0.25,
            "low": close - 1.0,
            "close": close,
            "volume": 10.0 + index * 3.0,
        }
        for index, close in enumerate(closes[:count])
    ]


BATCH_SCRIPT = """
indicator("Expanded TA")
plot(ta.rma(close, 3), "RMA")
plot(ta.wma(close, 3), "WMA")
plot(ta.vwma(close, 3, volume), "VWMA")
plot(ta.variance(close, 3), "Variance")
plot(ta.stdev(close, 3), "Stdev")
plot(ta.stoch(close, high, low, 3), "Stoch")
plot(ta.cci(hlc3, 3), "CCI")
supertrend_line, direction = ta.supertrend(2.0, 3)
plot(supertrend_line, "Supertrend")
"""


INCREMENTAL_SCRIPT = """
indicator("Expanded TA", mode="incremental")

def init(ctx):
    ctx.ta.rma("rma", period=3)
    ctx.ta.wma("wma", period=3)
    ctx.ta.vwma("vwma", period=3)
    ctx.ta.variance("variance", period=3)
    ctx.ta.stdev("stdev", period=3)
    ctx.ta.stoch("stoch", period=3)
    ctx.ta.cci("cci", period=3)
    ctx.ta.supertrend("supertrend", factor=2.0, atr_period=3)

def on_bar(ctx, bar):
    ctx.plot("RMA", ctx.ta.rma("rma").update(bar.close))
    ctx.plot("WMA", ctx.ta.wma("wma").update(bar.close))
    ctx.plot("VWMA", ctx.ta.vwma("vwma").update(bar.close, bar.volume))
    ctx.plot("Variance", ctx.ta.variance("variance").update(bar.close))
    ctx.plot("Stdev", ctx.ta.stdev("stdev").update(bar.close))
    ctx.plot("Stoch", ctx.ta.stoch("stoch").update(bar.close, bar.high, bar.low))
    typical = (bar.high + bar.low + bar.close) / 3.0
    ctx.plot("CCI", ctx.ta.cci("cci").update(typical))
    supertrend_line, direction = ctx.ta.supertrend("supertrend").update(bar)
    ctx.plot("Supertrend", supertrend_line)
"""


def _rounded_view(result: Any) -> dict[str, list[float]]:
    return {
        name: [round(float(value), 10) for value in result.values(name)]
        for name in NAMES
    }


def test_expanded_incremental_ta_matches_batch_results() -> None:
    report = pn.run_incremental_parity(
        batch_script=BATCH_SCRIPT,
        incremental_script=INCREMENTAL_SCRIPT,
        bars=_bars(),
        normalizer=_rounded_view,
    )

    report.assert_ok()


def test_expanded_incremental_ta_survives_portable_restore() -> None:
    bars = _bars()
    settings = pn.PyneSettings(executor_mode="inline", timeframe="1S")
    original = pn.PyneIncrementalSession(script=INCREMENTAL_SCRIPT, settings=settings)
    original.seed(bars[:8])

    restored = pn.PyneIncrementalSession.from_portable_snapshot(
        original.snapshot_portable(),
        script=INCREMENTAL_SCRIPT,
        settings=settings,
    )

    for bar in bars[8:]:
        expected = original.on_bar_closed(bar)
        actual = restored.on_bar_closed(bar)
        assert actual == expected
