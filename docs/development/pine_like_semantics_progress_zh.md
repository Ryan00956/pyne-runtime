# Pine-like 语义阶段进度

本文记录 Pyne 作为 Python 包时，向 Pine 运行时语义靠近的当前进度、
剩余差距和下一步执行顺序。它不是编译器或解释器计划；Pyne 不直接运行
TradingView Pine 源码，而是在 Python API 层提供尽量接近 Pine 的数据、
执行、绘图、请求和策略语义。

## 边界

- Pyne 是 Python 包，不做 Pine 源码解析、编译或解释。
- Python 用户可以直接写 Python 语句；Pyne API 负责承载 Pine-like 的运行时概念。
- Python 语法无法重载的 Pine 表达方式需要显式 API 近似，例如：
  - Pine 三元表达式要用 `when(cond, a, b)`。
  - Pine `if`/`switch` 对 series 分支要用 `when()` 或 `switch()`。
  - Pine `:=` 递归赋值要用 `var()` / `pyne.var()` 状态单元。
  - `request.security()` 的表达式上下文要用 callable thunk，例如 `lambda ctx: ctx.close`。

## 已完成的主要语义

### Series 与执行模型

- `PyneSeries` 支持 Pine-like 历史引用：`close[1]`、`high[2]`。
- `na`、`na(x)`、`nz(x)`、series 算术、比较、布尔组合已经可用。
- `bar_index`、`time`、`time_close`、`barstate.*`、增量执行上下文已经覆盖。
- `syminfo`、`timeframe`、`session` 等运行时元数据可由 host 或 `PyneSettings` 注入。

### 状态与表达式辅助

- `var()`、`pyne.var()`、`set_each()` 覆盖 Pine 的跨 bar 状态模型。
- `when()`、`switch()` 覆盖 Python 语法无法表达的 series 条件选择。
- 顶层内置与运行时上下文已支持 batch 和 incremental 两种口径。

### 集合类型

- `array.*` 核心可变数组语义已可用。
- 支持 `array.new_*()`、`array.from_values()`、`get/set/push/pop/shift/unshift`、
  `insert/remove/clear/copy/slice/fill/reverse/sort`、搜索和数值聚合。
- Python 关键字限制下，Pine 的 `array.from(...)` 对应为
  `array.from_values(...)` / `array.from_list(...)`。
- `map.*` 核心 key/value 语义已可用，包含 `new/from_values/get/put/remove`、
  `contains/keys/values/copy/clear/size`。
- `matrix.*` 核心二维容器语义已可用，包含 `new/from_rows/get/set/row/col`、
  `transpose/reshape/add/sub/mult` 和数值聚合。

### TA 与数据输出

- 常用 `ta.*` 已覆盖：`sma`、`ema`、`rsi`、`macd`、`bb`、`atr` 等。
- 扩展 TA 已覆盖：`alma`、`hma`、`swma`、`dmi`、`sar`、percentiles 等。
- 输出使用稳定 JSON schema，适合宿主图表层渲染。

### 标准库宽度

- `str.*` 高频字符串 helper 已可用。
- 覆盖 `tostring/tonumber/length/substring/pos/contains/startswith/endswith`、
  `replace/replace_all/split/trim/upper/lower/repeat/format`。
- `str` namespace 保持可调用，因此 `str(value)` 仍然可用。
- `ticker.*` 核心 ticker id helper 已可用，覆盖 `new/inherit/modify/standard`
  和 `heikinashi/renko/linebreak/kagi/pointfigure`。
- `time.*` helper 已可用，同时保留 `time` 的 series 行为，覆盖
  `year/month/dayofmonth/dayofweek/hour/minute/second/timestamp/format`。
- `color.*` helper 已扩展，覆盖 `rgb/new/r/g/b/t/when/from_gradient` 和常用颜色常量。

### Plot 与绘图对象

- `plot()`、`hline()`、`fill()`、`marker()`、`bgcolor()`、`barcolor()` 已可用。
- `plotshape()`、`plotchar()`、`plotarrow()` 已可用，并映射到现有 marker 输出协议。
- 已加入 Pine-like enum namespace：
  - `shape.*`
  - `location.*`
  - `size.*`
  - `display.*`
  - `format.*`
  - `scale.*`
  - `xloc.*`
  - `yloc.*`
  - `line.*`、`label.*`、`box.*`、`text.*`、`position.*`
