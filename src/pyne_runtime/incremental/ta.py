"""Step-by-step technical analysis helpers for incremental sessions."""
from __future__ import annotations

import math
from collections import deque
from typing import Any

from .limits import IncrementalLimits, _LimitTracker


class _StepSMA:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.window: deque[float | None] = deque()
        self.sum = 0.0
        self.valid_count = 0

    def update(self, value: Any) -> float | None:
        number = _number_or_none(value)
        self.window.append(number)
        if number is not None:
            self.sum += number
            self.valid_count += 1
        if len(self.window) > self.period:
            removed = self.window.popleft()
            if removed is not None:
                self.sum -= removed
                self.valid_count -= 1
        if len(self.window) < self.period or self.valid_count < self.period:
            return None
        return self.sum / self.period


class _StepEMA:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.alpha = 2.0 / (self.period + 1)
        self.count = 0
        self.seed_sum = 0.0
        self.seed_count = 0
        self.ema: float | None = None

    def update(self, value: Any) -> float | None:
        number = _number_or_none(value)
        if self.ema is not None:
            if number is None:
                return self.ema
            self.ema = self.alpha * number + (1 - self.alpha) * self.ema
            return self.ema

        self.count += 1
        if number is not None:
            self.seed_sum += number
            self.seed_count += 1
        if self.count < self.period:
            return None
        if self.seed_count == 0:
            return self.ema
        self.ema = self.seed_sum / self.seed_count
        return self.ema


class _StepRMA:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.alpha = 1.0 / self.period
        self.seed_sum = 0.0
        self.seed_count = 0
        self.value: float | None = None

    def update(self, value: Any) -> float | None:
        number = _number_or_none(value)
        if number is None:
            return self.value
        if self.value is None:
            self.seed_sum += number
            self.seed_count += 1
            if self.seed_count < self.period:
                return None
            self.value = self.seed_sum / self.period
            return self.value
        self.value = self.alpha * number + (1.0 - self.alpha) * self.value
        return self.value


class _StepWMA:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.window: deque[float | None] = deque()
        self.simple_sum = 0.0
        self.weighted_sum = 0.0
        self.valid_count = 0
        self.denominator = self.period * (self.period + 1) / 2.0

    def update(self, value: Any) -> float | None:
        number = _number_or_none(value)
        numeric = number or 0.0
        next_weight = len(self.window) + 1
        self.window.append(number)
        self.simple_sum += numeric
        self.weighted_sum += next_weight * numeric
        if number is not None:
            self.valid_count += 1
        if len(self.window) > self.period:
            removed = self.window.popleft()
            self.weighted_sum -= self.simple_sum
            self.simple_sum -= removed or 0.0
            if removed is not None:
                self.valid_count -= 1
        if len(self.window) < self.period or self.valid_count < self.period:
            return None
        return self.weighted_sum / self.denominator


class _StepVWMA:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.window: deque[tuple[float | None, float | None]] = deque()
        self.numerator = 0.0
        self.denominator = 0.0

    def update(self, value: Any, volume: Any) -> float | None:
        number = _number_or_none(value)
        weight = _number_or_none(volume)
        self.window.append((number, weight))
        if number is not None and weight is not None:
            self.numerator += number * weight
        if weight is not None:
            self.denominator += weight
        if len(self.window) > self.period:
            removed_value, removed_weight = self.window.popleft()
            if removed_value is not None and removed_weight is not None:
                self.numerator -= removed_value * removed_weight
            if removed_weight is not None:
                self.denominator -= removed_weight
        if len(self.window) < self.period or self.denominator <= 0.0:
            return None
        return self.numerator / self.denominator


class _StepVariance:
    def __init__(self, period: int, *, biased: bool = True) -> None:
        self.period = max(int(period), 1)
        self.biased = bool(biased)
        self.window: deque[float | None] = deque()
        self.sum = 0.0
        self.sumsq = 0.0
        self.valid_count = 0

    def update(self, value: Any) -> float | None:
        number = _number_or_none(value)
        self.window.append(number)
        if number is not None:
            self.sum += number
            self.sumsq += number * number
            self.valid_count += 1
        if len(self.window) > self.period:
            removed = self.window.popleft()
            if removed is not None:
                self.sum -= removed
                self.sumsq -= removed * removed
                self.valid_count -= 1
        if len(self.window) < self.period or self.valid_count < self.period:
            return None
        denominator = self.period if self.biased else self.period - 1
        if denominator <= 0:
            return None
        centered = max(self.sumsq - self.sum * self.sum / self.period, 0.0)
        return centered / denominator


