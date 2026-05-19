indicator("Pine-Like Semantics", overlay=True)

fast = ta.ema(close, 3)
prev_close = close[1]
bull = close > open
body = when(bull, close - open, open - close)

regime = pyne.var("regime", 0)
regime_updates = when(
    crossover(close, fast),
    1,
    when(crossunder(close, fast), -1, na),
)
regime_series = regime.set_each(regime_updates)

plot(close, "Close", color=color.orange)
plot(prev_close, "Previous Close", color=color.blue)
plot(body, "Body", style=plot.style_histogram, color=color.gray)
plot(regime_series, "Regime", pane="separate", color=color.purple)

marker(barstate.isfirst, text="First", color=color.green, location=location.belowbar)
marker(barstate.islast, text="Last", color=color.red, location=location.abovebar)

trend_line = line.new(bar_index[5], close[5], bar_index, close, color=color.orange)
line.set_width(trend_line, 2)
label.new(bar_index, high, text="Latest", color=color.green)

strategy.entry_when(crossover(close, fast), "Long", strategy.long, qty=1)
strategy.close_when(crossunder(close, fast), "Long")
