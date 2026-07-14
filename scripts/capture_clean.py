"""Shared destructive-clean guard for TradingView capture output packs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PROTECTED_REPO_DIRS = (
    ".git",
    "docs",
    "examples",
    "scripts",
    "src",
    "tests",
)


def ensure_safe_capture_clean_target(
    out_dir: Path,
    golden_dir: Path,
    *,
    capture_type: str,
) -> bool:
    """Return whether a recognizable non-empty capture pack may be removed."""
    if out_dir.is_symlink():
        _refuse(out_dir, "symbolic-link output directories are not cleanable")
    if not out_dir.is_dir():
        _refuse(out_dir, "output path is not a directory")

    target = out_dir.resolve()
    repo_root = REPO_ROOT.resolve()
    cwd = Path.cwd().resolve()
    home = Path.home().resolve()
    filesystem_root = Path(target.anchor).resolve()

    if target == filesystem_root:
        _refuse(out_dir, "filesystem root is protected")
    if _is_same_or_ancestor(target, repo_root):
        _refuse(out_dir, "repository root and its ancestors are protected")
    if _is_same_or_ancestor(target, cwd):
        _refuse(out_dir, "current working directory and its ancestors are protected")
    if _is_same_or_ancestor(target, home):
        _refuse(out_dir, "home directory and its ancestors are protected")

    protected_dirs = [repo_root / name for name in PROTECTED_REPO_DIRS]
    protected_dirs.append(golden_dir.resolve())
    for protected in protected_dirs:
        if _paths_overlap(target, protected):
            _refuse(out_dir, f"protected directory overlaps target: {protected}")

    children = list(target.iterdir())
    if not children:
        return False
    _validate_capture_manifest(target / "manifest.json", capture_type, out_dir)
    return True


def _validate_capture_manifest(
    manifest_path: Path,
    capture_type: str,
    display_path: Path,
) -> None:
    try:
        manifest: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _refuse(display_path, "non-empty directory has no readable capture manifest")
    if not isinstance(manifest, dict):
        _refuse(display_path, "capture manifest must be a JSON object")
    if manifest.get("capture_type") != capture_type:
        _refuse(
            display_path,
            f"capture manifest is not a {capture_type!r} output pack",
        )
    if not isinstance(manifest.get("entries"), list):
        _refuse(display_path, "capture manifest has no entries list")


def _is_same_or_ancestor(candidate: Path, path: Path) -> bool:
    return candidate == path or candidate in path.parents


def _paths_overlap(first: Path, second: Path) -> bool:
    return (
        first == second
        or first in second.parents
        or second in first.parents
    )


def _refuse(path: Path, reason: str) -> None:
    raise SystemExit(f"refusing to clean protected directory {path}: {reason}")
