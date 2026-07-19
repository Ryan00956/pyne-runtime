"""Runtime-scoped Pine-like state helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from .series import PyneSeries, wrap_like
from .values import is_na_value, to_missing_scalar


@dataclass
class PyneVar:
    """A runtime-scoped variable cell.

    The cell is initialized once per script execution/session. In batch mode it
    can hold scalars or series. ``set_each()`` provides a Pine-like way to carry
    state forward across bars: missing update values mean "keep the prior state".
    """

    name: str
    default: Any = None
    _value: Any = field(default=None, init=False)
    _initialized: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not self._initialized:
            self._value = self.default
            self._initialized = True

    @property
    def value(self) -> Any:
        return self._value

    @value.setter
    def value(self, value: Any) -> None:
        self.set(value)

    def get(self) -> Any:
        return self._value

    def set(self, value: Any) -> Any:
        self._value = to_missing_scalar(value)
        return self._value

    def update(self, func: Callable[[Any], Any]) -> Any:
        if not callable(func):
            raise TypeError("PyneVar.update() requires a callable")
        return self.set(func(self._value))

    def set_each(self, updates: Any, default: Any = None) -> Any:
        """Apply per-bar updates, carrying the previous value through ``na``.

        Args:
            updates: Scalar, array, or ``PyneSeries``. Missing values mean
                "retain the previous state".
            default: Optional initial state. If omitted, the cell's current
                value is used.
        """
        initial = self._value if default is None else default
        initial = to_missing_scalar(initial)

        if isinstance(updates, PyneSeries):
            source = updates.to_numpy()
        elif isinstance(updates, np.ndarray):
            source = updates
        elif isinstance(updates, (list, tuple)):
            source = np.asarray(updates)
        else:
            self._value = to_missing_scalar(updates) if not is_na_value(updates) else initial
            return self._value

        numeric_result = _numeric_carry_forward(source, initial)
        if numeric_result is not None:
            wrapped = wrap_like(numeric_result, updates, name=self.name)
            self._value = wrapped
            return wrapped

        result = np.empty(len(source), dtype=object)
        current = initial
        for idx, item in enumerate(source):
            if not is_na_value(item):
                current = item
            result[idx] = current

        normalized = _normalize_series_values(result)
        wrapped = wrap_like(normalized, updates, name=self.name)
        self._value = wrapped
        return wrapped

    def reset(self, value: Any | None = None) -> Any:
        return self.set(self.default if value is None else value)

    def __array__(self, dtype: Any = None, copy: bool | None = None) -> np.ndarray:
        if isinstance(self._value, PyneSeries):
            values = self._value.to_numpy(dtype=dtype)
        else:
            values = np.asarray(self._value, dtype=dtype)
        if copy is None:
            return values
        return np.array(values, dtype=dtype, copy=copy)

    def __repr__(self) -> str:
        return f"PyneVar(name={self.name!r}, value={self._value!r})"


class PyneStateNamespace:
    """Runtime-scoped state namespace injected into Pyne scripts."""

    def __init__(self) -> None:
        self._vars: dict[str, PyneVar] = {}

    def var(self, name: str, default: Any = None) -> PyneVar:
        key = str(name)
        if key not in self._vars:
            self._vars[key] = PyneVar(name=key, default=default)
        return self._vars[key]

    def state(self, name: str, default: Any = None) -> PyneVar:
        return self.var(name, default)

    def snapshot(self) -> dict[str, Any]:
        return {name: cell.get() for name, cell in self._vars.items()}


def _normalize_series_values(values: np.ndarray) -> np.ndarray:
    try:
        return values.astype(np.float64)
    except (TypeError, ValueError):
        return values


def _numeric_carry_forward(source: np.ndarray, initial: Any) -> np.ndarray | None:
    """Vectorized ``set_each`` path for real numeric arrays; object values fall back."""
    values = np.asarray(source)
    if values.dtype.kind not in "biuf":
        return None

    try:
        initial_value = np.nan if is_na_value(initial) else float(initial)
    except (TypeError, ValueError):
        return None

    numeric = values.astype(np.float64, copy=False)
    if len(numeric) == 0:
        return np.empty(0, dtype=np.float64)

    missing = np.isnan(numeric)
    if not np.any(missing):
        return np.array(numeric, dtype=np.float64, copy=True)

    indices = np.where(~missing, np.arange(len(numeric), dtype=np.intp), -1)
    np.maximum.accumulate(indices, out=indices)
    result = np.empty(len(numeric), dtype=np.float64)
    leading = indices < 0
    result[leading] = initial_value
    result[~leading] = numeric[indices[~leading]]
    return result
