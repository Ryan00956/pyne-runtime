# Quality Gates

Pyne Runtime is intended to be developed and tested as an independent package.

## Local Setup

From the repository root:

```bash
python -m pip install -e .[dev]
```

## Required Checks

Run these before committing package changes:

```bash
python -m ruff check .
python -m pytest tests/test_architecture.py -q
python -m pytest
python scripts/strategy_capture_scaffold.py --check
python scripts/strategy_capture_diff.py
```

## Architecture Checks

Architecture guard tests live in `tests/test_architecture.py`. Run them directly when
moving modules or changing public package exports:

```bash
python -m pytest tests/test_architecture.py -q
```

These checks verify that:

- every name in `pyne_runtime.__all__` is importable;
- core package modules do not import host application modules such as `app` or
  `candlescope`;
- the internal `pyne_runtime` import graph has no static cycles;
- unusually large modules emit a warning for architecture review without failing
  the test suite.

Golden-style semantic fixtures live under `tests/golden/` and are exercised by
the normal pytest suite. Add or update a fixture when a Pine-like compatibility
claim depends on exact alignment or replay output, especially for
`request.security` gaps/lookahead alignment, lower-timeframe grouping, strategy
fills, and barstate flags.

The strategy capture gates protect the TradingView external-evidence workflow:
`strategy_capture_scaffold.py --check` ensures every strategy pine-equivalent
case keeps an `external_capture` contract, and `strategy_capture_diff.py` fails
when any `captured` TradingView plot sequence diverges from current Pyne output.

From the package root, the full package check also verifies build metadata:

```bash
scripts/check.ps1
```

On POSIX shells:

```bash
scripts/check.sh
```

The build output is written to a temporary directory, so the package tree stays clean.

## Independence Check

Package code must not import CandleScope application modules. The architecture
tests enforce this with AST scanning. For a quick manual check, this should
return no matches:

```bash
Select-String -Path src/pyne_runtime/*.py -Pattern 'from app\.|import app\.|app\.'
```

## Release Readiness

A release candidate is ready only when:

- package tests pass in a clean virtual environment;
- CLI smoke tests pass with `pyne run`, `pyne validate`, `pyne schema`, and `pyne --version`;
- `python -m build` creates both wheel and source distribution;
- `python -m twine check` passes for built artifacts;
- documentation and changelog reflect public API changes.