- `indicator(..., format=..., scale=..., precision=...)` 可写入 metadata。
- `label.new(..., yloc=...)`、`label.set_xloc()`、`label.set_yloc()` 已支持。

### Request 多上下文

- `request.security()` 支持 callable thunk、tuple 返回、字段表达式。
- `request.security_lower_tf()` 支持 lower timeframe 分组。
- lower timeframe 返回对象支持 `to_lists()`、`size()`、`first()`、`last()`、
  `get()`、`sum()`、`min()`、`max()`、`avg()` 和 bars-back。
- `barmerge.gaps_*`、`barmerge.lookahead_*` 已加入并校验。
- `ignore_invalid_symbol` 已覆盖 invalid symbol 容错。
- provider capability、provider metadata、requested context cache 已完成。
- 已有 higher timeframe alignment 与 lower timeframe alignment golden fixture。

### Strategy

- `strategy.entry()`、`strategy.order()`、`strategy.exit()`、`strategy.close()`、
  `strategy.close_all()`、`strategy.cancel()`、`strategy.cancel_all()` 已可用。
- `same_bar_fill_priority` 已支持，用于显式控制同一根 bar 同时触及 stop/limit
  时选择 `strategy.same_bar.stop_first` 还是 `strategy.same_bar.limit_first`。
- `strategy.close()` / `strategy.close_when()` 支持 `qty` 和 `qty_percent`。
- `strategy.exit()` 支持 `qty` 和 `qty_percent`，并保持 `qty` 优先。
- 已有 OCA、pyramiding、commission、slippage、limit verification、margin、
  risk rules、closed/open trade ledgers 和 strategy summary。

## 仍然不是 Pine 的地方

这些差异来自 Python 包边界或当前实现阶段，不代表必须做 Pine 编译器：

- 不能直接运行 `.pine` 源码。
- 不能让 Python `if cond:` 对 series 做 Pine 式逐 bar 分支。
- 不能让 Python 原生三元表达式 `a if cond else b` 对 series 做 Pine 式选择。
- 不能捕获 `request.security(symbol, tf, close + open)` 这种裸表达式的 AST 上下文；
  需要 `lambda ctx: ctx.close + ctx.open`。
- Strategy 仍是确定性回放模型，不是完整券商模拟器。
- Drawing output 目前偏最终快照，尚未做完整增量对象事件流。

## 下一阶段优先级

### P1: Plot wrapper 补齐

视觉 enum 基础已经完成，`plotshape()`、`plotchar()` 和 `plotarrow()` 已完成。
后续可继续补齐更细的绘图显示参数，但常见 plot wrapper 已经进入可迁移状态。

它们先映射到现有 `marker()` / plot output schema，不需要改变宿主渲染协议。

### P2: 集合类型

面向 Python 包的 Pine-like 集合 API：

- `array.*` 核心语义已完成；后续可以补历史快照和更细的 Pine 边界行为。
- `map.*` 核心语义已完成。
- `matrix.*` 核心语义已完成。

重点不是模仿 Pine 语法，而是保留 Pine 的可变集合语义、历史引用边界和运行时错误口径。

### P3: 标准库宽度

继续扩展高频 namespace：

- `str.*` 高频 helper 已完成；后续可补更细的时间格式化口径。
- `ticker.*` 核心 helper 已完成。
- 更多 `time.*` 核心 helper 已完成。
- 更完整的 `color.*` 核心 helper 已完成。
- 更多数学与统计 helper

### P4: Strategy 回放语义深化

- same-bar stop/limit 触发顺序策略已明确，默认 `stop_first`，可配置 `limit_first`。
- 扩展 intrabar path policy。
- 增加更细的 fill reason、fill phase 和订单生命周期事件。
- 增加 strategy golden fixtures。

### P5: Golden 与兼容性证据

- TA golden fixtures。
- request edge-case golden fixtures。
- strategy fill golden fixtures。
- batch / incremental parity tests。

## 下一步建议

下一步建议进入 Strategy 回放语义深化，优先补 same-bar stop/limit 触发顺序策略文档和 golden 测试。完成后应同步更新：

- `src/pyne_runtime/strategy.py`
- `tests/test_strategy_runtime.py`
- `docs/api/strategy.md`
- `docs/reference/pine_like_api_matrix.md`

验证门槛保持为完整检查脚本通过。
