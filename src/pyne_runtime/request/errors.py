"""Request error types."""
from __future__ import annotations


class PyneRequestError(Exception):
    """Stable runtime error raised by host-backed request helpers."""

    def __init__(self, message: str, *, code: str = "PYNE_UNSUPPORTED_FEATURE") -> None:
        super().__init__(message)
        self.code = code


class PyneInvalidSymbolError(Exception):
    """Provider-side signal for Pine-like invalid symbol handling."""
