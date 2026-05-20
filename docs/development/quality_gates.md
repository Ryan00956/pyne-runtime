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
python -m pytest
```

Golden-style semantic fixtures live under `tests/golden/` and are exercised by
the normal pytest suite. Add or update a fixture when a Pine-like compatibility
claim depends on exact alignment or replay output, especially for
`request.security` gaps/lookahead alignment, lower-timeframe grouping, strategy
fills, and barstate flags.

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

Package code must not import CandleScope application modules. This should return no matches:

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
