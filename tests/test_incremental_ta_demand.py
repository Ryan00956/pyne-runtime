from __future__ import annotations

import math
from typing import Any

import pyne_runtime as pn


def _bars(count: int = 48) -> list[dict[str, float]]:
    result = []
    for index in range(count):
        close = 100.0 + math.sin(index * 0.73) * 5.0 + index * 0.07
        result.append(
            {
                "time": (index + 1) * 60,
                "open": close - 0.3,
                "high": close + 1.0 + (index % 3) * 0.2,
                "low": close - 0.9 - (index % 2) * 0.2,
                "close": close,
                "volume": 100.0 + index,
            }
        )
    return result


BATCH_SCRIPT = """
indicator("Demand TA")
ph = ta.pivothigh(high, 2, 2)
pl = ta.pivotlow(low, 2, 2)
changed = ta.change(close, 3)
mid, upper, lower = ta.bb(close, 4, 2)
levels = ta.pivot_point_levels("Traditional", bar_index % 8 == 0)
plot(ph, "Pivot High Confirmed")
plot(pl, "Pivot Low Confirmed")
plot(changed, "Change")
plot(ta.highestbars(close, 5), "Highest Bars")
plot(ta.lowestbars(close, 5), "Lowest Bars")
plot(ta.tr(), "TR")
plot(ta.cum(changed), "Cum")
plot(ta.swma(close), "SWMA")
plot(mid, "BB Mid")
plot(upper, "BB Upper")
plot(lower, "BB Lower")
plot(ta.alma(close, 5, 0.85, 6), "ALMA")
plot(ta.dev(close, 5), "DEV")
plot(levels.get(0), "Pivot P")
plot(levels.get(1), "Pivot R1")
plot(levels.get(2), "Pivot S1")
"""


INCREMENTAL_SCRIPT = """
indicator("Demand TA", mode="incremental")

def init(ctx):
    ctx.ta.pivothigh("ph", 2, 2)
    ctx.ta.pivotlow("pl", 2, 2)
    ctx.ta.change("change", 3)
    ctx.ta.highestbars("highestbars", 5)
    ctx.ta.lowestbars("lowestbars", 5)
    ctx.ta.tr("tr")
    ctx.ta.cum("cum")
    ctx.ta.swma("swma")
    ctx.ta.bb("bb", 4, 2)
    ctx.ta.alma("alma", 5, 0.85, 6)
    ctx.ta.dev("dev", 5)
    ctx.ta.pivot_point_levels("levels", "Traditional")

def on_bar(ctx, bar):
    ph = ctx.ta.pivothigh("ph").update(bar.high)
    pl = ctx.ta.pivotlow("pl").update(bar.low)
    change = ctx.ta.change("change").update(bar.close)
    mid, upper, lower = ctx.ta.bb("bb").update(bar.close)
    levels = ctx.ta.pivot_point_levels("levels").update(
        bar,
        anchor=bar.bar_index % 8 == 0,
    )
    ctx.plot("Pivot High Confirmed", ph)
    ctx.plot("Pivot Low Confirmed", pl)
    ctx.plot("Change", change)
    ctx.plot("Highest Bars", ctx.ta.highestbars("highestbars").update(bar.close))
    ctx.plot("Lowest Bars", ctx.ta.lowestbars("lowestbars").update(bar.close))
    ctx.plot("TR", ctx.ta.tr("tr").update(bar))
    ctx.plot("Cum", ctx.ta.cum("cum").update(change))
    ctx.plot("SWMA", ctx.ta.swma("swma").update(bar.close))
    ctx.plot("BB Mid", mid)
    ctx.plot("BB Upper", upper)
    ctx.plot("BB Lower", lower)
    ctx.plot("ALMA", ctx.ta.alma("alma").update(bar.close))
    ctx.plot("DEV", ctx.ta.dev("dev").update(bar.close))
    ctx.plot("Pivot P", levels[0])
    ctx.plot("Pivot R1", levels[1])
    ctx.plot("Pivot S1", levels[2])
"""


def _rounded(result: Any) -> dict[str, list[float]]:
    return {
        line["name"]: [round(float(point["value"]), 10) for point in line["data"]]
        for line in result.lines
    }


def test_corpus_demand_incremental_ta_matches_batch() -> None:
    report = pn.run_incremental_parity(
        batch_script=BATCH_SCRIPT,
        incremental_script=INCREMENTAL_SCRIPT,
        bars=_bars(),
        settings=pn.PyneSettings(executor_mode="inline", timeframe="1"),
        normalizer=_rounded,
    )

    report.assert_ok()


def test_corpus_demand_incremental_ta_survives_typed_state_restore() -> None:
    bars = _bars()
    settings = pn.PyneSettings(executor_mode="inline", timeframe="1")
    original = pn.PyneIncrementalSession(script=INCREMENTAL_SCRIPT, settings=settings)
    original.seed(bars[:27])
    restored = pn.PyneIncrementalSession.from_portable_snapshot(
        original.snapshot_portable(mode="state"),
        script=INCREMENTAL_SCRIPT,
        settings=settings,
    )

    for bar in bars[27:]:
        assert restored.on_bar_closed(bar) == original.on_bar_closed(bar)
