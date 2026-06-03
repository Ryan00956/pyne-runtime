# Pyne Runtime Documentation

Pyne Runtime is a Pine-like Python package for deterministic indicator,
strategy, request, and host-renderer output workflows.

## Start Here

- [Quickstart](quickstart.md): install the package and run the first script.
- [First Indicator](tutorials/first_indicator.md): write and run a basic
  indicator.
- [Pine-to-Pyne Cookbook](tutorials/pine_to_pyne_cookbook.md): migrate common
  Pine patterns to Python syntax.
- [CSV to Signal](tutorials/csv_to_signal.md): produce structured signal
  output from OHLCV CSV data.

## Host Integration

- [Host Integration Guide](tutorials/host_integration_guide.md): embed Pyne in
  an application with parameter UI, request providers, structured output, and
  release checks.
- [Runtime API](api/runtime.md): choose `pn.run()` or `PyneRuntime`.
- [Settings API](api/settings.md): configure execution, security, metadata, and
  provider behavior.
- [Request API](api/request.md): implement typed host data providers for
  `request.security()` and `request.security_lower_tf()`.
- [Input API](api/input.md): expose script parameters to host UI panels.
- [Output Schema](reference/output_schema.md): consume renderer, object,
  signal, strategy, and error output.
- [Schema Migrations](reference/schema_migrations.md): branch on schema
  versions and follow breaking-change rules.

## API Reference

- [Public API](api/public_api.md): stable package-root imports.
- [Top-Level Script API](api/top_level.md): names injected into scripts.
- [Plot API](api/plot.md): lines, histograms, markers, colors, and drawing
  objects.
- [Strategy API](api/strategy.md): deterministic strategy event and report
  helpers.
- [TA API](api/ta.md): technical-analysis namespace.
- [Collections API](api/collections.md): array, map, and matrix helpers.
- [Result API](api/result.md): inspect `PyneResult` outputs.
- [CLI Reference](reference/cli.md): use `pyne run`, `pyne validate`,
  `pyne schema`, and `python -m pyne_runtime`.

## Concepts

- [Data Model](concepts/data_model.md): OHLCV rows and runtime data context.
- [Series Semantics](concepts/series_semantics.md): Pine-like series and
  history references.
- [Expression Helpers](concepts/expression_helpers.md): `when()`, `where()`,
  and `switch()`.
- [State Semantics](concepts/state_semantics.md): `var()` and explicit state
  cells.
- [Bar Execution Model](concepts/bar_execution_model.md): bar index, time,
  barstate, and strategy fill timing.
- [Incremental Runtime](concepts/incremental_runtime.md): confirmed and preview
  bar execution.
- [Security Modes](concepts/security_modes.md): script execution boundaries.

## Compatibility And Development

- [Pine-Like API Matrix](reference/pine_like_api_matrix.md): supported,
  partial, and known-difference status by feature family.
- [Compatibility](reference/compatibility.md): package and schema stability
  policy.
- [Release Process](reference/release_process.md): semver policy, release
  checklist, and changelog rules.
- [Error Codes](reference/error_codes.md): structured diagnostic codes.
- [Quality Gates](development/quality_gates.md): local and release validation
  commands.
- [Python Package Long-Term Direction](development/python_package_long_term_plan_zh.md):
  roadmap for package maturity.
