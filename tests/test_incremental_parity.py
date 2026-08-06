from __future__ import annotations

import pyne_runtime as pn
import pytest


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 10, "open": 1, "high": 3, "low": 0.5, "close": 2, "volume": 10},
        {"time": 20, "open": 2, "high": 4, "low": 1.5, "close": 3, "volume": 20},
    ]


def test_incremental_parity_framework_accepts_semantically_equal_candles() -> None:
    report = pn.run_incremental_parity(
        batch_script="""
indicator("Candles", overlay=True)
plotcandle(open, high, low, close, "Synthetic", color=color.green)
""",
        incremental_script="""
indicator("Candles", mode="incremental", overlay=True)
def on_bar(ctx, bar):
    ctx.plotcandle(bar.open, bar.high, bar.low, bar.close, "Synthetic", color=color.green)
""",
        bars=_bars(),
    )

    assert report.ok
    assert report.differences == ()
    report.assert_ok()


def test_incremental_parity_framework_reports_stable_difference_paths() -> None:
    report = pn.run_incremental_parity(
        batch_script='indicator("Line"); plot(close, "Close")',
        incremental_script="""
indicator("Line", mode="incremental")
def on_bar(ctx, bar):
    ctx.plot("Close", bar.close + 1)
""",
        bars=_bars(),
        normalizer=lambda result: result.values("Close"),
    )

    assert not report.ok
    assert report.differences[0].path == "$[0]"
    with pytest.raises(AssertionError, match="Batch/incremental parity failed"):
        report.assert_ok()


def test_incremental_parity_framework_preserves_execution_failures() -> None:
    report = pn.run_incremental_parity(
        batch_script='indicator("Good"); plot(close, "Close")',
        incremental_script='indicator("Bad", mode="incremental")',
        bars=_bars(),
    )

    assert not report.ok
    assert not report.incremental_result.ok
    with pytest.raises(AssertionError, match="Incremental execution failed"):
        report.assert_ok()
