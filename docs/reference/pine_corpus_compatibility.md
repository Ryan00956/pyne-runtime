# Pine Corpus Compatibility Audit

Pyne uses Pine source collections as **compatibility evidence**, not as scripts
to execute or content to bundle. Pyne remains a Pine-like Python runtime:
indicators must be rewritten as Python, and the original Pine source is neither
copied nor interpreted.

Run the aggregate audit against any directory of Pine sources:

```bash
python scripts/pine_corpus_audit.py <corpus-dir> --format markdown
python scripts/pine_corpus_audit.py <corpus-dir> --format json --output report.json
```

The report contains filenames and aggregate feature counts, but never source
text. It reflects the live Pyne namespace instead of maintaining a duplicate
list of implemented APIs. Pine `import` statements are parsed separately, so a
function supplied by a pinned Pine library is not mislabeled as a missing Pyne
core API.

## Reference Corpus Snapshot

The August 2026 compatibility pass used 104 indicator/study files (1,643,207
bytes): Pine v4=20, v5=43, v6=16, and 25 without a version declaration. The
declarations were 60 `indicator()` and 44 `study()` scripts.

After the fourth compatibility slice, the inventory produced:

| Bucket | Features | Files touched |
| --- | ---: | ---: |
| API analogue available | 350 | 104 |
| Core runtime gap | 0 | 0 |
| Imported Pine-library rewrite | 69 | 10 |
| Host-owned gap | 10 | 18 |
| Render-contract gap | 5 | 15 |
| Required syntax or host-policy rewrite | 8 | 30 |

These numbers are **not file pass rates**. “API analogue available” means only
that the referenced Pine concept has a corresponding Pyne API after a Python
rewrite. A file can still require control-flow, state, type, method, import,
session, rendering, or numerical-parity work.

The same corpus contains Pine-only syntax that must be rewritten explicitly:
ternaries in 92 files, `:=` reassignment in 70, function declarations in 62,
loops in 50, type declarations in 25, method declarations in 12, and imports
in 11.

## Closed In The First Slice

- Callable legacy `input(...)`, `input.integer`, and `input.resolution`.
- `input.text_area`, `input.price`, `input.enum`, `display`, and `active`
  parameter metadata.
- `array.new_line`, `array.new_label`, and `array.new_box`.
- `timeframe.in_seconds`, `timeframe.from_seconds`, `timeframe.change`,
  timeframe type flags, and the global `dayofweek` series/constants.
- Legacy `study`, `security`, `pivothigh`, `pivotlow`, `linreg`, `stdev`,
  `stoch`, `tostring`, `cci`, `mfi`, and `mom` spellings.
- `runtime.error`, common label/box getters and setters, box copying, and
  high-frequency enum constants such as `size.auto`, `format.mintick`, and
  `extend.right`.

## Closed In The Second Slice

- Callable `time(...)` with timeframe selection, session/day filters, explicit
  timezones, chart `bars_back`, and target `timeframe_bars_back`.
- IANA, UTC/GMT, numeric-offset, and Pine-style `UTC-5` timezone parsing shared
  by metadata and time helpers.
- `ta.vwap(source)`, explicit anchor resets, standard-deviation bands, and the
  legacy `vwap(source)` spelling.
- CandleScope plugin settings now retain host-configured exchange timezone,
  currency, base currency, tick size, point value, and volume type when binding
  the current market identity.

## Closed In The Third Slice

- `ta.pivot_point_levels()` for Traditional, Fibonacci, Woodie, Classic, DM,
  and Camarilla formulas, including fixed and developing periods, Pine's
  eleven-element order, absent-level `na` values, and the Woodie/developing
  rejection.
- Mutable `chart.point` values with `new`, `now`, `from_index`, `from_time`, and
  `copy`, plus point overloads and setters for lines, labels, and boxes in both
  batch and incremental execution.
- Live, oldest-first `line.all` and `box.all` handle snapshots.
- Output schema v2 closes `table.merge_cells`, `plotcandle`, `linefill`, and
  `polyline` as explicit renderer collections. A v1 host remains a declared
  fallback and must reject v2-only output rather than discard it.

## Closed In The Fourth Slice

- Pine imports now retain their owner, library, pinned version, alias, and used
  member as aggregate dependency evidence. Explicit aliases are inventoried;
  for a default alias that overlaps a built-in namespace, implemented core
  members remain core features while unknown members are attributed to the
  imported library.
- `ta.requestUpAndDownVolume` is attributed to the pinned
  `TradingView/ta/10` library and has an explicit Pyne adapter at
  `pine_library("TradingView/ta/10").requestUpAndDownVolume`. It requires
  authoritative host lower-timeframe OHLCV and never fabricates intrabars.
- `alert.freq_all`, `alert.freq_once_per_bar`, and
  `alert.freq_once_per_bar_close` are classified with `alert(...)` as migration
  boundaries. Pyne emits signal evidence with `emit_signal(...)`; realtime
  repetition, per-bar deduplication, and closed-bar delivery are host alert
  policies, not batch-runtime constants.
- After separating those boundaries, the reference corpus contains no unresolved
  core namespace member. This is an inventory result, not a claim that any Pine
  file runs directly.

## Remaining Boundaries

- Imported libraries: the pinned `TradingView/ta/10` registry now has nine
  explicit members, including the project-used volume adapter. Any other pinned
  member still needs an explicit Python port, a verified Pyne equivalent, or
  removal while converting each indicator. The audit now ranks these unresolved
  library members under `capabilityDemand.externalLibraryCandidates`.
- Incremental TA: the audit ranks batch-covered TA members that remain outside
  the 39-member incremental surface under
  `capabilityDemand.incrementalTaCandidates`. The frozen 104-file corpus currently
  lists only `ta.tsi` (one file). These lists are demand evidence, not automatic
  promotion or source-execution claims; the reviewed ranking is in the
  [capability demand backlog](../development/capability_demand_backlog_zh.md).
- Host state/data: chart theme and visible-range values, corporate actions,
  currency conversion, and automatic authoritative symbol timezone/volume
  type, plus realtime alert scheduling. Pyne accepts timezone and volume-type
  metadata when the host supplies them; it does not infer them from a ticker
  string.
- Python spelling: Pine's `array.from(...)` must be written as
  `array.from_values(...)` because `from` is a Python keyword. Pine ternaries,
  reassignment, object/color type casts, and `alert(...)` calls also require
  explicit Python rewrites (signals use `emit_signal(...)`).

Compatibility work should close these boundaries with semantic tests and host
contracts. It should not turn the corpus into bundled default indicators or
claim direct Pine execution.
