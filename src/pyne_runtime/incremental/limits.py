"""Incremental runtime safe-mode limits and state containers."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from ..security import PyneSecurityError, PyneSecurityPolicy

SAFE_MAX_WINDOW_SIZE = 10_000
SAFE_MAX_TOTAL_WINDOW_ITEMS = 50_000
SAFE_MAX_STATE_KEYS = 100


class StateCell:
    """Mutable state value exposed to incremental scripts."""

    def __init__(self, value: Any) -> None:
        self.value = value


class Window:
    """Fixed-size rolling window exposed to incremental scripts."""

    def __init__(self, size: int) -> None:
        self.size = max(int(size), 1)
        self._values: deque[Any] = deque(maxlen=self.size)

    def append(self, value: Any) -> None:
        self._values.append(value)

    @property
    def full(self) -> bool:
        return len(self._values) >= self.size

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self):
        return iter(self._values)

    def __getitem__(self, index: int) -> Any:
        return list(self._values)[index]

    def values(self) -> list[Any]:
        return list(self._values)


@dataclass
class IncrementalLimits:
    enabled: bool = False
    max_window_size: int = SAFE_MAX_WINDOW_SIZE
    max_total_window_items: int = SAFE_MAX_TOTAL_WINDOW_ITEMS
    max_state_keys: int = SAFE_MAX_STATE_KEYS

    @classmethod
    def for_policy(cls, policy: PyneSecurityPolicy) -> "IncrementalLimits":
        return cls(enabled=policy.mode == "safe")


class _LimitTracker:
    def __init__(self, limits: IncrementalLimits) -> None:
        self.limits = limits
        self.total_window_items = 0

    def reserve_window(self, size: int, *, label: str) -> None:
        if not self.limits.enabled:
            return
        normalized = max(int(size), 1)
        if normalized > self.limits.max_window_size:
            raise PyneSecurityError(
                f"Incremental window '{label}' size {normalized} exceeds safe-mode limit "
                f"{self.limits.max_window_size}"
            )
        next_total = self.total_window_items + normalized
        if next_total > self.limits.max_total_window_items:
            raise PyneSecurityError(
                f"Incremental windows need {next_total} items, exceeding safe-mode total "
                f"limit {self.limits.max_total_window_items}"
            )
        self.total_window_items = next_total
