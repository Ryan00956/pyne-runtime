# TradingView Strategy Capture 执行说明

本文记录 strategy pine-equivalent fixture 从 Pyne-defined 预期推进到真实
TradingView 导出序列的执行方式。Pyne 仍然不运行 Pine 源码；这里的目标是把
TradingView 导出的 plot 序列作为外部证据接入现有 golden runner。

## Fixture 字段

每个 strategy pine-equivalent case 可以加入可选字段：

```json
{
  "external_capture": {
    "provider": "tradingview",
    "status": "captured",
    "tolerance": 1e-9,
    "values": {
      "Position": [2.0, 2.0, 0.0],
      "Net Profit": [0.0, 0.0, 6.0]
    }
  }
}
```

- `provider` 固定为 `tradingview`。
- `status` 为 `not_captured` 时只记录 scaffold 已存在，不能包含 `values`。
- `status` 为 `captured` 时，`values` 会参与测试断言。
- `tolerance` 是可选绝对误差，默认 `0.0`。
- `values` 的 key 必须对应 fixture 脚本里的 `plot(..., "Title")` 标题。

## 导出流程

1. 从 fixture 复制 `pine_equivalent` 脚本到 TradingView Pine Editor。
2. 使用与 fixture `bars` 完全一致的数据窗口或导入数据源。
3. 导出 plot 数据，只保留 fixture 已声明的 plot 标题。
4. 将导出的序列填入 `external_capture.values`。
5. 将 `status` 从 `not_captured` 改为 `captured`。
6. 运行 `python -m pytest tests/test_golden_strategy.py -q`。

## 优先顺序

优先替换这些已经稳定的 scaffold：

1. `strategy_pine_equivalent_smoke.json`
2. `strategy_pine_equivalent_bracket_exit.json`
3. `strategy_pine_equivalent_cost_allocation.json`
4. `strategy_pine_equivalent_reversal_pyramiding.json`
5. `strategy_pine_equivalent_margin_order_cancel.json`

## 注意事项

- 不要用 Pyne 输出填充 `external_capture.values`。
- 如果 TradingView 导出存在时间戳列，先按 bar 顺序对齐后只写数值序列。
- 如果 TradingView 空值导出为空字符串，应按 fixture 需要转成 `null` 或保留未捕获状态。
- 若外部导出与 Pyne-defined baseline 不一致，先保留差异并新增说明，不要直接覆盖 Pyne baseline。