class _StepStdev(_StepVariance):
    def update(self, value: Any) -> float | None:
        variance = super().update(value)
        return None if variance is None else math.sqrt(variance)


class _StepBOLL:
    def __init__(self, period: int, multiplier: float = 2.0) -> None:
        self.period = max(int(period), 1)
        self.multiplier = float(multiplier)
        self.window: deque[float | None] = deque()
        self.sum = 0.0
        self.sumsq = 0.0
        self.valid_count = 0

    def update(self, value: Any) -> tuple[float | None, float | None, float | None]:
        number = _number_or_none(value)
        self.window.append(number)
        if number is not None:
            self.sum += number
            self.sumsq += number * number
            self.valid_count += 1
        if len(self.window) > self.period:
            removed = self.window.popleft()
            if removed is not None:
                self.sum -= removed
                self.sumsq -= removed * removed
                self.valid_count -= 1
        if len(self.window) < self.period or self.valid_count < self.period:
            return None, None, None
        mid = self.sum / self.period
        variance = max(self.sumsq / self.period - mid * mid, 0.0)
        std = math.sqrt(variance)
        return mid + self.multiplier * std, mid, mid - self.multiplier * std


class _StepMACD:
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        self.fast = _StepEMA(max(int(fast), 1))
        self.slow = _StepEMA(max(int(slow), 1))
        self.signal = _StepEMA(max(int(signal), 1))

    def update(self, value: Any) -> tuple[float | None, float | None, float | None]:
        fast_value = self.fast.update(value)
        slow_value = self.slow.update(value)
        if fast_value is None or slow_value is None:
            return None, None, None
        dif = fast_value - slow_value
        dea = self.signal.update(dif)
        hist = dif - dea if dea is not None else None
        return dif, dea, hist


class _StepRSI:
    def __init__(self, period: int = 14) -> None:
        self.period = max(int(period), 1)
        self.prev: float | None = None
        self.count = 0
        self.gain_sum = 0.0
        self.loss_sum = 0.0
        self.avg_gain: float | None = None
        self.avg_loss: float | None = None

    def update(self, value: Any) -> float | None:
        current = _number_or_none(value)
        if current is None:
            self.prev = None
            return self._current_value()
        if self.prev is None:
            self.prev = current
            return self._current_value()
        delta = current - self.prev
        self.prev = current
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        if self.avg_gain is None or self.avg_loss is None:
            self.count += 1
            self.gain_sum += gain
            self.loss_sum += loss
            if self.count < self.period:
                return None
            self.avg_gain = self.gain_sum / self.period
            self.avg_loss = self.loss_sum / self.period
        else:
            self.avg_gain = (self.avg_gain * (self.period - 1) + gain) / self.period
            self.avg_loss = (self.avg_loss * (self.period - 1) + loss) / self.period
        return _rsi_from_avgs(self.avg_gain, self.avg_loss)

    def _current_value(self) -> float | None:
        if self.avg_gain is None or self.avg_loss is None:
            return None
        return _rsi_from_avgs(self.avg_gain, self.avg_loss)


class _StepATR:
    def __init__(self, period: int = 14) -> None:
        self.period = max(int(period), 1)
        self.prev_close: float | None = None
        self.count = 0
        self.tr_sum = 0.0
        self.atr: float | None = None

    def update(self, bar_or_high: Any, low: Any = None, close: Any = None) -> float | None:
        if low is None and close is None:
            high = _number_or_none(getattr(bar_or_high, "high"))
            low = _number_or_none(getattr(bar_or_high, "low"))
            close = _number_or_none(getattr(bar_or_high, "close"))
        else:
            high = _number_or_none(bar_or_high)
            low = _number_or_none(low)
            close = _number_or_none(close)

        if high is None or low is None:
            self.prev_close = close
            return self.atr

        if self.prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - self.prev_close), abs(low - self.prev_close))
        self.prev_close = close

        if self.atr is None:
            self.count += 1
            self.tr_sum += tr
            if self.count < self.period:
                return None
            self.atr = self.tr_sum / self.period
        else:
            self.atr = (self.atr * (self.period - 1) + tr) / self.period
        return self.atr


