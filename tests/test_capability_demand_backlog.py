from __future__ import annotations

import re
from pathlib import Path

import pyne_runtime as pn


ROOT = Path(__file__).resolve().parents[1]
BACKLOG = ROOT / "docs" / "development" / "capability_demand_backlog_zh.md"
REQUIRED_COLUMNS = (
    "capability",
    "kind",
    "blocking workload",
    "files touched",
    "modes",
    "owner",
    "evidence plan",
    "risk",
    "decision",
)
BATCH_ONLY_INCREMENTAL = (
    "cmo",
    "correlation",
    "donchian",
    "falling",
    "keltner",
    "linreg",
    "mom",
    "nz",
    "obv",
    "percentile_linear_interpolation",
    "percentile_nearest_rank",
    "rising",
    "roc",
    "shift",
    "tsi",
    "volume_sma",
    "wpr",
)
SOURCE_ECHO_NEEDLES = (
    "indicator(",
    "study(",
    "strategy(",
    "//@version",
    "plot(",
)


def _tables(body: str) -> list[list[tuple[str, ...]]]:
    tables: list[list[tuple[str, ...]]] = []
    current: list[tuple[str, ...]] = []
    for line in body.splitlines():
        if line.startswith("|"):
            cells = tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
            current.append(cells)
            continue
        if current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def test_demand_backlog_has_required_columns_and_no_source_echo() -> None:
    body = BACKLOG.read_text(encoding="utf-8")
    assert "104" in body
    assert "1,643,207" in body
    assert "02ca3c50ff349fcf4c4adbde787abc9f8d4643bb254086a475b0c6344fc0dc3e" in body
    for needle in SOURCE_ECHO_NEEDLES:
        assert needle not in body

    headers = []
    for table in _tables(body):
        header = tuple(cell.lower() for cell in table[0])
        if header[: len(REQUIRED_COLUMNS)] == REQUIRED_COLUMNS:
            headers.append(header)
    assert headers, "demand tables must use the required column set"


def test_demand_backlog_covers_batch_only_incremental_pool() -> None:
    body = BACKLOG.read_text(encoding="utf-8")
    batch = set(pn.BATCH_TA_CAPABILITIES)
    incremental = set(pn.INCREMENTAL_TA_CAPABILITIES)
    live_pool = batch - incremental
    assert live_pool == set(BATCH_ONLY_INCREMENTAL)

    for member in live_pool:
        assert f"`ctx.ta.{member}`" in body
        assert re.search(
            rf"`ctx\.ta\.{re.escape(member)}`\s*\|.*\|\s*defer\s*\|?\s*$",
            body,
            flags=re.MULTILINE,
        )


def test_demand_backlog_has_no_unjustified_p0_implement_rows() -> None:
    body = BACKLOG.read_text(encoding="utf-8")
    p0_section = body.split("## P0", 1)[1].split("## P1", 1)[0]
    assert "_(none)_" in p0_section
    assert re.search(r"\|\s*implement\s*\|?\s*$", p0_section, flags=re.MULTILINE) is None
