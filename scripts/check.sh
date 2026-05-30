#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ -z "${PYTHON:-}" ]; then
  if [ -x "$ROOT/.venv/bin/python" ]; then
    PYTHON="$ROOT/.venv/bin/python"
  elif [ -f "$ROOT/.venv/Scripts/python.exe" ]; then
    PYTHON="$ROOT/.venv/Scripts/python.exe"
  else
    PYTHON="python"
  fi
fi
DIST="${TMPDIR:-/tmp}/pyne-runtime-dist-check"

cd "$ROOT"
"$PYTHON" -m ruff check .
"$PYTHON" -m pytest
"$PYTHON" scripts/strategy_capture_scaffold.py --check
"$PYTHON" scripts/strategy_capture_diff.py --assertion parity
rm -rf "$DIST"
"$PYTHON" -m build --outdir "$DIST"
"$PYTHON" -m twine check "$DIST"/*