class _StepMonotonic:
    def __init__(self, period: int, *, highest: bool) -> None:
        self.period = max(int(period), 1)
        self.highest = highest
        self.index = -1
        self.window: deque[tuple[int, float]] = deque()

    def update(self, value: Any) -> float | None:
        self.index += 1
        expiry = self.index - self.period
        while self.window and self.window[0][0] <= expiry:
            self.window.popleft()
        number = _number_or_none(value)
        if number is not None:
            if self.highest:
                while self.window and self.window[-1][1] <= number:
                    self.window.pop()
            else:
                while self.window and self.window[-1][1] >= number:
                    self.window.pop()
            self.window.append((self.index, number))
        if self.index + 1 < self.period:
            return None
        return self.window[0][1] if self.window else None


class _StepStoch:
    def __init__(self, period: int) -> None:
        self.highest = _StepMonotonic(period, highest=True)
        self.lowest = _StepMonotonic(period, highest=False)

    def update(self, source: Any, high: Any, low: Any) -> float | None:
        current = _number_or_none(source)
        highest = self.highest.update(high)
        lowest = self.lowest.update(low)
        if highest is None and self.highest.window:
            highest = self.highest.window[0][1]
        if lowest is None and self.lowest.window:
            lowest = self.lowest.window[0][1]
        if current is None or highest is None or lowest is None:
            return None
        spread = highest - lowest
        return 50.0 if spread == 0.0 else 100.0 * (current - lowest) / spread


class _StepCCI:
    def __init__(self, period: int) -> None:
        self.period = max(int(period), 1)
        self.window: deque[float | None] = deque()

    def update(self, source: Any) -> float | None:
        current = _number_or_none(source)
        self.window.append(current)
        if len(self.window) > self.period:
            self.window.popleft()
        if len(self.window) < self.period or any(value is None for value in self.window):
            return None
        values = [float(value) for value in self.window if value is not None]
        average = sum(values) / self.period
        deviation = sum(abs(value - average) for value in values) / self.period
        if deviation == 0.0:
            return 0.0
        return (float(current) - average) / (0.015 * deviation)


class _StepSupertrend:
    def __init__(self, factor: float, atr_period: int) -> None:
        self.factor = float(factor)
        self.atr = _StepATR(atr_period)
        self.previous_atr: float | None = None
        self.previous_close: float | None = None
        self.previous_upper = 0.0
        self.previous_lower = 0.0
        self.previous_supertrend: float | None = 0.0
        self.index = -1

    def update(
        self,
        bar_or_high: Any,
        low: Any = None,
        close: Any = None,
    ) -> tuple[float | None, float | None]:
        if low is None and close is None:
            high = _number_or_none(getattr(bar_or_high, "high"))
            low_value = _number_or_none(getattr(bar_or_high, "low"))
            close_value = _number_or_none(getattr(bar_or_high, "close"))
        else:
            high = _number_or_none(bar_or_high)
            low_value = _number_or_none(low)
            close_value = _number_or_none(close)
        self.index += 1
        atr = self.atr.update(high, low_value, close_value)
        if high is None or low_value is None or close_value is None or atr is None:
            self.previous_atr = atr
            self.previous_close = close_value
            self.previous_upper = 0.0
            self.previous_lower = 0.0
            return (0.0 if self.index == 0 else None), 1.0

        midpoint = (high + low_value) / 2.0
        upper = midpoint + self.factor * atr
        lower = midpoint - self.factor * atr
        previous_close = self.previous_close
        if not (
            lower > self.previous_lower
            or (previous_close is not None and previous_close < self.previous_lower)
        ):
            lower = self.previous_lower
        if not (
            upper < self.previous_upper
            or (previous_close is not None and previous_close > self.previous_upper)
        ):
            upper = self.previous_upper

        if self.index == 0 or self.previous_atr is None:
            direction = 1.0
        elif self.previous_supertrend == self.previous_upper:
            direction = -1.0 if close_value > upper else 1.0
        else:
            direction = 1.0 if close_value < lower else -1.0
        supertrend = lower if direction == -1.0 else upper

        self.previous_atr = atr
        self.previous_close = close_value
        self.previous_upper = upper
        self.previous_lower = lower
        self.previous_supertrend = supertrend
        return supertrend, direction


