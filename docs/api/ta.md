# `ta` API

The `ta` namespace is injected into scripts.

Common helpers:

```python
ta.sma(close, 20)
ta.ema(close, 20)
ta.wma(close, 20)
ta.hma(close, 20)
ta.swma(close)
ta.alma(close, 20, 0.85, 6)
ta.rsi(close, 14)
ta.cmo(close, 14)
ta.wpr(14)
ta.tsi(close, 25, 13)
ta.macd(close, 12, 26, 9)
ta.mom(close, 10)
ta.linreg(close, 20, 0)
ta.correlation(close, open, 20)
ta.dmi(14, 14)
ta.sar(0.02, 0.02, 0.2)
ta.bb(close, 20, 2)
ta.dev(close, 20)
ta.variance(close, 20)
ta.percentile_nearest_rank(close, 20, 50)
ta.percentile_linear_interpolation(close, 20, 50)
ta.atr(14)
ta.highest(close, 20)
ta.lowest(close, 20)
ta.cross(a, b)
ta.crossover(a, b)
ta.crossunder(a, b)
```

Several helpers are also exposed as top-level script functions, such as `cross()`, `crossover()`, `crossunder()`, `highest()`, and `lowest()`.

TA helpers are series-aware, so history references compose naturally:

```python
plot(ta.mom(close[1], 10), "Shifted Momentum")
marker(ta.cross(close, ta.sma(close, 20)), text="Cross")
```

