# Structured Market Data Support Design

## 背景

截至 2026-07-01，FinSight V1 已经打通了 `metric_lookup` 的控制面执行链：

- router 能把用户问题识别为 `metric_lookup`
- planner 能生成 `query_structured_data -> synthesize_brief_answer` 短路径
- orchestrator 能真实执行这两步并返回统一 response / trace

当前真正缺失的不是执行链，而是 `structured_data` 能力本身仍是占位实现：

- `StructuredDataService.query_metric_lookup(...)` 目前返回 `value = "TODO"`
- 这导致 `metric_lookup` 虽然链路已通，但还不能稳定返回真实指标值

与此同时，仓库里已经具备两块关键基础：

- 本地财报 retrieval 链已经能完成 PDF acquisition、parsing、chunking、索引和 evidence assembly
- PDF 解析链已经能抽取表格，并把表格以 `ParsedTable` 结构落盘

这意味着当前最合适的下一阶段不是重做 orchestrator，也不是直接引入重量级外部数据库，而是补出一层真正可查询的结构化指标能力，把“已解析的财报原材料”转成“按公司 / 指标 / 期间可查询的内部指标库”。

同时也要承认一个现实约束：

- 用户可能会查询当前本地语料里并不存在的公司、期间或指标
- 因此首版设计不能只考虑本地文件命中的理想情况，还要预留本地缺失时的外部兜底路径

## 目标

本轮设计目标是为 `structured-market-data-support` 定义一个首版可落地方案，使 `metric_lookup` 能真正返回可追溯的结构化指标结果。

具体目标：

- 明确 `structured_data` 模块的职责边界
- 明确它与 retrieval、orchestrator、router 的衔接方式
- 设计首版最小真实数据路径
- 设计本地财报优先、外部 API 兜底的多源查询策略
- 定义内部指标数据模型、查询模型和来源标注
- 定义本地无数据、外部失败、口径不匹配时的降级语义
- 为后续 implementation plan 提供文件级设计边界

## 非目标

本轮不包含以下内容：

- 不修改现有 OpenSpec 主 spec
- 不重做 retrieval 主链
- 不在首版实现完整 XBRL 级财务仓库
- 不要求覆盖任意公司、任意指标、任意历史期间
- 不让外部 API 成为唯一真相源
- 不把数值解释、证据展开和复杂对比分析都塞进 `structured_data`
- 不在首版把 `event_impact_analysis` 的公司映射与筛选一起做完

## 当前仓库现状

### 已有输入与能力

#### 1. `metric_lookup` 的上游输入已经稳定

router 目前能稳定抽出：

- `company`
- `metric`
- `time_scope`

其中已存在的指标规范化值至少包括：

- `revenue`
- `net_profit`

planner 已经把它收口成固定短路径：

- `query_structured_data`
- `synthesize_brief_answer`

#### 2. retrieval 已具备表格原材料

当前仓库已能从 PDF 中抽取并保存结构化表格，关键字段包括：

- `caption_text`
- `table_text`
- `table_markdown`
- `section_path`
- `related_metric_hints`

这说明本地财报已经不只是“可检索文本”，还具备了进一步做指标抽取的原材料。

#### 3. `structured_data` 仍是占位

当前目录 `backend/src/finsight_agent/capabilities/structured_data/` 只有：

- `service.py`
- `models.py`
- `queries.py`

其中核心问题是：

- 没有内部指标数据模型
- 没有本地指标存储
- 没有从财报表格抽取指标的规则层
- 没有外部 provider 抽象
- 没有查询回退语义

### 设计约束

当前设计必须满足以下约束：

1. `structured_data` 不能侵入 retrieval 的中间产物主权
2. orchestrator 只消费结构化查询结果，不感知底层来源细节
3. 结果必须尽量可追溯到具体财报与表格
4. 本地无数据时不能伪造答案
5. 外部来源只能作为 fallback，不应反过来定义内部 contract

## 职责边界

### `structured_data` 负责什么

`structured_data` 首版负责以下事情：

1. 接收标准化的指标查询条件
2. 先查内部本地指标库
3. 本地未命中时，按策略调用外部 provider
4. 返回统一的结构化查询结果
5. 明确标注数值来源、期间、单位、命中方式和置信度

### `structured_data` 不负责什么

`structured_data` 不负责：

- 不自己做意图识别
- 不自己解析原始用户 query
- 不负责全文证据检索
- 不直接组装复杂 report blocks
- 不负责会话记忆
- 不负责从外部 API 抓取所有历史财报原文

一句话概括：

`structured_data` 是“指标查询能力层”，不是“自然语言理解层”，也不是“证据检索层”。

## 方案对比

### 方案 A：仅做本地财报指标库

结构：

- 只从本地已解析财报表格抽取指标
- `metric_lookup` 只查询本地指标库
- 查不到就直接降级

优点：

- 可追溯性最好
- 和当前 retrieval 资产衔接最自然
- 无外部依赖，测试最稳定

缺点：

- 覆盖率受本地语料限制
- 新公司、新期间或未采集文档时命中率会明显不足

### 方案 B：外部 API 优先，本地财报只做补证

