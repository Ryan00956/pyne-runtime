"""
Pyne Technical Analysis — Pine-style ``ta.*`` function library.

All functions accept and return numpy arrays. They can be freely
composed and nested::

    ta.ema(ta.rsi(close, 14), 10)   # smooth RSI with EMA
    ta.bb(ta.ema(close, 20), 20, 2) # Bollinger Bands on EMA

The module is injected as ``ta`` in the script namespace. Functions
that need OHLCV data (like ``atr``, ``tr``, ``obv``) receive a
reference to the runtime context so they can implicitly access
global high/low/close/volume when called without explicit arguments.

Usage::

    # In user scripts — ta is already available
    plot(ta.sma(close, 20), title="SMA 20")
    dif, dea, hist = ta.macd(close)
    mid, upper, lower = ta.bb(close, 20, 2)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from . import utils
from .series import PyneSeries, to_numpy, wrap_like

if TYPE_CHECKING:
    from .context import PyneContext


def _fixnan(values: np.ndarray) -> np.ndarray:
    result = np.array(values, dtype=np.float64, copy=True)
    last = np.nan
    for idx, value in enumerate(result):
        if np.isnan(value):
            if not np.isnan(last):
                result[idx] = last
            continue
        last = value
    return result


_ROLLING_REBASE_CHUNK = 4096
_FLOAT_EXACT_SCALE = 1 << 1074


def _window_sums(values: np.ndarray, period: int) -> np.ndarray:
    cumulative = np.concatenate(
        (np.zeros(1, dtype=values.dtype), np.cumsum(values, dtype=values.dtype))
    )
    return cumulative[period:] - cumulative[:-period]


def _block_window_sums(values: np.ndarray, period: int) -> np.ndarray:
    """Sum windows from block-local prefixes/suffixes, avoiding cumulative poisoning."""
    source = np.asarray(values, dtype=np.float64)
    n = len(source)
    if period == 1:
        return source.copy()

    prefix = np.empty(n, dtype=np.float64)
    suffix = np.empty(n, dtype=np.float64)
    with np.errstate(over="ignore", invalid="ignore"):
        for block_start in range(0, n, period):
            block_stop = min(block_start + period, n)
            block = source[block_start:block_stop]
            prefix[block_start:block_stop] = np.cumsum(block)
            suffix[block_start:block_stop] = np.cumsum(block[::-1])[::-1]

        starts = np.arange(0, n - period + 1, dtype=np.intp)
        ends = starts + period - 1
        sums = suffix[starts] + prefix[ends]
        same_block = starts // period == ends // period
        sums[same_block] = prefix[ends[same_block]]
    return sums


def _exact_window_sums(values: np.ndarray, period: int) -> np.ndarray:
    """Accumulate finite binary64 values exactly, rounding once per output window."""
    source = np.asarray(values, dtype=np.float64)
    result = np.empty(len(source) - period + 1, dtype=np.float64)
    window = [0] * period
    total = 0
    for index, value in enumerate(source):
        numerator, denominator = float(value).as_integer_ratio()
        shift = 1074 - (denominator.bit_length() - 1)
        scaled_value = numerator << shift
        slot = index % period
        if index >= period:
            total -= window[slot]
        window[slot] = scaled_value
        total += scaled_value
        if index < period - 1:
            continue
        output_index = index - period + 1
        try:
            result[output_index] = total / _FLOAT_EXACT_SCALE
        except OverflowError:
            result[output_index] = np.inf if total > 0 else -np.inf
    return result


def _rolling_nansum(values: np.ndarray, period: int) -> np.ndarray:
    """Return full-window ``nansum`` values without letting infinities poison later windows."""
    source = np.asarray(values, dtype=np.float64)
    finite = np.isfinite(source)
    finite_values = np.where(finite, source, 0.0)
    with np.errstate(over="ignore", invalid="ignore"):
        cumulative = np.concatenate(([0.0], np.cumsum(finite_values)))
        left = cumulative[period:]
        right = cumulative[:-period]
        sums = left - right
        cancellation_bound = (
            np.maximum(np.abs(left), np.abs(right)) * np.finfo(np.float64).eps * 4.0
        )
    nonfinite_sums = ~np.isfinite(sums)
    cancellation_risk = np.abs(sums) <= cancellation_bound
    magnitudes = np.abs(finite_values[finite_values != 0.0])
    dynamic_range_is_unsafe = bool(
        len(magnitudes)
        and np.min(magnitudes) <= np.max(magnitudes) * np.finfo(np.float64).eps * 4.0
    )
    if np.any(nonfinite_sums) or dynamic_range_is_unsafe:
        # Binary64 has a bounded exponent range, so fixed-scale integer
        # accumulation remains O(n) while recovering after finite overflow.
        sums = _exact_window_sums(finite_values, period)
    elif np.any(cancellation_risk):
        # Prefix subtraction can erase a small window sum after a much larger
        # historical cumulative value. Block-local prefix/suffix sums recover
        # without an O(n*period) fallback.
        sums = _block_window_sums(finite_values, period)
    positive_infinity = _window_sums((source == np.inf).astype(np.int64), period)
    negative_infinity = _window_sums((source == -np.inf).astype(np.int64), period)

    both = (positive_infinity > 0) & (negative_infinity > 0)
    sums[positive_infinity > 0] = np.inf
    sums[negative_infinity > 0] = -np.inf
    sums[both] = np.nan
    return sums


def _exact_rolling_weighted_sums(values: np.ndarray, period: int) -> np.ndarray:
    """Return 1..period weighted sums with exact binary64 accumulation."""
    source = np.asarray(values, dtype=np.float64)
    result = np.empty(len(source) - period + 1, dtype=np.float64)
    scaled_values: list[int] = []
    for value in source:
        numerator, denominator = float(value).as_integer_ratio()
        shift = 1074 - (denominator.bit_length() - 1)
        scaled_values.append(numerator << shift)

    simple = sum(scaled_values[:period])
    weighted = sum((index + 1) * value for index, value in enumerate(scaled_values[:period]))
    for output_index in range(len(result)):
        try:
            result[output_index] = weighted / _FLOAT_EXACT_SCALE
        except OverflowError:
            result[output_index] = np.inf if weighted > 0 else -np.inf
        next_index = output_index + period
        if next_index >= len(source):
            continue
        outgoing = scaled_values[output_index]
        incoming = scaled_values[next_index]
        weighted = weighted - simple + period * incoming
        simple = simple - outgoing + incoming
    return result


def _rolling_weighted_sums(values: np.ndarray, period: int) -> np.ndarray:
    """Return 1..period weighted sums in O(n), periodically rebasing drift."""
    source = np.asarray(values, dtype=np.float64)
    n = len(source)
    result = np.empty(n - period + 1, dtype=np.float64)
    weights = np.arange(1, period + 1, dtype=np.float64)
    chunk_size = max(period, _ROLLING_REBASE_CHUNK)
    first_output = period - 1
    with np.errstate(over="ignore", invalid="ignore"):
        for output_start in range(first_output, n, chunk_size):
            output_stop = min(output_start + chunk_size, n)
            segment_start = output_start - period + 1
            segment = source[segment_start:output_stop]
            simple = float(np.sum(segment[:period]))
            weighted = float(np.dot(segment[:period], weights))
            for end_index in range(output_start, output_stop):
                result[end_index - period + 1] = weighted
                relative_end = end_index - output_start + period - 1
                next_index = relative_end + 1
                if next_index >= len(segment):
                    continue
                outgoing = segment[relative_end - period + 1]
                incoming = segment[next_index]
                weighted = weighted - simple + period * incoming
                simple = simple - outgoing + incoming

    # An overflowing recurrence can otherwise remain infinite after the large
    # value leaves its window. Exact integer state preserves O(n) recovery.
    if np.any(~np.isfinite(result)) and np.all(np.isfinite(source)):
        return _exact_rolling_weighted_sums(source, period)
    return result


def _rolling_weighted_average_values(source: np.ndarray, period: int) -> np.ndarray:
    """Compute finite weighted averages with block-local centering."""
    values = np.asarray(source, dtype=np.float64)
    n = len(values)
    result = np.empty(n - period + 1, dtype=np.float64)
    denominator = period * (period + 1) / 2.0
    chunk_size = max(period, _ROLLING_REBASE_CHUNK)
    first_output = period - 1
    for output_start in range(first_output, n, chunk_size):
        output_stop = min(output_start + chunk_size, n)
        segment_start = output_start - period + 1
        segment = values[segment_start:output_stop]
        finite = np.isfinite(segment)
        anchor = float(np.mean(segment[finite])) if np.any(finite) else 0.0
        centered = np.where(finite, segment - anchor, 0.0)
        weighted = _rolling_weighted_sums(centered, period)
        result[output_start - period + 1 : output_stop - period + 1] = (
            anchor + weighted / denominator
        )
    return result


def _rolling_linear_regression_values(
    source: np.ndarray,
    period: int,
    offset: int,
) -> np.ndarray:
    """Compute rolling least-squares values in O(n) with centered chunks."""
    values = np.asarray(source, dtype=np.float64)
    n = len(values)
    result = np.full(n, np.nan)
    if period <= 0 or period > n:
        return result
    if period == 1:
        return values.copy()

    x_mean = (period - 1) / 2.0
    denom = period * (period * period - 1) / 12.0
    target_x = float(period - 1 - offset)
    chunk_size = max(period, _ROLLING_REBASE_CHUNK)
    first_output = period - 1
    for output_start in range(first_output, n, chunk_size):
        output_stop = min(output_start + chunk_size, n)
        segment_start = output_start - period + 1
        segment = values[segment_start:output_stop]
        finite = np.isfinite(segment)
        if not np.any(finite):
            continue
        anchor = float(np.mean(segment[finite]))
        centered = np.where(finite, segment - anchor, 0.0)
        counts = _window_sums(finite.astype(np.int64), period)
        sums = _window_sums(centered, period)
        weighted = _rolling_weighted_sums(centered, period) - sums
        slopes = (weighted - x_mean * sums) / denom
        means = anchor + sums / period
        values_at_target = means + slopes * (target_x - x_mean)
        values_at_target[counts != period] = np.nan
        result[output_start:output_stop] = values_at_target
    return result


class _FenwickTree:
    """Coordinate-compressed rolling counts and sums in O(log n)."""

    def __init__(self, size: int) -> None:
        self.counts = np.zeros(size + 1, dtype=np.int64)
        self.sums = [0] * (size + 1)

    def add(self, index: int, count: int, value: int) -> None:
        position = index + 1
        while position < len(self.counts):
            self.counts[position] += count
            self.sums[position] += value
            position += position & -position

    def prefix(self, stop: int) -> tuple[int, int]:
        count = 0
        total = 0
        position = stop
        while position > 0:
            count += int(self.counts[position])
            total += self.sums[position]
            position -= position & -position
        return count, total

    def kth(self, order: int) -> int:
        """Return the zero-based coordinate containing a one-based order statistic."""
        position = 0
        size = len(self.counts) - 1
        step = 1 << (size.bit_length() - 1)
        remaining = int(order)
        while step:
            candidate = position + step
            if candidate < len(self.counts) and self.counts[candidate] < remaining:
                remaining -= int(self.counts[candidate])
                position = candidate
            step >>= 1
        return position


def _rolling_mean_and_mad(
    source: np.ndarray,
    period: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return full-window means and exact mean absolute deviations in O(n log n)."""
    values = np.asarray(source, dtype=np.float64)
    n = len(values)
    means = np.full(n, np.nan)
    deviations = np.full(n, np.nan)
    if period <= 0 or period > n:
        return means, deviations

    finite = np.isfinite(values)
    if period == 1:
        means[finite] = values[finite]
        deviations[finite] = 0.0
        return means, deviations
    if not np.any(finite):
        return means, deviations
    coordinates = np.unique(values[finite])
    ranks = np.full(n, -1, dtype=np.intp)
    ranks[finite] = np.searchsorted(coordinates, values[finite])
    scaled_values = [0] * n
    for index in np.flatnonzero(finite):
        numerator, denominator = float(values[index]).as_integer_ratio()
        shift = 1074 - (denominator.bit_length() - 1)
        scaled_values[int(index)] = numerator << shift
    tree = _FenwickTree(len(coordinates))
    invalid_count = 0
    window_sum = 0

    for index in range(n):
        if finite[index]:
            scaled = scaled_values[index]
            tree.add(int(ranks[index]), 1, scaled)
            window_sum += scaled
        else:
            invalid_count += 1
        if index >= period:
            outgoing = index - period
            if finite[outgoing]:
                scaled = scaled_values[outgoing]
                tree.add(int(ranks[outgoing]), -1, -scaled)
                window_sum -= scaled
            else:
                invalid_count -= 1
        if index < period - 1 or invalid_count:
            continue

        mean = window_sum / (_FLOAT_EXACT_SCALE * period)
        split = int(np.searchsorted(coordinates, mean, side="right"))
        left_count, left_sum = tree.prefix(split)
        right_count = period - left_count
        right_sum = window_sum - left_sum
        minimum = tree.kth(1)
        maximum = tree.kth(period)
        if minimum == maximum:
            means[index] = mean
            deviations[index] = 0.0
            continue
        absolute_numerator = (
            window_sum * left_count
            - period * left_sum
            + period * right_sum
            - window_sum * right_count
        )
        means[index] = mean
        deviations[index] = max(
            absolute_numerator / (_FLOAT_EXACT_SCALE * period * period),
            0.0,
        )
    return means, deviations


