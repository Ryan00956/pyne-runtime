"""Request error types."""
from __future__ import annotations


class PyneRequestError(Exception):
    """Stable runtime error raised by host-backed request helpers."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "PYNE_UNSUPPORTED_FEATURE",
        category: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.category = category


class PyneInvalidSymbolError(Exception):
    """Provider-side signal for Pine-like invalid symbol handling."""
