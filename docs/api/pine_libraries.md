# External Pine libraries

Pyne does not download or execute arbitrary Pine libraries. Each supported
dependency is a pinned, reviewed Python adapter and unknown identifiers fail
closed with `PYNE_UNSUPPORTED_FEATURE`.

The current registry exposes one project-required adapter:

```python
tv_ta = pine_library("TradingView/ta/10")
up, down, delta = tv_ta.requestUpAndDownVolume("1")
```

`requestUpAndDownVolume()` requires a host data provider with
`request.security_lower_tf` capability. It categorizes each authoritative
intrabar by comparing its close with its open, returns positive up volume,
negative down volume, and their net delta for every chart bar. Empty intrabar
groups remain `na`; the runtime never estimates them from chart OHLCV.

Host code can inspect `pn.SUPPORTED_PINE_LIBRARIES`. Adding another adapter
requires a pinned library identifier, an explicit member allowlist, semantic
tests, and declared data requirements.
