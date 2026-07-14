from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "capture_command.py"


def test_quote_command_path_preserves_spaces() -> None:
    module = _load_capture_command()

    assert module.quote_command_path(
        Path("capture packs") / "TA export.csv"
    ) == '"capture packs/TA export.csv"'


def test_render_capture_import_command_quotes_combined_path() -> None:
    module = _load_capture_command()

    rendered = module.render_capture_import_command(
        "python import.py --values <export-dir>/export.csv",
        Path("capture packs"),
        "export.csv",
    )

    assert rendered == 'python import.py --values "capture packs/export.csv"'


@pytest.mark.parametrize("unsafe_character", ['"', "$", "`", "\n", "\r"])
def test_quote_command_path_rejects_shell_unsafe_characters(
    unsafe_character: str,
) -> None:
    module = _load_capture_command()

    with pytest.raises(ValueError, match="cannot be safely double-quoted"):
        module.quote_command_path(Path(f"capture{unsafe_character}pack"))


def test_render_capture_import_command_rejects_unknown_placeholder_shape() -> None:
    module = _load_capture_command()

    with pytest.raises(ValueError, match="unsupported <export-dir> placeholder"):
        module.render_capture_import_command(
            "python import.py --values <export-dir>/different.csv",
            Path("capture packs"),
            "export.csv",
        )


def _load_capture_command() -> ModuleType:
    spec = spec_from_file_location("capture_command", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
