# Pyne Python 包长期计划

本文档定义 Pyne 作为 Python 包的长期路线。核心边界很明确：

- Pyne 不做 TradingView Pine Script 源码编译器。
- Pyne 不做 Pine 解释器。
- Pyne 不承诺直接运行 `.pine` 脚本。
- Pyne 的目标是让用户用 Python 语法写出尽量接近 Pine 逻辑模型的指标、策略和运行时对象。

换句话说，Pyne 的产品形态不是：

```text
Pine source -> parser/compiler/interpreter -> execution
```

而是：

```text
Python script + Pine-like runtime API -> deterministic chart/strategy output
```

## 1. 产品定位

Pyne 应该是一个 Python-native 的 Pine-like runtime package。

它服务三类用户：

1. 想在 Python 里使用 Pine-like series、bar、plot、request、strategy 语义的脚本作者。
2. 需要稳定指标和策略运行时的宿主应用。
3. CandleScope 这类图表工作台，用 Pyne 执行用户脚本并渲染结构化输出。

Pyne 不需要和 Python 自身竞争。如果用户只想写普通数组、pandas、循环或自定义回测，他们可以直接写 Python。Pyne 存在的价值，是把 Pine 的心智模型带进 Python：

- `close[1]` 表示上一根 bar。
- series 表达式按 bar 传播。
- `barstate.*` 存在。
- `request.security()` 负责跨上下文对齐。
- `strategy.*` 记录确定性的订单、成交和持仓演化。
- plot 和 drawing object 输出为宿主可渲染的数据结构。

## 2. 明确不做什么

这些能力不属于 Pyne Python 包路线：

- Pine 源码 parser。
- Pine AST。
- Pine bytecode 或 compiler。
- 完整 TradingView runtime clone。
- 未翻译地直接运行用户复制来的 Pine 脚本。
- 保证 TradingView 未公开细节的完全一致。
- 在 core package 内置市场数据存储、交易所 adapter 或 broker connector。
- 做完整真实券商撮合模拟器。

未来可以有独立项目把 Pine 源码翻译成 Pyne-style Python，但它不应该反向绑架 Pyne core 的架构。

## 3. 设计原则

### 3.1 Pine-like 语义优先

如果一个 API 可以做成普通 Python 回测库风格，也可以做成 Pine-like 风格，默认选择 Pine-like。

例如：

```python
strategy(
    "System",
    slippage=2,
    commission_type=strategy.commission.percent,
    commission_value=0.1,
)
```

这种形式比 `slippage_price=...` 更好，因为它保留了 Pine 用户熟悉的心智模型。Python 用户如果不需要这种模型，本来就可以直接写普通 Python。

### 3.2 Python 语法保持 Python 语法

Pyne 不应该假装 Python 可以表达所有 Pine 语法。

只能近似或显式替代的典型点：

- Python `if` 不能对 series 条件逐 bar 分支。
- Python 三元表达式不能变成 series-aware。
- Pine `:=` 不能在 Python 中复刻为语法。
- Pine `varip` 这类声明模式需要显式 Python API。

Pyne 应该给这些限制提供一等公民的替代 API：

```python
body = when(close > open, close - open, open - close)
state = pyne.var("state", 0)
```

### 3.3 宿主边界保持干净

Pyne 负责运行时语义。宿主负责：

- 市场数据获取
- symbol metadata
- chart rendering
- 用户、会话、权限
- 持久化
- broker connectivity

Pyne core 暴露 provider protocol 和结构化输出，不变成数据平台。

### 3.4 每个兼容性说法都要有证据

只要文档说某个行为是 Pine-like，就应该有自动化测试支撑。

高风险区域优先做 golden tests：

- TA 函数
- `request.security` 对齐
- barstate realtime 行为
- strategy fill 和 trade ledger

## 4. 当前基础

当前 Pyne 已经具备比较完整的底座：

