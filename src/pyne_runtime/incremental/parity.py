"""Test-runner-independent batch/incremental semantic parity helpers."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping

from ..request.provider import DataProvider
from ..settings import PyneSettings

if TYPE_CHECKING:
    from ..result import PyneResult


ParityNormalizer = Callable[["PyneResult"], Any]


@dataclass(frozen=True)
class IncrementalParityDifference:
    """One stable path where batch and incremental semantic views differ."""

    path: str
    batch: Any
    incremental: Any


@dataclass(frozen=True)
class IncrementalParityReport:
    """Results and structured differences for one parity execution."""

    batch_result: PyneResult
    incremental_result: PyneResult
    batch_view: Any
    incremental_view: Any
    differences: tuple[IncrementalParityDifference, ...]

    @property
    def ok(self) -> bool:
        return (
            self.batch_result.ok
            and self.incremental_result.ok
            and not self.differences
        )

    def assert_ok(self) -> None:
        """Raise an ordinary assertion with bounded, readable differences."""
        if self.ok:
            return
        if not self.batch_result.ok:
            raise AssertionError(f"Batch execution failed: {self.batch_result.error}")
        if not self.incremental_result.ok:
            raise AssertionError(
                f"Incremental execution failed: {self.incremental_result.error}"
            )
        detail = "; ".join(
            f"{item.path}: batch={item.batch!r}, incremental={item.incremental!r}"
            for item in self.differences[:10]
        )
        if len(self.differences) > 10:
            detail += f"; ... {len(self.differences) - 10} more"
        raise AssertionError(f"Batch/incremental parity failed: {detail}")


def run_incremental_parity(
    *,
    batch_script: str,
    incremental_script: str,
    bars: Iterable[Mapping[str, Any]],
    params: dict[str, Any] | None = None,
    settings: PyneSettings | None = None,
    data_provider: DataProvider | None = None,
    syminfo: Any = None,
    timeframe: Any = None,
    session: Any = None,
    normalizer: ParityNormalizer | None = None,
    max_differences: int = 100,
) -> IncrementalParityReport:
    """Execute paired scripts and compare stable host-facing semantics.

    The scripts may differ syntactically because incremental callbacks consume
    scalar bars while batch scripts operate on full series. The default view
    removes transport-only plot identifiers but preserves titles, panes,
    styling, points, drawing objects, and strategy reports. A caller can supply
    a stricter or domain-specific ``normalizer`` without depending on pytest.
    """
    from ..api import run

    materialized = [dict(item) for item in bars]
    shared = {
        "params": params,
        "settings": settings,
        "executor_mode": "inline",
        "data_provider": data_provider,
        "syminfo": syminfo,
        "timeframe": timeframe,
        "session": session,
    }
    batch_result = run(batch_script, materialized, **shared)
    incremental_result = run(incremental_script, materialized, **shared)
    project = normalizer or _default_semantic_view
    batch_view = project(batch_result) if batch_result.ok else None
    incremental_view = project(incremental_result) if incremental_result.ok else None
    differences: list[IncrementalParityDifference] = []
    if batch_result.ok and incremental_result.ok:
        _collect_differences(
            "$",
            batch_view,
            incremental_view,
            differences,
            max_differences=max(int(max_differences), 1),
        )
    return IncrementalParityReport(
        batch_result=batch_result,
        incremental_result=incremental_result,
        batch_view=batch_view,
        incremental_view=incremental_view,
        differences=tuple(differences),
    )


def _default_semantic_view(result: PyneResult) -> dict[str, Any]:
    output = copy.deepcopy(result.output)
    semantic: dict[str, Any] = {}
    for key in ("lines", "candles", "histograms", "markers"):
        values = output.get(key)
        if isinstance(values, list):
            semantic[key] = sorted(
                (_normalize_series_entry(key, item) for item in values),
                key=_series_sort_key,
            )
    for key in ("objects", "strategy", "signals", "hlines", "fills", "bgcolors", "barcolors"):
        if key in output:
            semantic[key] = output[key]
    return semantic


def _normalize_series_entry(key: str, value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    normalized = {name: item for name, item in value.items() if name != "id"}
    if key == "lines":
        normalized.pop("per_bar_color", None)
    return normalized


def _series_sort_key(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict):
        return ("", repr(value))
    return (str(value.get("title") or value.get("name") or ""), repr(value.get("pane")))


def _collect_differences(
    path: str,
    batch: Any,
    incremental: Any,
    differences: list[IncrementalParityDifference],
    *,
    max_differences: int,
) -> None:
    if len(differences) >= max_differences:
        return
    if isinstance(batch, dict) and isinstance(incremental, dict):
        for key in sorted(set(batch) | set(incremental), key=str):
            child = f"{path}.{key}"
            if key not in batch:
                differences.append(IncrementalParityDifference(child, None, incremental[key]))
            elif key not in incremental:
                differences.append(IncrementalParityDifference(child, batch[key], None))
            else:
                _collect_differences(
                    child,
                    batch[key],
                    incremental[key],
                    differences,
                    max_differences=max_differences,
                )
            if len(differences) >= max_differences:
                return
        return
    if isinstance(batch, list) and isinstance(incremental, list):
        for index in range(max(len(batch), len(incremental))):
            child = f"{path}[{index}]"
            if index >= len(batch):
                differences.append(IncrementalParityDifference(child, None, incremental[index]))
            elif index >= len(incremental):
                differences.append(IncrementalParityDifference(child, batch[index], None))
            else:
                _collect_differences(
                    child,
                    batch[index],
                    incremental[index],
                    differences,
                    max_differences=max_differences,
                )
            if len(differences) >= max_differences:
                return
        return
    if batch != incremental:
        differences.append(IncrementalParityDifference(path, batch, incremental))
