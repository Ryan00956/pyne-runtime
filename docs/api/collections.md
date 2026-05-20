# Collections API

Pyne exposes Pine-like mutable collections as script globals. The first
supported namespace is `array.*`.

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