def _interpolate_hazen(lower: float, upper: float, fraction: float) -> float:
    with np.errstate(over="ignore", invalid="ignore"):
        difference = upper - lower
        if fraction >= 0.5:
            return float(upper - difference * (1.0 - fraction))
        return float(lower + difference * fraction)


def _rolling_percentile_values(
    source: np.ndarray,
    period: int,
    percentage: float,
    *,
    linear: bool,
) -> np.ndarray:
    """Compute exact rolling order statistics in O(n log n)."""
    values = np.asarray(source, dtype=np.float64)
    n = len(values)
    result = np.full(n, np.nan)
    if period <= 0 or period > n:
        return result

    valid = ~np.isnan(values)
    if not np.any(valid):
        return result
    coordinates = np.unique(values[valid])
    ranks = np.full(n, -1, dtype=np.intp)
    ranks[valid] = np.searchsorted(coordinates, values[valid])
    tree = _FenwickTree(len(coordinates))
    invalid_count = 0
    pct = float(np.clip(percentage, 0.0, 100.0))
    nearest_rank = max(int(np.ceil(pct / 100.0 * period)), 1)
    virtual_index = pct / 100.0 * period - 0.5

    for index in range(n):
        if valid[index]:
            tree.add(int(ranks[index]), 1, 0.0)
        else:
            invalid_count += 1
        if index >= period:
            outgoing = index - period
            if valid[outgoing]:
                tree.add(int(ranks[outgoing]), -1, 0.0)
            else:
                invalid_count -= 1
        if index < period - 1 or invalid_count:
            continue

        if not linear:
            result[index] = coordinates[tree.kth(nearest_rank)]
            continue
        if virtual_index < 0.0:
            boundary = float(coordinates[tree.kth(1)])
            result[index] = _interpolate_hazen(boundary, boundary, 0.0)
            continue
        if virtual_index >= period - 1:
            boundary = float(coordinates[tree.kth(period)])
            result[index] = _interpolate_hazen(boundary, boundary, 0.0)
            continue
        lower_order = int(np.floor(virtual_index)) + 1
        fraction = virtual_index - np.floor(virtual_index)
        lower = float(coordinates[tree.kth(lower_order)])
        upper = float(coordinates[tree.kth(lower_order + 1)])
        result[index] = _interpolate_hazen(lower, upper, fraction)
    return result


