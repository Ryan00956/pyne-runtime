"""Drawing object namespace helpers."""

from __future__ import annotations

from typing import Any


class _Namespace:
    def __init__(self, **entries: Any) -> None:
        self.__dict__.update(entries)


class _DrawingNamespace(_Namespace):
    def __init__(self, *, all_getter: Any, **entries: Any) -> None:
        super().__init__(**entries)
        self._all_getter = all_getter

    @property
    def all(self) -> Any:
        """Return a fresh oldest-first snapshot of live object handles."""
        return self._all_getter()


class _CallableNamespace(_Namespace):
    def __init__(self, call: Any, **entries: Any) -> None:
        super().__init__(**entries)
        self._call = call

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._call(*args, **kwargs)