- `PyneSeries` 和 `close[1]` 这类历史引用。
- series arithmetic、comparison、boolean composition。
- callable `na` 和 series-aware `nz`。
- `when()`、`switch()` 用于绕开 Python 语法限制。
- `bar_index`、`last_bar_index`、`time`、`time_close`、`barstate.*`。
- incremental `ctx.bar_index`、`bar.bar_index`、`ctx.barstate.*`。
- `var()`、`pyne.var()` 和持久状态 cell。
- core 和 expanded `ta.*`。
- drawing objects：line、label、box、table。
- host-backed `request.security()`，支持 callable expression thunk 和 tuple return。
- `strategy(...)` 声明。
- strategy entry/order/exit/close/cancel/OCA/pyramiding/slippage/commission。
- CLI 和 package quality gates。

所以后续工作不是推倒重来，而是继续把语义深度、API 覆盖、测试证据和宿主协议做扎实。

## 5. 长期工作流

### 5.1 Runtime Metadata：`syminfo`、`timeframe`、`session`

目标：提供 Pine-like 的运行时元数据对象。

为什么优先级高：

- strategy slippage 需要 `mintick`。
- request 对齐需要 timeframe 信息。
- session-aware 指标需要交易时段信息。
- symbol-specific formatting 需要 currency、pointvalue 等元数据。

目标 API：

```python
strategy("System", slippage=2)

plot(syminfo.mintick, "Min Tick")
plot(timeframe.multiplier, "TF Multiplier")
marker(session.ismarket, text="Market")
```

工作项：

1. 给 `PyneSettings` 或执行输入增加 metadata 字段。
2. 增加 `syminfo` namespace：
   - `ticker`
   - `tickerid`
   - `prefix`
   - `currency`
   - `basecurrency`
   - `mintick`
   - `pointvalue`
   - `type`
3. 增加 `timeframe` namespace：
   - `period`
   - `multiplier`
   - `isintraday`
   - `isdaily`
   - `isweekly`
   - `ismonthly`
4. 增加轻量 `session` namespace：
   - `ismarket`
   - `isfirstbar`
   - `islastbar`
5. `strategy(..., slippage=...)` 在未显式传 `mintick` 时使用 `syminfo.mintick`。
6. 文档写清宿主必须提供哪些 metadata，以及缺省值是什么。

完成标准：

- 脚本可以读取 `syminfo.*` 和 `timeframe.*`。
- strategy slippage 有 metadata-backed mintick 路径。
- 缺失 metadata 时行为确定，并且有文档。

### 5.2 Request 语义扩展

目标：让 host-backed 多上下文请求更完整、更可预测。

目标 API：

```python
higher_close = request.security("BTCUSDT", "1h", lambda ctx: ctx.close)
lower_values = request.security_lower_tf("BTCUSDT", "1m", lambda ctx: ctx.close)
```

工作项：

1. 加强 timeframe parse 和比较。
2. 给 provider 增加 capability metadata。
3. 实现 `request.security_lower_tf()`，返回适合 lower-timeframe array 语义的数据结构。
4. 扩展 gaps/lookahead 测试。
5. 从 provider response 注入 symbol metadata。
6. 对 unsupported provider capability 给出结构化错误。

完成标准：

- higher-timeframe 和 lower-timeframe request 有分开的文档语义。
- host provider 可以声明能力。
- 对齐逻辑有 golden-style tests。

### 5.3 Strategy Replay 深化

目标：保持 Pine-like，但定位为 deterministic replay layer，而不是完整真实 broker simulator。

已具备：

- `strategy(...)`
- `entry`、`order`、`exit`、`close`、`close_all`
- `cancel`、`cancel_all`
- pending stop/limit triggers
- OCA cancel/reduce
- pyramiding
- partial exits
- slippage 和 commission
- position size 和 average price

剩余工作：

1. 资本与权益字段：
   - `initial_capital`
   - `currency`
   - `strategy.equity`
   - `strategy.netprofit`
   - `strategy.openprofit`
   - `strategy.grossprofit`
   - `strategy.grossloss`
