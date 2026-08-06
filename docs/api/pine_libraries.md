# External Pine libraries

Pyne does not download or execute arbitrary Pine libraries. Each supported
dependency is a pinned, reviewed Python adapter and unknown identifiers fail
closed with `PYNE_UNSUPPORTED_FEATURE`.

The current registry exposes one project-required adapter:

```python
tv_ta = pine_library("TradingView/ta/10")
up, down, delta = tv_ta.requestUpAndDownVolume("1")
opening, high, low, current = tv_ta.requestVolumeDelta("1", "1D")
```

The pinned adapter is currently a batch-runtime surface. It exposes `cagr()`,
`changePercent()`, `highestSince()`,
`lowestSince()`, `requestUpAndDownVolume()`, and `requestVolumeDelta()`.

The two volume functions require a host data provider with
`request.security_lower_tf` capability. It categorizes each authoritative
intrabar by comparing its close with its open, returns positive up volume,
negative down volume, and their net delta for every chart bar. Flat intrabars
use the previous valid intrabar close to determine polarity.
`requestVolumeDelta()` additionally accumulates delta within the requested
period and returns opening, highest, lowest, and current CVD values. Empty
intrabar groups remain `na`; the runtime never estimates them from chart OHLCV.

`cagr()` returns `na` until the exit time is reached and for spans shorter than
one day. The pure series members do not require a provider.

Host code can inspect `pn.SUPPORTED_PINE_LIBRARIES`. Adding another adapter
requires a pinned library identifier, an explicit member allowlist, semantic
tests, and declared data requirements.
