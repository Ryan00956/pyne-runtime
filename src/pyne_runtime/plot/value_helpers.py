"""Value normalization helpers shared by plot function factories."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..series import PyneSeries
from ..state import PyneVar
from ..values import is_na_value
from .collector import OutputCollector


class PlotValueAdapter:
    """Normalize batch plot inputs against one output collector."""

    def __init__(self, collector: OutputCollector) -> None:
        self._collector = collector

    def from_data(self, data: PyneSeries | np.ndarray | list | Any) -> list:
        if isinstance(data, PyneVar):
            data = data.get()
        if isinstance(data, PyneSeries):
            return data.to_numpy().tolist()
        if isinstance(data, np.ndarray):
            return data.tolist()
        if isinstance(data, list):
            return data
        if hasattr(data, "to_numpy"):
            return np.asarray(data.to_numpy()).tolist()
        return [data] * len(self._collector.times)

    @staticmethod
    def color_for_index(color_data: Any, idx: int, timestamp: int) -> str | None:
        if color_data is None:
            return None
        if isinstance(color_data, PyneSeries):
            color_data = color_data.to_numpy()
        if isinstance(color_data, np.ndarray):
            if idx < len(color_data):
                return str(color_data[idx])
            return None
        if isinstance(color_data, list):
            if idx >= len(color_data):
                return None
            item = color_data[idx]
            if isinstance(item, dict):
                if item.get("time") == timestamp or "time" not in item:
                    return str(item.get("color")) if item.get("color") else None
                return None
            if is_na_value(item):
                return None
            return str(item) if item else None
        if is_na_value(color_data):
            return None
        return str(color_data) if color_data else None

    @staticmethod
    def is_valid(value: Any) -> bool:
        return not is_na_value(value)

    @staticmethod
    def condition_is_true(value: Any) -> bool:
        return False if is_na_value(value) else bool(value)

    @staticmethod
    def scalar(value: Any) -> Any:
        if isinstance(value, PyneVar):
            value = value.get()
        if isinstance(value, PyneSeries):
            values = value.to_numpy().tolist()
        elif isinstance(value, np.ndarray):
            values = value.tolist()
        elif isinstance(value, list):
            values = value
        else:
            return serialize_scalar(value)

        for item in reversed(values):
            if not is_na_value(item):
                return serialize_scalar(item)
        return None


def serialize_scalar(value: Any) -> Any:
    if is_na_value(value):
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bool | str | int):
        return value
    if isinstance(value, float):
        return round(value, 8)
    return value


def display_options(
    *,
    display: str | None,
    format: str | None,
    precision: int | None,
) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if display is not None:
        options["display"] = str(display)
    if format is not None:
        options["format"] = str(format)
    if precision is not None:
        options["precision"] = int(precision)
    return options