结构：

- 先查外部 API
- 本地财报只作为来源补证或后验核对

优点：

- 覆盖率高，启动快
- 很容易快速让 `metric_lookup` 返回真值

缺点：

- 可追溯性弱于财报原文
- 字段口径与稳定性受外部提供方影响
- 会把核心能力绑到第三方依赖上

### 方案 C：本地财报优先，外部 API 兜底

结构：

1. 优先查询本地内部指标库
2. 本地未命中时按策略调用外部 provider
3. 无论本地还是外部命中，都返回统一结构
4. 未命中时显式降级

优点：

- 兼顾可追溯性与覆盖率
- 与现有 retrieval 最一致
- 可逐步引入外部源，不会把系统一开始就绑死

缺点：

- 设计比单源更复杂
- 需要定义来源优先级和统一结果模型

## 推荐方案

采用 **方案 C：本地财报优先，外部 API 兜底**。

推荐原因：

1. 它最符合当前仓库已经具备的真实能力积累：本地财报采集、解析、表格抽取已经完成
2. 它能最大化保留“可追溯到财报表格”的优势
3. 它也承认现实覆盖率问题，不会让 `metric_lookup` 被本地语料边界卡死
4. 它允许外部 provider 后续逐步演进，而不破坏现有 contract

## 总体设计

### 设计原则

首版遵守四条原则：

1. 先做有限指标，不做泛化财务仓库
2. 先做可追溯查询，再做更大覆盖
3. 先做 deterministic 抽取，再考虑更复杂表格理解
4. 先把“内部指标库 + fallback provider”边界定清，再扩展来源数量

### 首版最小真实路径

首版 `metric_lookup` 真实路径如下：

1. router 抽出 `company`、`metric`、`time_scope`
2. orchestrator 执行 `query_structured_data`
3. `StructuredDataService` 先查本地指标库
4. 若命中，返回本地结构化结果
5. 若未命中，调用外部 provider adapter
6. 若外部命中，返回统一结构并标注来源
7. 若全部失败，返回显式降级结果
8. `synthesize_brief_answer` 读取结构化结果生成最终简答

## 模块分层

建议把 `structured_data` 拆成四层：

### 1. 查询入口层

负责统一对外接口：

- `StructuredDataService`

职责：

- 接收查询参数
- 执行本地优先、外部兜底
- 产出统一结果

### 2. 本地指标库层

负责内部指标记录的存储与查询：

- `MetricRepository`

职责：

- 存储结构化指标记录
- 按公司 / 指标 / 期间查询
- 返回最佳匹配

首版建议使用文件型存储，不要求一上来引入数据库。

### 3. 指标抽取与归一化层

负责把财报解析产物转成指标记录：

- `MetricExtractor`
- `MetricNormalizer`

职责：

- 从 `ParsedTable` 中识别指标行
- 归一化指标名、期间、数值、单位
- 生成内部 `MetricRecord`

### 4. 外部 provider 层

负责封装第三方数据源：

- `ExternalMetricProvider` 抽象
- 一个或多个 adapter 实现

职责：

- 接受统一查询
- 返回统一 provider 结果
- 不把第三方字段直接泄漏到上层

## 数据模型设计

### `MetricQuery`

内部查询对象建议至少包含：

- `company_name`
- `metric_name`
- `time_scope`
- `allow_external_fallback`

### `MetricRecord`

本地指标库中的标准记录建议包含：

- `company_name`
- `company_code`
- `metric_name`
- `metric_label`
- `time_scope`
- `period_end`
- `value`
- `unit`
- `currency`
- `source_type`
- `source_document_id`
- `source_table_id`
- `source_caption`
- `confidence`

其中：

- `metric_name` 使用内部规范名，例如 `revenue`、`net_profit`
- `metric_label` 保留原展示名，例如“营业收入”“归属于上市公司股东的净利润”
- `source_type` 固定为 `local_filing_table` 或 `external_api`

### `MetricLookupResult`

统一查询结果建议包含：

- `company_name`
- `metric_name`
- `time_scope`
- `value`
- `unit`
- `source_type`
- `source_summary`
- `matched_by`
- `confidence`
- `is_degraded`
- `notes`

这样 orchestrator 与 reporting 层不需要知道底层究竟来自本地还是外部。

## 本地数据路径设计

### 数据来源

首版本地来源限定为：

- 年报
- 半年报

暂不要求季报、快报、临时公告全部覆盖。

### 抽取输入

指标抽取器消费已有解析产物中的：

- `document` 元信息
- `ParsedTable.caption_text`
- `ParsedTable.table_text`
- `ParsedTable.table_markdown`
- `ParsedTable.section_path`

### 首版支持指标

首版建议只支持少量高频核心指标：

- `revenue`
- `net_profit`
- `deducted_net_profit`
- `operating_cash_flow`

这样可以先把规则做稳，再考虑扩展。

### 首版支持期间

首版建议先支持：

- `YYYY_annual`
- `YYYY_semiannual`
- `latest`

其中：

- `latest` 表示优先命中当前本地指标库里该公司的最新可用期间
- 若查询明确带年限，则优先精确匹配