2. trade ledgers：
   - `strategy.closedtrades`
   - `strategy.opentrades`
   - entry/exit time、price、size、profit
3. risk namespace：
   - `strategy.risk.max_drawdown`
   - `strategy.risk.max_intraday_loss`
   - `strategy.risk.allow_entry_in`
4. margin 语义：
   - `margin_long`
   - `margin_short`
5. fill assumptions：
   - 当前 deterministic high/low scan。
   - 可选 open/high/low/close path policy。
   - 明确 same-bar ambiguity 规则。

完成标准：

- 常见 Pine strategy report 可以从输出推导。
- strategy output 区分 orders、fills、positions、open trades、closed trades。
- intrabar 假设明确并有测试。

### 5.4 Drawing 和 Visual Output 完整性

目标：扩展 Pine 视觉 API 词汇，同时保持 host-renderable。

工作项：

1. 增加 Pine-like namespaces 和 constants：
   - `plot.style_*`
   - `shape.*`
   - `location.*`
   - `size.*`
   - `display.*`
   - `position.*`
2. 增加 API：
   - `plotshape`
   - `plotchar`
   - `plotarrow`
   - 更完整的 `plot()` style
3. 增加 incremental object event stream：
   - create
   - update
   - delete
4. batch 模式继续保留 final snapshot。

完成标准：

- Pine-style visual scripts 不需要滥用 generic marker 输出。
- 宿主可以选择 snapshot rendering 或 event-stream rendering。

### 5.5 Pine-like Collections

目标：用 Python API 提供 Pine-like collection 语义，而不是实现 Pine collection 语法。

目标 API：

```python
arr = array.new_float()
array.push(arr, close)
last = array.get(arr, array.size(arr) - 1)
```

工作项：

1. 增加 `array` namespace。
2. 增加 `map` namespace。
3. 增加 `matrix` namespace。
4. 定义可存储值：
   - scalar
   - series
   - drawing object handle
5. 增加 safe-mode limits，避免无限内存增长。

完成标准：

- 常见 Pine array/map/matrix 示例能用 Python 调用表达。
- safe mode 可以限制内存风险。

### 5.6 Standard Library Width

目标：继续扩展脚本作者常用的 Pine-like namespace。

优先级：

1. `str.*`
2. `math.*`
3. `time.*`
4. `ticker.*`
5. `ta.*` edge functions
6. `color.*` completeness

工作项：

1. 维护 API coverage matrix。
2. 函数级测试。
3. 按 namespace 写文档。
4. 明确 known differences。

完成标准：

- 用户能按 namespace 发现支持情况。
- 缺失函数有 planned 或 unsupported 状态。

### 5.7 Realtime 和 Incremental Convergence

目标：让 batch execution 和 incremental execution 在语义上收敛。

工作项：

1. 为部分脚本定义 reference bar-by-bar evaluator。
2. 对比 batch result 和 incremental replay result。
3. 增加 incremental object events。
4. 如果可行，增加显式 `varip`-like API。
5. 改进 strategy events 在 preview/confirmed 下的行为。

完成标准：

- 同一脚本可以同时验证 batch 和 incremental 结果。
- preview updates 被隔离，confirmed bars 确定提交。

### 5.8 Error Model 和 Developer Experience

目标：让 Pyne 作为 Python 包更好用、更好调试。

工作项：

1. 优化 series truthiness 错误：
   - `if close > open`
   - Python ternary with series
2. 对 unsupported Pine-like API 给出诊断。
3. 增强 `pn.validate()` 输出。
4. 补齐 typed public API hints。
5. 增加示例：
   - indicator
   - strategy
   - request provider
   - incremental session
6. README 增加 recipe。

完成标准：

- 新用户能快速理解 Python 语法限制。
- 常见错误能给出可执行建议。

### 5.9 Golden Tests 和兼容性证据

目标：从 best effort 走向 evidence-backed compatibility。

工作项：

