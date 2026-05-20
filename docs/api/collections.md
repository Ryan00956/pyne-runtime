# Collections API

Pyne exposes Pine-like mutable collections as script globals. The currently
supported namespaces are `array.*`, `map.*`, and `matrix.*`.

Pyne arrays are Python objects created by `array.new_*()` or `array.from_*()`.
They can be used with Pine-style namespace functions:

```python
values = array.new_float(2, 1.0)
array.push(values, close[1])
last = array.get(values, -1)
```

They also expose Python-style methods for package users:

```python
values = array.from_values(1, 2, 3)
values.push(4)
average = values.avg()
```

## Constructors

- `array.new(size=0, initial_value=None)`
- `array.new_float(size=0, initial_value=None)`
- `array.new_int(size=0, initial_value=None)`
- `array.new_bool(size=0, initial_value=None)`
- `array.new_string(size=0, initial_value=None)`
- `array.new_color(size=0, initial_value=None)`
- `array.from_values(*values)`
- `array.from_list(values)`

Pine's `array.from(...)` name cannot be written as normal Python syntax because
`from` is a Python keyword, so Pyne exposes `array.from_values(...)` and
`array.from_list(...)` instead.

## Mutations And Accessors

- `array.size(arr)`
- `array.get(arr, index)`
- `array.set(arr, index, value)`
- `array.push(arr, value)`
- `array.pop(arr)`
- `array.unshift(arr, value)`
- `array.shift(arr)`
- `array.insert(arr, index, value)`
- `array.remove(arr, index)`
- `array.clear(arr)`
- `array.copy(arr)`
- `array.slice(arr, index_from, index_to=None)`
- `array.fill(arr, value, index_from=0, index_to=None)`
- `array.reverse(arr)`
- `array.sort(arr, reverse=False)`

Negative indexes are accepted as Python-friendly shorthand for positions from
the end, so `array.get(values, -1)` returns the latest item.

## Search And Reduction

- `array.includes(arr, value)`
- `array.indexof(arr, value)`
- `array.lastindexof(arr, value)`
- `array.join(arr, separator=",")`
- `array.sum(arr)`
- `array.avg(arr)`
- `array.min(arr)`
- `array.max(arr)`

Numeric reducers skip `na` values and non-numeric payloads. They return `None`
when no numeric values are available, which serializes as `na` in normal Pyne
plot output.

## Maps

Pyne maps are mutable key/value containers created by `map.new()`,
`map.from_values()`, or `map.from_dict()`.

```python
levels = map.new()
map.put(levels, "fast", 10)
map.put(levels, "slow", 20)
slow = map.get(levels, "slow")
```

Python-style object methods are also available:

```python
weights = map.from_values("fast", 2, "slow", 4)
copy = weights.copy()
copy.put("signal", 8)
keys = copy.keys()
```

Supported map helpers:

- `map.new()`
- `map.from_values(key1, value1, ...)`
- `map.from_dict(values)`
- `map.copy(m)`
- `map.size(m)`
- `map.put(m, key, value)`
- `map.get(m, key, default=None)`
- `map.contains(m, key)`
- `map.remove(m, key)`
- `map.clear(m)`
- `map.keys(m)`
- `map.values(m)`

`map.keys()` and `map.values()` return `PyneArray` instances, so they can be
used directly with `array.*` helpers such as `array.join(map.keys(m), ",")` or
`array.sum(map.values(m))`.

## Matrices

Pyne matrices are mutable two-dimensional containers created by `matrix.new_*()`
or `matrix.from_rows()`.

```python
m = matrix.new_float(2, 3, 0.0)
matrix.set(m, 0, 1, 2.0)
cell = matrix.get(m, 0, 1)
```

Python-style object methods are also available:

```python
m = matrix.from_rows([[1, 2], [3, 4]])
t = m.transpose()
total = m.sum()
```

Supported matrix helpers:

- `matrix.new(rows=0, columns=0, initial_value=None)`
- `matrix.new_float(rows=0, columns=0, initial_value=None)`
- `matrix.new_int(rows=0, columns=0, initial_value=None)`
- `matrix.from_rows(rows)`
- `matrix.copy(m)`
- `matrix.rows(m)`
- `matrix.columns(m)`
- `matrix.elements_count(m)`
- `matrix.get(m, row, column)`
- `matrix.set(m, row, column, value)`
- `matrix.fill(m, value)`
- `matrix.row(m, row)`
- `matrix.col(m, column)`
- `matrix.transpose(m)`
- `matrix.reshape(m, rows, columns)`
- `matrix.add(left, right)`
- `matrix.sub(left, right)`
- `matrix.mult(left, right)`
- `matrix.sum(m)`
- `matrix.avg(m)`
- `matrix.min(m)`
- `matrix.max(m)`

`matrix.row()` and `matrix.col()` return `PyneArray` instances. `matrix.add()`
and `matrix.sub()` support matching matrix dimensions. `matrix.mult()` supports
scalar multiplication and matrix multiplication.
