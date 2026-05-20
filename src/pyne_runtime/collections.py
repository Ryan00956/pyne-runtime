"""Pine-like mutable collection helpers."""
from __future__ import annotations

from typing import Any, Iterable

from .values import is_na_value


class PyneArray:
    """Mutable Pine-like array value."""

    def __init__(self, values: Iterable[Any] | None = None) -> None:
        self._values = list(values or [])

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self):
        return iter(self._values)

    def __repr__(self) -> str:
        return f"PyneArray({self._values!r})"

    def to_list(self) -> list[Any]:
        return list(self._values)

    def copy(self) -> PyneArray:
        return PyneArray(self._values)

    def size(self) -> int:
        return len(self._values)

    def get(self, index: int) -> Any:
        return self._values[_resolve_index(index, len(self._values))]

    def set(self, index: int, value: Any) -> None:
        self._values[_resolve_index(index, len(self._values))] = value

    def push(self, value: Any) -> None:
        self._values.append(value)

    def pop(self) -> Any:
        if not self._values:
            raise IndexError("array.pop() cannot pop from an empty array")
        return self._values.pop()

    def unshift(self, value: Any) -> None:
        self._values.insert(0, value)

    def shift(self) -> Any:
        if not self._values:
            raise IndexError("array.shift() cannot shift from an empty array")
        return self._values.pop(0)

    def insert(self, index: int, value: Any) -> None:
        idx = int(index)
        if idx < 0 or idx > len(self._values):
            raise IndexError(f"array index {idx} is out of bounds")
        self._values.insert(idx, value)

    def remove(self, index: int) -> Any:
        return self._values.pop(_resolve_index(index, len(self._values)))

    def clear(self) -> None:
        self._values.clear()

    def includes(self, value: Any) -> bool:
        return value in self._values

    def indexof(self, value: Any) -> int:
        try:
            return self._values.index(value)
        except ValueError:
            return -1

    def lastindexof(self, value: Any) -> int:
        for idx in range(len(self._values) - 1, -1, -1):
            if self._values[idx] == value:
                return idx
        return -1

    def slice(self, index_from: int, index_to: int | None = None) -> PyneArray:
        start = int(index_from)
        stop = None if index_to is None else int(index_to)
        return PyneArray(self._values[start:stop])

    def fill(self, value: Any, index_from: int = 0, index_to: int | None = None) -> None:
        start = max(int(index_from), 0)
        stop = len(self._values) if index_to is None else min(int(index_to), len(self._values))
        for idx in range(start, stop):
            self._values[idx] = value

    def reverse(self) -> None:
        self._values.reverse()

    def sort(self, *, reverse: bool = False) -> None:
        self._values.sort(reverse=bool(reverse))

    def join(self, separator: str = ",") -> str:
        return str(separator).join("" if is_na_value(item) else str(item) for item in self._values)

    def sum(self) -> float | None:
        numbers = _numeric_values(self._values)
        return float(sum(numbers)) if numbers else None

    def avg(self) -> float | None:
        numbers = _numeric_values(self._values)
        return float(sum(numbers) / len(numbers)) if numbers else None

    def min(self) -> float | None:
        numbers = _numeric_values(self._values)
        return float(min(numbers)) if numbers else None

    def max(self) -> float | None:
        numbers = _numeric_values(self._values)
        return float(max(numbers)) if numbers else None


class PyneMap:
    """Mutable Pine-like key/value map."""

    def __init__(self, values: dict[Any, Any] | None = None) -> None:
        self._values = dict(values or {})

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self):
        return iter(self._values)

    def __repr__(self) -> str:
        return f"PyneMap({self._values!r})"

    def to_dict(self) -> dict[Any, Any]:
        return dict(self._values)

    def copy(self) -> PyneMap:
        return PyneMap(self._values)

    def size(self) -> int:
        return len(self._values)

    def put(self, key: Any, value: Any) -> None:
        self._values[key] = value

    def get(self, key: Any, default: Any = None) -> Any:
        return self._values.get(key, default)

    def contains(self, key: Any) -> bool:
        return key in self._values

    def remove(self, key: Any) -> Any:
        return self._values.pop(key, None)

    def clear(self) -> None:
        self._values.clear()

    def keys(self) -> PyneArray:
        return PyneArray(self._values.keys())

    def values(self) -> PyneArray:
        return PyneArray(self._values.values())