1. 创建 `tests/golden/`。
2. 为这些领域增加 deterministic fixtures：
   - TA functions
   - `request.security` alignment
   - strategy fills
   - barstate flags
3. expected outputs 存为 JSON/CSV。
4. 文档标明每个 golden 的来源：
   - derived from Pine behavior
   - derived from Pyne-defined behavior
   - host-defined behavior

完成标准：

- 兼容性声明可以指向具体 fixture。
- API 越扩越大时，回归风险仍可控。

### 5.10 Packaging、Versioning 和 Host Contracts

目标：让宿主应用可以稳定依赖 Pyne。

工作项：

1. 定义 semantic versioning 规则。
2. 给 output schema 做版本化。
3. 写 provider protocol docs：
   - OHLCV provider
   - symbol metadata provider
   - request capability provider
4. 写 breaking changes migration notes。
5. 保持 `scripts/check.ps1` 和 `scripts/check.sh` 作为 release gates。

完成标准：

- 宿主应用可以有计划地升级 Pyne。
- output schema 变化显式可追踪。

## 6. 推荐里程碑

### Milestone A：Metadata 和 Runtime Context

范围：

- `syminfo`
- `timeframe`
- session basics
- strategy slippage defaulting to `syminfo.mintick`

为什么先做：

它能同时加强 strategy、request 和 plotting 的语义基础。

### Milestone B：Strategy Reporting

范围：

- equity
- netprofit
- openprofit
- closed trades
- open trades

为什么第二：

订单生命周期已经有基础，下一层最有价值的是报告和 ledger。

### Milestone C：Request Lower Timeframe

范围：

- `request.security_lower_tf`
- provider capability metadata
- alignment goldens

为什么第三：

这是 Pine 用户很常见的工作流，而且会影响 provider contract。

### Milestone D：Visual API Completion

范围：

- `plotshape`
- `plotchar`
- `plotarrow`
- constants namespaces
- incremental object events

为什么第四：

它提升图表表达能力，但不需要改变 core execution model。

### Milestone E：Collections 和 Standard Library Width

范围：

- `array`
- `map`
- `matrix`
- `str`
- additional `math` and `ta`

为什么第五：

等 core runtime 更稳定后，再扩脚本 API 面更稳。

### Milestone F：Golden Compatibility Suite

范围：

- fixture framework
- compatibility report
- documented known differences

为什么第六：

Pyne 的 surface area 到这个阶段会很大，需要用证据维护兼容性说法。

### Milestone G：1.0 Hardening

范围：

- public API freeze
- output schema versioning
- provider protocol freeze
- migration guide
- release checklist

为什么最后：

1.0 的核心不是再加功能，而是让宿主和用户相信升级不会随意破坏行为。

## 7. 每个里程碑的完成标准

每个里程碑都必须同时完成：

1. runtime/API 实现。
2. 单元测试和必要的 golden tests。
3. `docs/reference/pine_like_api_matrix.md` 更新。
4. 对应 API 文档或概念文档更新。
5. 示例脚本能运行。
6. `scripts/check.ps1` 或 `scripts/check.sh` 通过。

没有测试和文档的功能，不应该算完成。

## 8. 近期下一步

下一步最适合做：

```text
Runtime metadata: syminfo + timeframe
```

最小目标：

```python
strategy("Meta Strategy", slippage=2)
plot(syminfo.mintick, "Min Tick")
plot(timeframe.multiplier, "Timeframe Multiplier")
```

必需行为：

- `syminfo.mintick` 默认是 `1.0`。
- `strategy(..., slippage=2)` 在没有显式 `mintick` 时使用 `syminfo.mintick`。
- `timeframe.period` 可读。
- `timeframe.multiplier` 能解析 `"1"`、`"5"`、`"1h"`、`"1D"` 这类常见值。
- 文档说明 metadata 由宿主提供。
- 测试覆盖默认 metadata 和显式 metadata。

这个切片不会把 Pyne 推向编译器或解释器方向，但会明显增强它作为 Python package 的 Pine-like 运行时基础。
