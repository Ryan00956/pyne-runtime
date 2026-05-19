# State Semantics

Pyne provides runtime-scoped state cells through `var()` and `pyne.var()`.

```python
counter = var("counter", 0)
counter.set(counter.get() + 1)
plot(counter.get(), "Counter")
```

State is isolated per script execution. Running the same script twice creates fresh cells.

## Reusing A Cell

Calling `var()` with the same name returns the same cell for the current execution:

```python
trend = var("trend", 0)
trend.set(1)

same = var("trend", 99)
plot(same.get(), "Trend")  # 1
```

## Carrying State Across Bars

Batch scripts are vectorized, so ordinary Python assignment does not run once per bar. Use `set_each()` when a series of updates should carry the prior state through missing values:

```python
trend = pyne.var("trend", 0)
updates = where(bar_index == 0, 1, where(bar_index == 2, -1, na))
plot(trend.set_each(updates), "Trend")
```

The output is:

```text
1, 1, -1, -1
```

`na` means "keep the previous state".

This is useful for regime-like indicators:

```python
fast = ta.ema(close, 12)
slow = ta.ema(close, 26)

trend = pyne.var("trend", 0)
updates = where(crossover(fast, slow), 1, where(crossunder(fast, slow), -1, na))
plot(trend.set_each(updates), "Trend")
```

## API

- `var(name, default=None)`: create or return a runtime-scoped cell.
- `state(name, default=None)`: alias for `var()`.
- `pyne.var(name, default=None)`: namespace form.
- `pyne.state(name, default=None)`: namespace alias.
- `cell.get()`: return current cell value.
- `cell.set(value)`: set and return the value.
- `cell.update(func)`: update from a callable.
- `cell.set_each(updates, default=None)`: apply per-bar updates, carrying prior state through `na`.
- `cell.reset(value=None)`: reset to default or explicit value.

Current scope:

- `var()` is runtime-scoped and deterministic in batch mode.
- `set_each()` provides Pine-like carry-forward behavior for series updates.
- Full recursive bar-by-bar assignment semantics will be refined in later runtime phases.
