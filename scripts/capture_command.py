"""Shell-safe path rendering for generated capture commands."""
from __future__ import annotations

from pathlib import Path


_UNSAFE_DOUBLE_QUOTED_CHARACTERS = ('"', "$", "`", "\n", "\r", "\\")


def quote_command_path(path: Path) -> str:
    """Quote a path for both PowerShell and POSIX-compatible shells."""
    text = path.as_posix()
    if any(character in text for character in _UNSAFE_DOUBLE_QUOTED_CHARACTERS):
        raise ValueError(
            "capture command path cannot be safely double-quoted for "
            "PowerShell/POSIX shells"
        )
    return f'"{text}"'


def render_capture_import_command(
    command: str,
    export_dir: Path,
    export_file: str,
) -> str:
    """Replace a capture-pack placeholder with one quoted full path."""
    marker = f"<export-dir>/{export_file}"
    if marker not in command:
        if "<export-dir>" in command:
            raise ValueError(
                "capture import command has an unsupported <export-dir> placeholder"
            )
        return command
    rendered = command.replace(
        marker,
        quote_command_path(export_dir / export_file),
    )
    if "<export-dir>" in rendered:
        raise ValueError(
            "capture import command has an unsupported <export-dir> placeholder"
        )
    return rendered
