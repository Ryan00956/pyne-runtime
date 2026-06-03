# Examples

These scripts are packaged examples that run against `sample_ohlcv.csv`. They
double as smoke fixtures for release checks and as small host-integration
references.

Run one example from the repository root:

```bash
pyne run examples/ma_cross.py --ohlcv examples/sample_ohlcv.csv --out result.json
```

Validate one example:

```bash
pyne validate examples/ma_cross.py
```

## Script Examples

| File | Focus |
| --- | --- |
| `bollinger.py` | Bollinger Bands with line plots and fill output. |
| `collection_history.py` | Incremental array, map, and matrix history snapshots. |
| `host_output_contract.py` | Representative host renderer output contract payload. |
| `macd.py` | MACD lines and histogram output. |
| `ma_cross.py` | Moving-average crossover markers. |
| `param_schema_indicator.py` | Complete input metadata and parameter schema output. |
| `pine_like_semantics.py` | Series history, `when()`, `var()`, drawing objects, and strategy events. |
| `rsi_signals.py` | RSI threshold lines and signal markers. |
| `supertrend.py` | Supertrend line and direction markers. |

## Data Fixture

`sample_ohlcv.csv` is the shared OHLCV fixture for CLI examples, documentation,
and package smoke tests. Keep it small enough for quick release gates.
