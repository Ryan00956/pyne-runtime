from __future__ import annotations

import pyne_runtime as pn


def _bars() -> list[dict[str, float]]:
    return [
        {"time": 1, "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 100},
        {"time": 2, "open": 2, "high": 3, "low": 1.5, "close": 2.5, "volume": 120},
        {"time": 3, "open": 3, "high": 4, "low": 2.5, "close": 3.5, "volume": 140},
    ]


def test_array_namespace_core_mutations_and_accessors() -> None:
    result = pn.run(
        """
prices = array.new_float(2, 1.5)
array.push(prices, 3.5)
array.set(prices, 1, 2.5)
array.unshift(prices, 0.5)
removed = array.remove(prices, 0)
popped = array.pop(prices)
array.insert(prices, 2, 4.5)

plot(array.size(prices), "Size")
plot(array.get(prices, 0), "First")
plot(array.get(prices, -1), "Last")
plot(removed, "Removed")
plot(popped, "Popped")
plot(array.indexof(prices, 4.5), "Index")
plot(array.includes(prices, 2.5), "Includes")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Size") == [3.0, 3.0, 3.0]
    assert result.values("First") == [1.5, 1.5, 1.5]
    assert result.values("Last") == [4.5, 4.5, 4.5]
    assert result.values("Removed") == [0.5, 0.5, 0.5]
    assert result.values("Popped") == [3.5, 3.5, 3.5]
    assert result.values("Index") == [2.0, 2.0, 2.0]
    assert result.values("Includes") == [1.0, 1.0, 1.0]


def test_array_object_methods_copy_slice_fill_and_numeric_reducers() -> None:
    result = pn.run(
        """
values = array.from_values(1, 2, 3, 4)
copy = values.copy()
copy.fill(9, 1, 3)
window = copy.slice(1, 3)
array.reverse(window)

plot(values.sum(), "Sum")
plot(values.avg(), "Avg")
plot(values.min(), "Min")
plot(values.max(), "Max")
plot(copy.get(1), "Copy Changed")
plot(values.get(1), "Original Kept")
plot(window.get(0), "Window First")
plot(array.lastindexof(copy, 9), "Last Index")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Sum") == [10.0, 10.0, 10.0]
    assert result.values("Avg") == [2.5, 2.5, 2.5]
    assert result.values("Min") == [1.0, 1.0, 1.0]
    assert result.values("Max") == [4.0, 4.0, 4.0]
    assert result.values("Copy Changed") == [9.0, 9.0, 9.0]
    assert result.values("Original Kept") == [2.0, 2.0, 2.0]
    assert result.values("Window First") == [9.0, 9.0, 9.0]
    assert result.values("Last Index") == [2.0, 2.0, 2.0]


def test_array_join_and_clear_support_non_numeric_payloads() -> None:
    result = pn.run(
        """
names = array.new_string()
array.push(names, "fast")
array.push(names, "slow")
joined = array.join(names, "/")
array.clear(names)

label(joined)
plot(array.size(names), "Cleared Size")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.output["labels"][0]["text"] == "fast/slow"
    assert result.values("Cleared Size") == [0.0, 0.0, 0.0]


def test_array_out_of_bounds_errors_are_actionable() -> None:
    result = pn.run(
        """
values = array.new_float(1, 1.0)
array.get(values, 3)
""",
        _bars(),
        executor_mode="inline",
    )

    assert not result.ok
    assert result.code == "PYNE_RUNTIME_ERROR"
    assert "array index 3 is out of bounds" in str(result.error)


def test_map_namespace_core_key_value_semantics() -> None:
    result = pn.run(
        """
levels = map.new()
map.put(levels, "fast", 10)
map.put(levels, "slow", 20)
removed = map.remove(levels, "fast")
map.put(levels, "signal", 9)

plot(map.size(levels), "Map Size")
plot(map.get(levels, "slow"), "Slow")
plot(map.get(levels, "missing", 42), "Default")
plot(map.contains(levels, "signal"), "Contains")
plot(removed, "Removed")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.values("Map Size") == [2.0, 2.0, 2.0]
    assert result.values("Slow") == [20.0, 20.0, 20.0]
    assert result.values("Default") == [42.0, 42.0, 42.0]
    assert result.values("Contains") == [1.0, 1.0, 1.0]
    assert result.values("Removed") == [10.0, 10.0, 10.0]


def test_map_methods_copy_keys_and_values_interoperate_with_arrays() -> None:
    result = pn.run(
        """
weights = map.from_values("fast", 2, "slow", 4)
copy = weights.copy()
copy.put("signal", 8)
map.clear(weights)

keys = copy.keys()
vals = map.values(copy)

label(array.join(keys, "|"))
plot(weights.size(), "Original Size")
plot(copy.size(), "Copy Size")
plot(vals.sum(), "Value Sum")
plot(copy.get("signal"), "Signal")
""",
        _bars(),
        executor_mode="inline",
    )

    assert result.ok, result.error
    assert result.output["labels"][0]["text"] == "fast|slow|signal"
    assert result.values("Original Size") == [0.0, 0.0, 0.0]
    assert result.values("Copy Size") == [3.0, 3.0, 3.0]
    assert result.values("Value Sum") == [14.0, 14.0, 14.0]
    assert result.values("Signal") == [8.0, 8.0, 8.0]


def test_map_from_values_requires_key_value_pairs() -> None:
    result = pn.run(
        """
map.from_values("fast", 1, "slow")
""",
        _bars(),
        executor_mode="inline",
    )

    assert not result.ok
    assert result.code == "PYNE_RUNTIME_ERROR"
    assert "map.from_values() expects key/value pairs" in str(result.error)