### 抽取策略

首版不依赖 LLM 抽表。

采用 deterministic 规则：

1. 根据表题、章节和行名判断该表是否像主要财务数据表
2. 根据指标别名匹配目标行
3. 从同一行提取对应期间列数值
4. 统一清洗千分位、百分号、括号负数等格式
5. 归一化成 `MetricRecord`

### 为什么不直接复用 retrieval 命中结果

因为 retrieval 的目标是“证据召回”，而不是“精确指标查询”。

当前 chunking 还刻意不把表格本体直接塞进普通 child chunk，这更说明 retrieval 和 `structured_data` 应该分层：

- retrieval 负责找证据
- `structured_data` 负责给指标值

## 外部 fallback 设计

### 触发条件

仅当以下条件满足时才允许调用外部 provider：

1. 本地指标库未命中
2. 查询指标属于受支持范围
3. 查询未被显式限制为“仅本地财报”

### provider 角色

外部 provider 的角色是：

- 覆盖本地缺失
- 提供临时可用值
- 在后续阶段作为扩展来源

外部 provider 不是：

- 内部 contract 的定义者
- 唯一真相源
- `metric_lookup` 的默认首选来源

### 首版 provider 策略

首版实现建议：

- 先定义 `ExternalMetricProvider` 抽象接口
- 允许接入一个真实 provider adapter
- provider 缺失或不可用时，系统仍可仅靠本地指标库工作

也就是说：

- 外部 fallback 是首版架构能力的一部分
- 但不能让首版运行闭环强依赖网络和第三方鉴权

### 来源标注

若命中外部 provider，返回结果必须显式包含：

- `source_type = external_api`
- `source_summary`
- `notes` 里标记“结果来自外部指标接口，非本地财报抽取”

这样下游展示和调试时不会误把它当成本地财报真值。

## 降级语义

### 本地未命中，外部命中

结果状态：

- 返回成功结构
- 标注来源为 `external_api`
- `confidence` 低于本地财报抽取命中

### 本地未命中，外部也未命中

结果状态：

- 返回 `is_degraded = true`
- `value` 为空
- `notes` 说明当前未找到对应指标数据

### 指标不在首版支持范围

结果状态：

- 直接降级
- 不伪造数值
- 明确提示“当前结构化指标能力尚不支持该指标”

### 期间口径不匹配

例如只找到年报，用户问季度数据。

结果状态：

- 不把年报值假装成季度值
- 降级或返回“仅找到邻近期间数据”的明确说明

## 与现有模块的衔接点

### 与 router

router 继续只负责：

- 抽 `company`
- 抽 `metric`
- 抽 `time_scope`

不新增结构化数据层细节泄漏到 router。

### 与 planner

planner 继续使用已有短路径：

- `query_structured_data`
- `synthesize_brief_answer`

首版无需为此修改计划结构。

### 与 orchestrator

orchestrator 继续只调用：

- `StructuredDataService.query_metric_lookup(...)`

不需要感知：

- 本地指标库
- 财报表格抽取
- 外部 provider

### 与 retrieval

retrieval 与 `structured_data` 的衔接边界是：

- retrieval 提供解析产物与表格原材料
- `structured_data` 自己负责把这些原材料变成指标记录

换句话说，`structured_data` 可以消费 retrieval 的离线产物，但不应该侵入 retrieval 在线查询接口。

## 测试设计

首版测试建议覆盖四类行为：

### 1. 指标抽取单测

验证：

- 表题识别
- 指标别名识别
- 年报 / 半年报期间识别
- 数值清洗与单位归一化

### 2. 本地指标库查询单测

验证：

- 精确期间命中
- `latest` 命中
- 未命中返回空

### 3. service fallback 单测

验证：

- 本地命中时不调用外部 provider
- 本地未命中时调用外部 provider
- 外部 provider 失败时返回降级结构

### 4. 入口级集成测试

验证：

- `metric_lookup` 端到端返回真实数值而非 `TODO`
- trace / response 结构不回归
- 降级路径可被稳定观察

## 分阶段实现建议

### 阶段 1：本地指标库闭环

先完成：

- 内部数据模型
- 文件型 repository
- 表格抽取器
- 本地查询 service

目标是让一批 fixture 财报能真实回答 `metric_lookup`。

### 阶段 2：外部 provider 兜底

再补：

- `ExternalMetricProvider` 抽象
- 一个真实 adapter
- 来源标注与降级策略

目标是缓解本地语料覆盖不足。

### 阶段 3：指标覆盖扩展

后续再扩：

- 更多指标
- 更多期间类型
- 更稳的表格列识别
- 更完整的来源排序策略

## 完成标准

当满足以下条件时，可视为 `structured-market-data-support` 首版落地：

1. `metric_lookup` 不再返回 `TODO`
2. 至少一组真实财报 fixture 可稳定抽出并查询核心指标
3. 本地命中结果可追溯到具体报告与表格
4. 本地未命中时可按统一策略尝试外部 fallback
5. 命中失败时系统显式降级，而不是伪造答案
6. 不破坏现有 router / planner / orchestrator / session / retrieval 已完成链路