class IncrementalTaNamespace:
    """Stateful TA helper namespace available as ``ctx.ta``."""

    def __init__(self, limits: _LimitTracker | None = None) -> None:
        self._helpers: dict[str, Any] = {}
        self._limits = limits or _LimitTracker(IncrementalLimits(enabled=False))

    def sma(self, name: str, period: int | None = None) -> _StepSMA:
        key = f"sma:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.sma('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepSMA(period)
        return self._helpers[key]

    def ema(self, name: str, period: int | None = None) -> _StepEMA:
        key = f"ema:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.ema('{name}') has not been initialized")
            self._helpers[key] = _StepEMA(period)
        return self._helpers[key]

    def rma(self, name: str, period: int | None = None) -> _StepRMA:
        key = f"rma:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.rma('{name}') has not been initialized")
            self._helpers[key] = _StepRMA(period)
        return self._helpers[key]

    def wma(self, name: str, period: int | None = None) -> _StepWMA:
        key = f"wma:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.wma('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepWMA(period)
        return self._helpers[key]

    def vwma(self, name: str, period: int | None = None) -> _StepVWMA:
        key = f"vwma:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.vwma('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepVWMA(period)
        return self._helpers[key]

    def variance(
        self,
        name: str,
        period: int | None = None,
        *,
        biased: bool = True,
    ) -> _StepVariance:
        key = f"variance:{name}:{int(bool(biased))}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.variance('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepVariance(period, biased=biased)
        return self._helpers[key]

    def stdev(self, name: str, period: int | None = None) -> _StepStdev:
        key = f"stdev:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.stdev('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepStdev(period)
        return self._helpers[key]

    def boll(self, name: str, period: int | None = None, multiplier: float = 2.0) -> _StepBOLL:
        key = f"boll:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.boll('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepBOLL(period, multiplier)
        return self._helpers[key]

    def macd(
        self,
        name: str,
        fast: int | None = None,
        slow: int = 26,
        signal: int = 9,
    ) -> _StepMACD:
        key = f"macd:{name}"
        if key not in self._helpers:
            if fast is None:
                raise ValueError(f"ctx.ta.macd('{name}') has not been initialized")
            self._helpers[key] = _StepMACD(fast, slow, signal)
        return self._helpers[key]

    def rsi(self, name: str, period: int | None = None) -> _StepRSI:
        key = f"rsi:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.rsi('{name}') has not been initialized")
            self._helpers[key] = _StepRSI(period)
        return self._helpers[key]

    def atr(self, name: str, period: int | None = None) -> _StepATR:
        key = f"atr:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.atr('{name}') has not been initialized")
            self._helpers[key] = _StepATR(period)
        return self._helpers[key]

    def highest(self, name: str, period: int | None = None) -> _StepMonotonic:
        key = f"highest:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.highest('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepMonotonic(period, highest=True)
        return self._helpers[key]

    def lowest(self, name: str, period: int | None = None) -> _StepMonotonic:
        key = f"lowest:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.lowest('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepMonotonic(period, highest=False)
        return self._helpers[key]

    def stoch(self, name: str, period: int | None = None) -> _StepStoch:
        key = f"stoch:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.stoch('{name}') has not been initialized")
            self._limits.reserve_window(period * 2, label=key)
            self._helpers[key] = _StepStoch(period)
        return self._helpers[key]

    def cci(self, name: str, period: int | None = None) -> _StepCCI:
        key = f"cci:{name}"
        if key not in self._helpers:
            if period is None:
                raise ValueError(f"ctx.ta.cci('{name}') has not been initialized")
            self._limits.reserve_window(period, label=key)
            self._helpers[key] = _StepCCI(period)
        return self._helpers[key]

    def supertrend(
        self,
        name: str,
        factor: float | None = None,
        atr_period: int = 10,
    ) -> _StepSupertrend:
        key = f"supertrend:{name}"
        if key not in self._helpers:
            if factor is None:
                raise ValueError(f"ctx.ta.supertrend('{name}') has not been initialized")
            self._helpers[key] = _StepSupertrend(factor, atr_period)
        return self._helpers[key]

def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 0.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return None if math.isnan(number) else number