_DIRECT_CONVOLUTION_WORK_LIMIT = 1_000_000


def _valid_weighted_convolution(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Return valid correlation, switching to FFT before direct work can grow quadratic."""
    source = np.asarray(values, dtype=np.float64)
    kernel = np.asarray(weights, dtype=np.float64)
    if len(source) * len(kernel) <= _DIRECT_CONVOLUTION_WORK_LIMIT:
        return np.correlate(source, kernel, mode="valid")

    finite = np.isfinite(source)
    anchor = float(np.mean(source[finite])) if np.any(finite) else 0.0
    centered = np.where(finite, source - anchor, 0.0)
    output_size = len(source) + len(kernel) - 1
    fft_size = 1 << (output_size - 1).bit_length()
    transformed = np.fft.rfft(centered, fft_size) * np.fft.rfft(kernel[::-1], fft_size)
    convolution = np.fft.irfft(transformed, fft_size)[:output_size]
    return convolution[len(kernel) - 1 : len(source)] + anchor * np.sum(kernel)


def _valid_boolean_correlation(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    correlated = _valid_weighted_convolution(
        np.asarray(values, dtype=np.float64),
        np.asarray(weights, dtype=np.float64),
    )
    return np.rint(correlated).astype(np.int64)


def _rolling_variance_values(source: np.ndarray, period: int, ddof: int) -> np.ndarray:
    """Compute full-window variance in O(n) with periodically rebased centered moments."""
    values = np.asarray(source, dtype=np.float64)
    n = len(values)
    result = np.full(n, np.nan)
    if period <= 0 or period > n or period - ddof <= 0:
        return result

    chunk_size = max(period, _ROLLING_REBASE_CHUNK)
    first_output = period - 1
    for output_start in range(first_output, n, chunk_size):
        output_stop = min(output_start + chunk_size, n)
        segment_start = output_start - period + 1
        segment = values[segment_start:output_stop]
        valid = np.isfinite(segment)
        if not np.any(valid):
            continue

        # Rebasing keeps the cumulative moments small even for 1e12-scale inputs.
        anchor = float(np.mean(segment[valid]))
        centered = np.where(valid, segment - anchor, 0.0)
        counts = _window_sums(valid.astype(np.int64), period)
        sums = _window_sums(centered, period)
        squared_sums = _window_sums(centered * centered, period)
        numerator = squared_sums - sums * sums / period
        np.maximum(numerator, 0.0, out=numerator)
        variances = numerator / (period - ddof)
        variances[counts != period] = np.nan
        result[output_start:output_stop] = variances
    return result


def _rolling_correlation_values(
    source_a: np.ndarray,
    source_b: np.ndarray,
    period: int,
) -> np.ndarray:
    """Compute rolling Pearson correlation using periodically rebased moments."""
    a = np.asarray(source_a, dtype=np.float64)
    b = np.asarray(source_b, dtype=np.float64)
    n = min(len(a), len(b))
    result = np.full(n, np.nan)
    if period <= 1 or period > n:
        return result

    a = a[:n]
    b = b[:n]
    chunk_size = max(period, _ROLLING_REBASE_CHUNK)
    first_output = period - 1
    for output_start in range(first_output, n, chunk_size):
        output_stop = min(output_start + chunk_size, n)
        segment_start = output_start - period + 1
        a_segment = a[segment_start:output_stop]
        b_segment = b[segment_start:output_stop]
        valid = np.isfinite(a_segment) & np.isfinite(b_segment)
        if not np.any(valid):
            continue

        a_anchor = float(np.mean(a_segment[valid]))
        b_anchor = float(np.mean(b_segment[valid]))
        a_centered = np.where(valid, a_segment - a_anchor, 0.0)
        b_centered = np.where(valid, b_segment - b_anchor, 0.0)
        counts = _window_sums(valid.astype(np.int64), period)
        a_sums = _window_sums(a_centered, period)
        b_sums = _window_sums(b_centered, period)
        a_squared_sums = _window_sums(a_centered * a_centered, period)
        b_squared_sums = _window_sums(b_centered * b_centered, period)
        product_sums = _window_sums(a_centered * b_centered, period)

        a_m2 = a_squared_sums - a_sums * a_sums / period
        b_m2 = b_squared_sums - b_sums * b_sums / period
        covariance = product_sums - a_sums * b_sums / period
        np.maximum(a_m2, 0.0, out=a_m2)
        np.maximum(b_m2, 0.0, out=b_m2)
        with np.errstate(divide="ignore", invalid="ignore"):
            correlations = covariance / np.sqrt(a_m2 * b_m2)
        invalid = (counts != period) | (a_m2 <= 0.0) | (b_m2 <= 0.0)
        correlations[invalid] = np.nan
        np.clip(correlations, -1.0, 1.0, out=correlations)
        result[output_start:output_stop] = correlations
    return result


class TaModule:
    """Pine-style technical analysis namespace.

    Instantiated with a reference to the current ``PyneContext`` so
    functions like ``atr(14)`` can implicitly use global OHLCV data.
    """

    def __init__(self, ctx: PyneContext | None = None) -> None:
        self._ctx = ctx

    def bind(self, ctx: PyneContext) -> None:
        """Bind to a context (called by runtime before script exec)."""
        self._ctx = ctx

    # ═══════════════════════════════════════════════════════════
    #  Moving Averages
    # ═══════════════════════════════════════════════════════════

    def sma(self, src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
        """Simple Moving Average.

        Pine equivalent: ``ta.sma(close, 20)``
        """
        source = to_numpy(src, dtype=np.float64)
        n = len(source)
        result = np.full(n, np.nan)
        if period <= 0 or period > n:
            return wrap_like(result, src)
        clean = np.where(np.isnan(source), 0.0, source)
        sums = np.cumsum(clean)
        counts = np.cumsum(~np.isnan(source))
        window_sums = sums[period - 1 :].copy()
        window_counts = counts[period - 1 :].copy()
        if period < n:
            window_sums[1:] -= sums[: n - period]
            window_counts[1:] -= counts[: n - period]
        valid = window_counts == period
        result[period - 1 :][valid] = window_sums[valid] / period
        return wrap_like(result, src)

    def ema(self, src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
        """Exponential Moving Average.

        Pine equivalent: ``ta.ema(close, 20)``

        Uses SMA as the seed value for the first ``period`` bars,
        matching Pine Script / TradingView behavior.
        """
        source = to_numpy(src, dtype=np.float64)
        n = len(source)
        result = np.full(n, np.nan)
        if period <= 0 or period > n:
            return wrap_like(result, src)

        k = 2.0 / (period + 1)

        # Seed with SMA
        window = source[:period]
        valid = window[~np.isnan(window)]
        if len(valid) == 0:
            return wrap_like(result, src)
        seed = float(np.mean(valid))
        result[period - 1] = seed

        for i in range(period, n):
            val = source[i]
            if np.isnan(val):
                result[i] = result[i - 1]
            else:
                result[i] = val * k + result[i - 1] * (1 - k)

        return wrap_like(result, src)

    def wma(self, src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
        """Weighted Moving Average.

        Pine equivalent: ``ta.wma(close, 20)``

        Weights: [1, 2, 3, ..., period]. Most recent bar has highest weight.
        """
        source = to_numpy(src, dtype=np.float64)
        n = len(source)
        result = np.full(n, np.nan)
        if period <= 0 or period > n:
            return wrap_like(result, src)

        window_values = _rolling_weighted_average_values(source, period)
        nan_counts = _window_sums(np.isnan(source).astype(np.int64), period)
        positive_infinity = _window_sums((source == np.inf).astype(np.int64), period)
        negative_infinity = _window_sums((source == -np.inf).astype(np.int64), period)
        window_values[positive_infinity > 0] = np.inf
        window_values[negative_infinity > 0] = -np.inf
        window_values[(positive_infinity > 0) & (negative_infinity > 0)] = np.nan
        window_values[nan_counts > 0] = np.nan
        result[period - 1 :] = window_values

        return wrap_like(result, src)

    def hma(self, src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
        """Hull Moving Average.

        Pine equivalent: ``ta.hma(close, 20)``.
        """
        if period <= 0:
            return wrap_like(np.full(len(to_numpy(src)), np.nan), src)
        half = max(int(period / 2), 1)
        root = max(int(np.sqrt(period)), 1)
        fast = self.wma(src, half)
        slow = self.wma(src, period)
        return self.wma(2 * fast - slow, root)

    def swma(self, src: PyneSeries | np.ndarray) -> PyneSeries | np.ndarray:
        """Symmetrically weighted moving average.

        Pine equivalent: ``ta.swma(close)``. Uses weights ``[1, 2, 2, 1] / 6``.
        """
        source = to_numpy(src, dtype=np.float64)
        n = len(source)
        result = np.full(n, np.nan)
        weights = np.array([1.0, 2.0, 2.0, 1.0], dtype=np.float64)
        for idx in range(3, n):
            window = source[idx - 3 : idx + 1]
            if not np.any(np.isnan(window)):
                result[idx] = float(np.dot(window, weights) / 6.0)
        return wrap_like(result, src)

    def alma(
        self,
        src: PyneSeries | np.ndarray,
        period: int,
        offset: float = 0.85,
        sigma: float = 6.0,
    ) -> PyneSeries | np.ndarray:
        """Arnaud Legoux Moving Average.

        Pine equivalent: ``ta.alma(close, 20, 0.85, 6)``.
        """
        source = to_numpy(src, dtype=np.float64)
        n = len(source)
        result = np.full(n, np.nan)
        if period <= 0 or period > n or sigma == 0:
            return wrap_like(result, src)

        m = offset * (period - 1)
        s = period / sigma
        positions = np.arange(period, dtype=np.float64)
        weights = np.exp(-((positions - m) ** 2) / (2 * s * s))
        weights = weights / np.sum(weights)

        clean = np.where(np.isfinite(source), source, 0.0)
        window_values = _valid_weighted_convolution(clean, weights)
        nan_counts = _window_sums(np.isnan(source).astype(np.int64), period)
        nonzero_weights = weights != 0.0
        zero_weights = ~nonzero_weights
        positive_infinity = _valid_boolean_correlation(
            source == np.inf,
            nonzero_weights,
        )
        negative_infinity = _valid_boolean_correlation(
            source == -np.inf,
            nonzero_weights,
        )
        zero_weight_infinity = _valid_boolean_correlation(
            np.isinf(source),
            zero_weights,
        )
        window_values[positive_infinity > 0] = np.inf
        window_values[negative_infinity > 0] = -np.inf
        window_values[(positive_infinity > 0) & (negative_infinity > 0)] = np.nan
        window_values[zero_weight_infinity > 0] = np.nan
        window_values[nan_counts > 0] = np.nan
        result[period - 1 :] = window_values

        return wrap_like(result, src)

    def vwma(
        self,
        src: PyneSeries | np.ndarray,
        period: int,
        volume: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """Volume-Weighted Moving Average.

        Pine equivalent: ``ta.vwma(close, 20)``

        If ``volume`` is not provided, uses the global volume from context.
        """
        if volume is None:
            if self._ctx is None:
                raise RuntimeError(
                    "ta.vwma() needs volume data — pass it explicitly or use within a Pyne script"
                )
            volume = self._ctx.volume

        source = to_numpy(src, dtype=np.float64)
        volume_arr = to_numpy(volume, dtype=np.float64)
        n = len(source)
        result = np.full(n, np.nan)
        if period <= 0 or period > n:
            return wrap_like(result, src)

        pv = source * volume_arr
        numerator = _rolling_nansum(pv, period)
        denominator = _rolling_nansum(volume_arr, period)
        with np.errstate(divide="ignore", invalid="ignore"):
            result[period - 1 :] = np.where(
                denominator > 0.0,
                numerator / denominator,
                np.nan,
            )

        return wrap_like(result, src)

    def rma(self, src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
        """Running Moving Average (Wilder's smoothing).

        Pine equivalent: ``ta.rma(close, 14)``

        Also known as Wilder's EMA. Used internally by RSI and ATR.
        ``alpha = 1 / period``
        """
        source = to_numpy(src, dtype=np.float64)
        n = len(source)
        result = np.full(n, np.nan)
        if period <= 0 or period > n:
            return wrap_like(result, src)

        alpha = 1.0 / period

        count = 0
        seed_sum = 0.0
        rma_value = np.nan
        for i in range(n):
            val = source[i]
            if np.isnan(val):
                if not np.isnan(rma_value):
                    result[i] = rma_value
                continue
            if count < period:
                count += 1
                seed_sum += val
                if count == period:
                    rma_value = seed_sum / period
                    result[i] = rma_value
                continue
            rma_value = alpha * val + (1 - alpha) * rma_value
            result[i] = rma_value

        return wrap_like(result, src)

    # ═══════════════════════════════════════════════════════════
    #  Oscillators
    # ═══════════════════════════════════════════════════════════

    def rsi(self, src: PyneSeries | np.ndarray, period: int = 14) -> PyneSeries | np.ndarray:
        """Relative Strength Index.

        Pine equivalent: ``ta.rsi(close, 14)``
        """
        source = to_numpy(src, dtype=np.float64)
        delta = to_numpy(utils.change(source, 1), dtype=np.float64)
        gain = np.where(np.isnan(delta), np.nan, np.where(delta > 0, delta, 0.0))
        loss = np.where(np.isnan(delta), np.nan, np.where(delta < 0, -delta, 0.0))

        avg_gain = self.rma(gain, period)
        avg_loss = self.rma(loss, period)

        with np.errstate(divide="ignore", invalid="ignore"):
            rs = np.where(avg_loss != 0, avg_gain / avg_loss, np.inf)
            rsi_val = 100.0 - 100.0 / (1.0 + rs)

        # Where avg_loss is 0 (all gains), RSI = 100
        rsi_val = np.where(avg_loss == 0, 100.0, rsi_val)
        # Where avg_gain is 0 (all losses), RSI = 0
        rsi_val = np.where(avg_gain == 0, 0.0, rsi_val)
        # Preserve NaN in warmup period
        rsi_val[:period] = np.nan

        return wrap_like(rsi_val, src)

    def cmo(self, src: PyneSeries | np.ndarray, period: int = 14) -> PyneSeries | np.ndarray:
        """Chande Momentum Oscillator.

        Pine equivalent: ``ta.cmo(close, 14)``.
        """
        source = to_numpy(src, dtype=np.float64)
        delta = to_numpy(utils.change(source, 1), dtype=np.float64)
        up = np.where(delta > 0, delta, 0.0)
        down = np.where(delta < 0, -delta, 0.0)
        up[0] = 0.0
        down[0] = 0.0
        up_sum = to_numpy(utils.sum_(up, period), dtype=np.float64)
        down_sum = to_numpy(utils.sum_(down, period), dtype=np.float64)
        with np.errstate(divide="ignore", invalid="ignore"):
            result = np.where(
                (up_sum + down_sum) != 0,
                100.0 * (up_sum - down_sum) / (up_sum + down_sum),
                0.0,
            )
        result[:period] = np.nan
        return wrap_like(result, src)

    def wpr(
        self,
        period: int = 14,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """Williams Percent Range.

        Pine-style helper for Williams %R over the current OHLC context.
        """
        if high is None:
            if self._ctx is None:
                raise RuntimeError("ta.wpr() needs OHLC data")
            high = self._ctx.high
        if low is None:
            low = self._ctx.low
        if close is None:
            close = self._ctx.close

        high_arr = to_numpy(high, dtype=np.float64)
        low_arr = to_numpy(low, dtype=np.float64)
        close_arr = to_numpy(close, dtype=np.float64)
        highest = to_numpy(utils.highest(high_arr, period), dtype=np.float64)
        lowest = to_numpy(utils.lowest(low_arr, period), dtype=np.float64)
        with np.errstate(divide="ignore", invalid="ignore"):
            result = np.where(
                (highest - lowest) != 0,
                -100.0 * (highest - close_arr) / (highest - lowest),
                0.0,
            )
        return wrap_like(result, high, low, close)

    def tsi(
        self,
        src: PyneSeries | np.ndarray,
        short: int = 13,
        long: int = 25,
    ) -> PyneSeries | np.ndarray:
        """True Strength Index.

        Pine equivalent: ``ta.tsi(source, short_length, long_length)``.
        """
        source = to_numpy(src, dtype=np.float64)
        momentum = to_numpy(utils.change(source, 1), dtype=np.float64)
        abs_momentum = np.abs(momentum)
        smooth_mom = _ema_skip_leading_na(_ema_skip_leading_na(momentum, long), short)
        smooth_abs = _ema_skip_leading_na(_ema_skip_leading_na(abs_momentum, long), short)
        with np.errstate(divide="ignore", invalid="ignore"):
            result = np.where(smooth_abs != 0, smooth_mom / smooth_abs, np.nan)
        return wrap_like(result, src)

    def stoch(
        self,
        source: PyneSeries | np.ndarray,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        period: int = 14,
        *,
        k_period: int | None = None,
    ) -> PyneSeries | np.ndarray:
        """Stochastic oscillator.

        Pine equivalent: ``ta.stoch(source, high, low, length)``.
        """
        if high is None:
            if self._ctx is None:
                raise RuntimeError(
                    "ta.stoch() needs high/low — pass explicitly or use within Pyne script"
                )
            high = self._ctx.high
        if low is None:
            low = self._ctx.low

        length = k_period if k_period is not None else period
        source_arr = to_numpy(source, dtype=np.float64)
        high_arr = to_numpy(high, dtype=np.float64)
        low_arr = to_numpy(low, dtype=np.float64)
        hh = to_numpy(utils.highest(high_arr, length), dtype=np.float64)
        ll = to_numpy(utils.lowest(low_arr, length), dtype=np.float64)

        with np.errstate(divide="ignore", invalid="ignore"):
            result = np.where(
                (hh - ll) != 0,
                100.0 * (source_arr - ll) / (hh - ll),
                50.0,
            )

        return wrap_like(result, source, high, low)

    def cci(
        self,
        source: PyneSeries | np.ndarray | None = None,
        period: int = 20,
        *,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """Commodity Channel Index.

        Pine equivalent: ``ta.cci(source, length)``.
        """
        if source is None:
            if high is None:
                if self._ctx is None:
                    raise RuntimeError("ta.cci() needs a source series")
                high = self._ctx.high
            if low is None:
                low = self._ctx.low
            if close is None:
                close = self._ctx.close
            source = (
                to_numpy(high, dtype=np.float64)
                + to_numpy(low, dtype=np.float64)
                + to_numpy(close, dtype=np.float64)
            ) / 3.0

        source_arr = to_numpy(source, dtype=np.float64)
        source_sma, mad = _rolling_mean_and_mad(source_arr, period)

        with np.errstate(divide="ignore", invalid="ignore"):
            result = np.where(mad != 0, (source_arr - source_sma) / (0.015 * mad), 0.0)
        result[: period - 1] = np.nan
        return wrap_like(result, source)

    # ═══════════════════════════════════════════════════════════
    #  Trend Indicators
    # ═══════════════════════════════════════════════════════════

    def macd(
        self,
        src: PyneSeries | np.ndarray,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> tuple[PyneSeries | np.ndarray, PyneSeries | np.ndarray, PyneSeries | np.ndarray]:
        """MACD — Moving Average Convergence Divergence.

        Pine equivalent: ``ta.macd(close, 12, 26, 9)``

        Returns:
            Tuple of (MACD line, signal line, histogram) arrays.
            ``histogram = macd_line - signal_line``.
        """
        ema_fast = self.ema(src, fast)
        ema_slow = self.ema(src, slow)
        dif = ema_fast - ema_slow
        dea = wrap_like(_ema_skip_leading_na(to_numpy(dif, dtype=np.float64), signal), src)
        hist = dif - dea
        return dif, dea, hist

    def mom(self, src: PyneSeries | np.ndarray, period: int = 1) -> PyneSeries | np.ndarray:
        """Momentum over ``period`` bars.

        Pine equivalent: ``ta.mom(close, 10)``.
        """
        source = to_numpy(src, dtype=np.float64)
        previous = to_numpy(utils.shift(source, period), dtype=np.float64)
        return wrap_like(source - previous, src)

    def linreg(
        self,
        src: PyneSeries | np.ndarray,
        period: int,
        offset: int = 0,
    ) -> PyneSeries | np.ndarray:
        """Linear regression curve.

        Pine equivalent: ``ta.linreg(source, length, offset)``.
        """
        source = to_numpy(src, dtype=np.float64)
        result = _rolling_linear_regression_values(source, period, offset)
        return wrap_like(result, src)

    def correlation(
        self,
        source_a: PyneSeries | np.ndarray,
        source_b: PyneSeries | np.ndarray,
        period: int,
    ) -> PyneSeries | np.ndarray:
        """Rolling Pearson correlation.

        Pine equivalent: ``ta.correlation(source1, source2, length)``.
        """
        a = to_numpy(source_a, dtype=np.float64)
        b = to_numpy(source_b, dtype=np.float64)
        result = _rolling_correlation_values(a, b, period)
        return wrap_like(result, source_a, source_b)

    def adx(
        self,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
        period: int = 14,
    ) -> PyneSeries | np.ndarray:
        """Average Directional Index.

        Pine equivalent: ``ta.adx(high, low, close, 14)``

        Returns:
            ADX array.
        """
        if high is None:
            if self._ctx is None:
                raise RuntimeError("ta.adx() needs OHLC data")
            high = self._ctx.high
        if low is None:
            low = self._ctx.low
        if close is None:
            close = self._ctx.close

        _, _, adx_val = self._dmi_components(high, low, close, period, period)
        return wrap_like(adx_val, high, low, close)

    def dmi(
        self,
        period: int = 14,
        adx_period: int = 14,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
    ) -> tuple[PyneSeries | np.ndarray, PyneSeries | np.ndarray, PyneSeries | np.ndarray]:
        """Directional Movement Index.

        Pine equivalent: ``ta.dmi(diLength, adxSmoothing)``.
        Returns ``(+DI, -DI, ADX)``.
        """
        if high is None:
            if self._ctx is None:
                raise RuntimeError("ta.dmi() needs OHLC data")
            high = self._ctx.high
        if low is None:
            low = self._ctx.low
        if close is None:
            close = self._ctx.close

        plus_di, minus_di, adx_val = self._dmi_components(
            high,
            low,
            close,
            period,
            adx_period,
        )

        return (
            wrap_like(plus_di, high, low, close),
            wrap_like(minus_di, high, low, close),
            wrap_like(adx_val, high, low, close),
        )

    def _dmi_components(
        self,
        high: PyneSeries | np.ndarray,
        low: PyneSeries | np.ndarray,
        close: PyneSeries | np.ndarray,
        period: int,
        adx_period: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        high_arr = to_numpy(high, dtype=np.float64)
        low_arr = to_numpy(low, dtype=np.float64)
        close_arr = to_numpy(close, dtype=np.float64)
        up_move = to_numpy(utils.change(high_arr, 1), dtype=np.float64)
        down_move = -to_numpy(utils.change(low_arr, 1), dtype=np.float64)

        plus_dm = np.where(
            np.isnan(up_move),
            np.nan,
            np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        )
        minus_dm = np.where(
            np.isnan(down_move),
            np.nan,
            np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        )
        trur = to_numpy(self.atr(period, high_arr, low_arr, close_arr), dtype=np.float64)
        plus_smoothed = to_numpy(self.rma(plus_dm, period), dtype=np.float64)
        minus_smoothed = to_numpy(self.rma(minus_dm, period), dtype=np.float64)

        with np.errstate(divide="ignore", invalid="ignore"):
            plus_di = _fixnan(100.0 * plus_smoothed / trur)
            minus_di = _fixnan(100.0 * minus_smoothed / trur)
            total = plus_di + minus_di
            denominator = np.where(total == 0.0, 1.0, total)
            dx_ratio = np.abs(plus_di - minus_di) / denominator
            adx_val = 100.0 * to_numpy(self.rma(dx_ratio, adx_period), dtype=np.float64)
        return plus_di, minus_di, adx_val

    def sar(
        self,
        start: float = 0.02,
        increment: float = 0.02,
        maximum: float = 0.2,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """Parabolic SAR.

        Pine equivalent: ``ta.sar(start, increment, max)``.
        """
        if high is None:
            if self._ctx is None:
                raise RuntimeError("ta.sar() needs high/low data")
            high = self._ctx.high
        if low is None:
            low = self._ctx.low
        if close is None and self._ctx is not None:
            close = self._ctx.close

        high_arr = to_numpy(high, dtype=np.float64)
        low_arr = to_numpy(low, dtype=np.float64)
        close_arr = (
            to_numpy(close, dtype=np.float64) if close is not None else (high_arr + low_arr) / 2.0
        )
        n = len(high_arr)
        result = np.full(n, np.nan)
        if n < 2:
            return wrap_like(result, high, low)

        sar_value = np.nan
        max_min = np.nan
        acceleration = np.nan
        is_below = False

        for idx in range(n):
            is_first_trend_bar = False
            if np.isnan(high_arr[idx]) or np.isnan(low_arr[idx]) or np.isnan(close_arr[idx]):
                sar_value = np.nan
                max_min = np.nan
                acceleration = np.nan
                continue

            if np.isnan(sar_value) and idx > 0 and not np.isnan(close_arr[idx - 1]):
                if close_arr[idx] > close_arr[idx - 1]:
                    is_below = True
                    max_min = high_arr[idx]
                    sar_value = low_arr[idx - 1]
                else:
                    is_below = False
                    max_min = low_arr[idx]
                    sar_value = high_arr[idx - 1]
                is_first_trend_bar = True
                acceleration = float(start)
            elif not np.isnan(sar_value):
                sar_value = sar_value + acceleration * (max_min - sar_value)
                if is_below:
                    if sar_value > low_arr[idx]:
                        is_first_trend_bar = True
                        is_below = False
                        sar_value = max(high_arr[idx], max_min)
                        max_min = low_arr[idx]
                        acceleration = float(start)
                else:
                    if sar_value < high_arr[idx]:
                        is_first_trend_bar = True
                        is_below = True
                        sar_value = min(low_arr[idx], max_min)
                        max_min = high_arr[idx]
                        acceleration = float(start)

                if not is_first_trend_bar:
                    if is_below:
                        if high_arr[idx] > max_min:
                            max_min = high_arr[idx]
                            acceleration = min(acceleration + increment, maximum)
                    elif low_arr[idx] < max_min:
                        max_min = low_arr[idx]
                        acceleration = min(acceleration + increment, maximum)

                if is_below:
                    sar_value = min(sar_value, low_arr[idx - 1])
                    if idx > 1 and not np.isnan(low_arr[idx - 2]):
                        sar_value = min(sar_value, low_arr[idx - 2])
                else:
                    sar_value = max(sar_value, high_arr[idx - 1])
                    if idx > 1 and not np.isnan(high_arr[idx - 2]):
                        sar_value = max(sar_value, high_arr[idx - 2])

            result[idx] = sar_value

        return wrap_like(result, high, low, close)

    def supertrend(
        self,
        factor: float = 3.0,
        atr_period: int = 10,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
        *,
        period: int | None = None,
        mult: float | None = None,
    ) -> tuple[PyneSeries | np.ndarray, PyneSeries | np.ndarray]:
        """Supertrend indicator.

        Pine equivalent: ``ta.supertrend(factor, atrPeriod)``.

        Returns:
            Tuple of (supertrend_line, direction) arrays.
            direction follows Pine's convention: 1 = downtrend, -1 = uptrend.
        """
        if period is not None:
            atr_period = period
        if mult is not None:
            factor = mult

        if high is None:
            if self._ctx is None:
                raise RuntimeError("ta.supertrend() needs OHLC data")
            high = self._ctx.high
        if low is None:
            low = self._ctx.low
        if close is None:
            close = self._ctx.close

        high_arr = to_numpy(high, dtype=np.float64)
        low_arr = to_numpy(low, dtype=np.float64)
        close_arr = to_numpy(close, dtype=np.float64)
        atr_val = to_numpy(self.atr(atr_period, high_arr, low_arr, close_arr), dtype=np.float64)
        hl2 = (high_arr + low_arr) / 2.0

        n = len(close_arr)
        upper_band = hl2 + factor * atr_val
        lower_band = hl2 - factor * atr_val
        supertrend = np.full(n, np.nan)
        direction = np.full(n, np.nan)

        if n:
            supertrend[0] = 0.0

        for i in range(n):
            prev_lower_band = 0.0 if i == 0 or np.isnan(lower_band[i - 1]) else lower_band[i - 1]
            prev_upper_band = 0.0 if i == 0 or np.isnan(upper_band[i - 1]) else upper_band[i - 1]
            prev_close = np.nan if i == 0 else close_arr[i - 1]

            if not np.isnan(lower_band[i]):
                if not (lower_band[i] > prev_lower_band or prev_close < prev_lower_band):
                    lower_band[i] = prev_lower_band

            if not np.isnan(upper_band[i]):
                if not (upper_band[i] < prev_upper_band or prev_close > prev_upper_band):
                    upper_band[i] = prev_upper_band

            if i == 0 or np.isnan(atr_val[i - 1]):
                direction[i] = 1.0
            else:
                prev_supertrend = supertrend[i - 1]
                if not np.isnan(prev_supertrend) and prev_supertrend == prev_upper_band:
                    direction[i] = -1.0 if close_arr[i] > upper_band[i] else 1.0
                else:
                    direction[i] = 1.0 if close_arr[i] < lower_band[i] else -1.0

            if not np.isnan(upper_band[i]) and not np.isnan(lower_band[i]):
                supertrend[i] = lower_band[i] if direction[i] == -1.0 else upper_band[i]

        return wrap_like(supertrend, high, low, close), wrap_like(direction, high, low, close)

    # ═══════════════════════════════════════════════════════════
    #  Volatility
    # ═══════════════════════════════════════════════════════════

    def tr(
        self,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """True Range.

        Pine equivalent: ``ta.tr``
        """
        if high is None:
            if self._ctx is None:
                raise RuntimeError("ta.tr() needs OHLC data")
            high = self._ctx.high
        if low is None:
            low = self._ctx.low
        if close is None:
            close = self._ctx.close

        high_arr = to_numpy(high, dtype=np.float64)
        low_arr = to_numpy(low, dtype=np.float64)
        close_arr = to_numpy(close, dtype=np.float64)
        prev_close = to_numpy(utils.shift(close_arr, 1), dtype=np.float64)
        tr1 = high_arr - low_arr
        tr2 = np.abs(high_arr - prev_close)
        tr3 = np.abs(low_arr - prev_close)
        result = np.where(np.isnan(prev_close), tr1, np.maximum(tr1, np.maximum(tr2, tr3)))
        return wrap_like(result, high, low, close)

    def atr(
        self,
        period: int = 14,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """Average True Range.

        Pine equivalent: ``ta.atr(14)``

        When called without high/low/close, uses the global context data.
        """
        tr_val = self.tr(high, low, close)
        return self.rma(tr_val, period)

    def bb(
        self,
        src: PyneSeries | np.ndarray,
        period: int = 20,
        mult: float = 2.0,
    ) -> tuple[PyneSeries | np.ndarray, PyneSeries | np.ndarray, PyneSeries | np.ndarray]:
        """Bollinger Bands.

        Pine equivalent: ``ta.bb(close, 20, 2)``

        Returns:
            Tuple of (middle, upper, lower) arrays.
        """
        middle = self.sma(src, period)
        sd = self.stdev(src, period)
        upper = middle + mult * sd
        lower = middle - mult * sd
        return middle, upper, lower

    def stdev(self, src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
        """Rolling Standard Deviation (O(n) optimized).

        Pine equivalent: ``ta.stdev(close, 20)``

        Uses periodically rebased centered moments. Windows containing missing
        values remain missing without forcing the rest of the series onto a
        per-window fallback path.
        """
        source = to_numpy(src, dtype=np.float64)
        result = _rolling_variance_values(source, period, ddof=0)
        np.sqrt(result, out=result)
        return wrap_like(result, src)

    def variance(
        self,
        src: PyneSeries | np.ndarray,
        period: int,
        biased: bool = True,
    ) -> PyneSeries | np.ndarray:
        """Rolling variance.

        Pine equivalent: ``ta.variance(close, 20, true)``.
        """
        ddof = 0 if biased else 1
        source = to_numpy(src, dtype=np.float64)
        result = _rolling_variance_values(source, period, ddof=ddof)
        return wrap_like(result, src)

    def dev(self, src: PyneSeries | np.ndarray, period: int) -> PyneSeries | np.ndarray:
        """Mean absolute deviation from SMA.

        Pine equivalent: ``ta.dev(close, 20)``.
        """
        source = to_numpy(src, dtype=np.float64)
        _, result = _rolling_mean_and_mad(source, period)
        return wrap_like(result, src)

    def percentile_nearest_rank(
        self,
        src: PyneSeries | np.ndarray,
        period: int,
        percentage: float,
    ) -> PyneSeries | np.ndarray:
        """Rolling percentile using nearest-rank selection.

        Pine equivalent: ``ta.percentile_nearest_rank(source, length, percentage)``.
        """
        source = to_numpy(src, dtype=np.float64)
        result = _rolling_percentile_values(
            source,
            period,
            percentage,
            linear=False,
        )
        return wrap_like(result, src)

    def percentile_linear_interpolation(
        self,
        src: PyneSeries | np.ndarray,
        period: int,
        percentage: float,
    ) -> PyneSeries | np.ndarray:
        """Rolling percentile using linear interpolation.

        Pine equivalent: ``ta.percentile_linear_interpolation(source, length, percentage)``.
        """
        source = to_numpy(src, dtype=np.float64)
        result = _rolling_percentile_values(
            source,
            period,
            percentage,
            linear=True,
        )
        return wrap_like(result, src)

    def keltner(
        self,
        period: int = 20,
        mult: float = 1.5,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
    ) -> tuple[PyneSeries | np.ndarray, PyneSeries | np.ndarray, PyneSeries | np.ndarray]:
        """Keltner Channel.

        Returns:
            Tuple of (upper, middle, lower) arrays.
        """
        if close is None:
            if self._ctx is None:
                raise RuntimeError("ta.keltner() needs OHLC data")
            close = self._ctx.close

        middle = self.ema(close, period)
        atr_val = self.atr(period, high, low, close)
        upper = middle + mult * atr_val
        lower = middle - mult * atr_val
        return upper, middle, lower

    def donchian(
        self,
        period: int = 20,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
    ) -> tuple[PyneSeries | np.ndarray, PyneSeries | np.ndarray, PyneSeries | np.ndarray]:
        """Donchian Channel.

        Returns:
            Tuple of (upper, middle, lower) arrays.
        """
        if high is None:
            if self._ctx is None:
                raise RuntimeError("ta.donchian() needs high/low data")
            high = self._ctx.high
        if low is None:
            low = self._ctx.low

        upper = utils.highest(high, period)
        lower = utils.lowest(low, period)
        middle = (upper + lower) / 2.0
        return upper, middle, lower

    # ═══════════════════════════════════════════════════════════
    #  Volume
    # ═══════════════════════════════════════════════════════════

    def obv(
        self,
        close: PyneSeries | np.ndarray | None = None,
        volume: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """On-Balance Volume.

        Pine equivalent: ``ta.obv``
        """
        if close is None:
            if self._ctx is None:
                raise RuntimeError("ta.obv() needs close/volume data")
            close = self._ctx.close
        if volume is None:
            volume = self._ctx.volume

        close_arr = to_numpy(close, dtype=np.float64)
        volume_arr = to_numpy(volume, dtype=np.float64)
        n = len(close_arr)
        result = np.zeros(n)
        for i in range(1, n):
            if close_arr[i] > close_arr[i - 1]:
                result[i] = result[i - 1] + volume_arr[i]
            elif close_arr[i] < close_arr[i - 1]:
                result[i] = result[i - 1] - volume_arr[i]
            else:
                result[i] = result[i - 1]
        return wrap_like(result, close, volume)

    def volume_sma(
        self,
        volume: PyneSeries | np.ndarray | None = None,
        period: int = 20,
    ) -> PyneSeries | np.ndarray:
        """Volume Simple Moving Average."""
        if volume is None:
            if self._ctx is None:
                raise RuntimeError("ta.volume_sma() needs volume data")
            volume = self._ctx.volume
        return self.sma(volume, period)

    def mfi(
        self,
        source: PyneSeries | np.ndarray | int | None = None,
        period: int = 14,
        *,
        volume: PyneSeries | np.ndarray | None = None,
        high: PyneSeries | np.ndarray | None = None,
        low: PyneSeries | np.ndarray | None = None,
        close: PyneSeries | np.ndarray | None = None,
    ) -> PyneSeries | np.ndarray:
        """Money Flow Index.

        Pine equivalent: ``ta.mfi(source, length)``.
        """
        if isinstance(source, int):
            period = source
            source = None
        if source is None:
            if high is None:
                if self._ctx is None:
                    raise RuntimeError("ta.mfi() needs a source series and volume data")
                high = self._ctx.high
            if low is None:
                low = self._ctx.low
            if close is None:
                close = self._ctx.close
            source = (
                to_numpy(high, dtype=np.float64)
                + to_numpy(low, dtype=np.float64)
                + to_numpy(close, dtype=np.float64)
            ) / 3.0
        if volume is None:
            if self._ctx is None:
                raise RuntimeError("ta.mfi() needs volume data")
            volume = self._ctx.volume

        source_arr = to_numpy(source, dtype=np.float64)
        volume_arr = to_numpy(volume, dtype=np.float64)
        raw_mf = source_arr * volume_arr

        pos_mf = np.where(utils.change(source_arr, 1) > 0, raw_mf, 0.0)
        neg_mf = np.where(utils.change(source_arr, 1) < 0, raw_mf, 0.0)
        pos_mf[0] = 0
        neg_mf[0] = 0

        pos_sum = utils.sum_(pos_mf, period)
        neg_sum = utils.sum_(neg_mf, period)

        with np.errstate(divide="ignore", invalid="ignore"):
            mfi_val = np.where(
                (~np.isnan(neg_sum)) & (neg_sum != 0),
                100.0 - 100.0 / (1.0 + pos_sum / neg_sum),
                100.0,
            )
        return wrap_like(mfi_val, source, volume)

    # ═══════════════════════════════════════════════════════════
    #  Proxy methods for utils (so ta.crossover works)
    # ═══════════════════════════════════════════════════════════

    crossover = staticmethod(utils.crossover)
    cross = staticmethod(utils.cross)
    crossunder = staticmethod(utils.crossunder)
    highest = staticmethod(utils.highest)
    lowest = staticmethod(utils.lowest)
    highestbars = staticmethod(utils.highestbars)
    lowestbars = staticmethod(utils.lowestbars)
    change = staticmethod(utils.change)
    roc = staticmethod(utils.roc)
    barssince = staticmethod(utils.barssince)
    valuewhen = staticmethod(utils.valuewhen)
    pivothigh = staticmethod(utils.pivothigh)
    pivotlow = staticmethod(utils.pivotlow)
    cum = staticmethod(utils.cum)
    rising = staticmethod(utils.rising)
    falling = staticmethod(utils.falling)
    shift = staticmethod(utils.shift)
    nz = staticmethod(utils.nz)


def _ema_skip_leading_na(src: np.ndarray, period: int) -> np.ndarray:
    """EMA helper that starts after the first complete non-NaN window."""
    source = np.asarray(src, dtype=np.float64)
    n = len(source)
    result = np.full(n, np.nan)
    if period <= 0 or period > n:
        return result

    valid_counts = _window_sums((~np.isnan(source)).astype(np.int64), period)
    complete_windows = np.flatnonzero(valid_counts == period)
    if len(complete_windows) == 0:
        return result

    start = int(complete_windows[0])
    seed_index = start + period - 1
    result[seed_index] = float(np.mean(source[start : seed_index + 1]))
    k = 2.0 / (period + 1)
    for idx in range(seed_index + 1, n):
        value = source[idx]
        if np.isnan(value):
            result[idx] = result[idx - 1]
        else:
            result[idx] = value * k + result[idx - 1] * (1 - k)

    return result
