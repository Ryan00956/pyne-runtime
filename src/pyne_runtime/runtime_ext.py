"""Pine-like ``runtime`` namespace helpers."""

from __future__ import annotations

from typing import Any, NoReturn


class RuntimeNamespace:
    """Explicit script-controlled runtime failures."""

    @staticmethod
    def error(message: Any) -> NoReturn:
        """Stop script execution with a host-visible runtime error."""
        raise RuntimeError(str(message))


runtime_namespace = RuntimeNamespace()