class ArrayNamespace:
    """Pine-like ``array.*`` namespace."""

    def new(self, size: int = 0, initial_value: Any = None) -> PyneArray:
        return PyneArray([initial_value for _ in range(max(int(size), 0))])

    def new_float(self, size: int = 0, initial_value: float | None = None) -> PyneArray:
        return self.new(size, initial_value)

    def new_int(self, size: int = 0, initial_value: int | None = None) -> PyneArray:
        return self.new(size, initial_value)

    def new_bool(self, size: int = 0, initial_value: bool | None = None) -> PyneArray:
        return self.new(size, initial_value)

    def new_string(self, size: int = 0, initial_value: str | None = None) -> PyneArray:
        return self.new(size, initial_value)

    def new_color(self, size: int = 0, initial_value: str | None = None) -> PyneArray:
        return self.new(size, initial_value)

    def from_values(self, *values: Any) -> PyneArray:
        return PyneArray(values)

    def from_list(self, values: Iterable[Any]) -> PyneArray:
        return PyneArray(values)

    def copy(self, arr: PyneArray) -> PyneArray:
        return _array(arr).copy()

    def size(self, arr: PyneArray) -> int:
        return _array(arr).size()

    def get(self, arr: PyneArray, index: int) -> Any:
        return _array(arr).get(index)

    def set(self, arr: PyneArray, index: int, value: Any) -> None:
        _array(arr).set(index, value)

    def push(self, arr: PyneArray, value: Any) -> None:
        _array(arr).push(value)

    def pop(self, arr: PyneArray) -> Any:
        return _array(arr).pop()

    def unshift(self, arr: PyneArray, value: Any) -> None:
        _array(arr).unshift(value)

    def shift(self, arr: PyneArray) -> Any:
        return _array(arr).shift()

    def insert(self, arr: PyneArray, index: int, value: Any) -> None:
        _array(arr).insert(index, value)

    def remove(self, arr: PyneArray, index: int) -> Any:
        return _array(arr).remove(index)

    def clear(self, arr: PyneArray) -> None:
        _array(arr).clear()

    def includes(self, arr: PyneArray, value: Any) -> bool:
        return _array(arr).includes(value)

    def indexof(self, arr: PyneArray, value: Any) -> int:
        return _array(arr).indexof(value)

    def lastindexof(self, arr: PyneArray, value: Any) -> int:
        return _array(arr).lastindexof(value)

    def slice(self, arr: PyneArray, index_from: int, index_to: int | None = None) -> PyneArray:
        return _array(arr).slice(index_from, index_to)

    def fill(
        self,
        arr: PyneArray,
        value: Any,
        index_from: int = 0,
        index_to: int | None = None,
    ) -> None:
        _array(arr).fill(value, index_from, index_to)

    def reverse(self, arr: PyneArray) -> None:
        _array(arr).reverse()

    def sort(self, arr: PyneArray, *, reverse: bool = False) -> None:
        _array(arr).sort(reverse=reverse)

    def join(self, arr: PyneArray, separator: str = ",") -> str:
        return _array(arr).join(separator)

    def sum(self, arr: PyneArray) -> float | None:
        return _array(arr).sum()

    def avg(self, arr: PyneArray) -> float | None:
        return _array(arr).avg()

    def min(self, arr: PyneArray) -> float | None:
        return _array(arr).min()

    def max(self, arr: PyneArray) -> float | None:
        return _array(arr).max()


class MapNamespace:
    """Pine-like ``map.*`` namespace."""

    def new(self) -> PyneMap:
        return PyneMap()

    def from_values(self, *items: Any) -> PyneMap:
        if len(items) % 2 != 0:
            raise ValueError("map.from_values() expects key/value pairs")
        result = PyneMap()
        for idx in range(0, len(items), 2):
            result.put(items[idx], items[idx + 1])
        return result

    def from_dict(self, values: dict[Any, Any]) -> PyneMap:
        return PyneMap(values)

    def copy(self, m: PyneMap) -> PyneMap:
        return _map(m).copy()

    def size(self, m: PyneMap) -> int:
        return _map(m).size()

    def put(self, m: PyneMap, key: Any, value: Any) -> None:
        _map(m).put(key, value)

    def get(self, m: PyneMap, key: Any, default: Any = None) -> Any:
        return _map(m).get(key, default)

    def contains(self, m: PyneMap, key: Any) -> bool:
        return _map(m).contains(key)

    def remove(self, m: PyneMap, key: Any) -> Any:
        return _map(m).remove(key)

    def clear(self, m: PyneMap) -> None:
        _map(m).clear()

    def keys(self, m: PyneMap) -> PyneArray:
        return _map(m).keys()

    def values(self, m: PyneMap) -> PyneArray:
        return _map(m).values()


array_namespace = ArrayNamespace()
map_namespace = MapNamespace()


def _array(value: PyneArray) -> PyneArray:
    if not isinstance(value, PyneArray):
        raise TypeError("array.* expects a PyneArray created by array.new_*()")
    return value


def _map(value: PyneMap) -> PyneMap:
    if not isinstance(value, PyneMap):
        raise TypeError("map.* expects a PyneMap created by map.new()")
    return value


def _resolve_index(index: int, length: int) -> int:
    idx = int(index)
    if idx < 0:
        idx = length + idx
    if idx < 0 or idx >= length:
        raise IndexError(f"array index {int(index)} is out of bounds")
    return idx


def _numeric_values(values: Iterable[Any]) -> list[float]:
    numbers: list[float] = []
    for item in values:
        if is_na_value(item):
            continue
        try:
            numbers.append(float(item))
        except (TypeError, ValueError):
            continue
    return numbers
