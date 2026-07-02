# Dual-Source Event Context Retrieval Design

## 背景

截至 2026-07-02，FinSight 已经具备以下基础能力：

- `semantic-routing-and-planning` 已能稳定产出 `event_impact_analysis` 的四阶段 `Plan`
- orchestrator 已打通 `metric_lookup`、`evidence_lookup`、`event_impact_analysis` 的首版真实执行链
- `collect_event_context` 与 `analyze_targets` 已有 runner、`ExternalContextRetriever` 抽象和受约束 LLM 目标分析服务
- 本地 retrieval 已完成 PDF acquisition、parsing、chunking、sparse、dense、fusion、rerank、evidence assembly
- 结构化市场数据首版已经落地，`metric_lookup` 不再返回占位 `TODO`

当前缺口在于：`event_impact_analysis` 的外部检索层仍只有抽象接口与空实现，导致系统虽然能跑通链路，但对“近期发生的真实事件”仍缺少稳定的外部输入。

同时，事件分析并不只需要“公司披露”：

- 一类问题需要先理解事件本身，如地缘冲突、关税、政策、油价、行业监管
- 另一类问题需要理解事件与 A 股公司的关系，如公告、披露、受益标的、受损标的

因此，外部检索不应被设计成单一 provider，而应拆成“事件搜索层”和“披露搜索层”两类能力。

## 目标

本设计目标是为 `event_impact_analysis` 定义一个可落地、可扩展、首版免费可用的双层外部检索架构，重点包括：

- 为 `collect_event_context` 定义两类外部检索能力：
  - `EventSearchProvider`
  - `DisclosureSearchProvider`
- 引入一个小模型驱动的 `RetrievalStrategyClassifier`，替代规则词表决定检索起手式
- 在 `collect_event_context` 中支持：
  - `event_primary`
  - `disclosure_primary`
  - `dual_primary`
  三种检索策略
- 明确本地 RAG 只作为条件触发的补充源，而不是固定必经步骤
- 为后续 implementation plan 提供清晰的组件边界、调用预算与降级语义

## 非目标

- 本轮不直接写实现代码
- 不重写现有 orchestrator、router、planner、retrieval、structured data 的主 contract
- 不把 `collect_event_context` 做成无限回路或 agent 自由探索
- 不在首版引入付费或强账号依赖的外部数据服务作为阻塞项
- 不要求首版覆盖所有新闻站点、政策站点或公告站点

## 现状判断

当前仓库里，之前的 RAG 已经使用过部分官方真相源，但用法主要是“离线采集 -> 落本地语料库 -> 本地检索”，而不是“运行时实时外部检索”。

已经接入过的离线采集源包括：

- `CNInfo / 巨潮`
- `SSE / 上交所公告`

它们支撑的是：

```text
官方披露源 -> 本地 PDF 采集 -> 本地解析/切块/索引 -> Local RAG
```

而本设计要补的是：

```text
用户问题 -> 运行时外部检索 -> collect_event_context / 候选发现
```

两者不是重复建设，而是能力层次不同：

- 前者负责本地证据库建设
- 后者负责近期事件感知与上下文建立

## 设计原则

### 1. 事件理解与披露理解分层

外部世界事件与上市公司披露不是同一种信息源，必须分层处理：

- `EventSearchProvider`
  - 面向新闻、政策、公共资讯、外部事件背景
- `DisclosureSearchProvider`
  - 面向公告、定期报告、临时披露、官方站点材料

### 2. 检索策略不由规则词表主导

用户问法无限多，单纯靠规则词表维护成本高、脆弱且难以覆盖真实 query 分布。

因此首版改为：

- 用小模型做检索策略分类
- 输出强约束标签
- 不让大模型自由推理整个执行路径

### 3. `collect_event_context` 不固定查全套

`collect_event_context` 的职责是“拿到足够的事件上下文”，不是“每次固定把外部、披露、本地 RAG 都打一遍”。

因此它应采用：

- 主源优先
- 条件补源
- 命中足够即提前结束

### 4. 免费优先，官方优先

首版 external provider 必须满足：

- 免费
- 可访问
- 来源足够可靠
- 不把系统阻塞在付费、采购或复杂鉴权上

因此首版推荐：

- `EventSearchProvider = GDELT`
- `DisclosureSearchProvider = 巨潮 + 上交所`

## 方案对比

### 方案 A：只接官方披露检索

做法：

- 只实现 `DisclosureSearchProvider`
- 用巨潮与上交所做事件背景、候选发现和补证据

优点：

- 免费
- 官方
- 与现有 PDF acquisition 源一致

缺点：

- 对“外部世界事件”的理解不足
- 很多 query 只能回答公司披露，不能先讲清楚事件本身

### 方案 B：只接事件新闻检索

做法：

- 只实现 `EventSearchProvider`
- 用新闻/公共资讯构建事件背景

优点：

- 对时效性事件友好
- 更能回答“最近发生了什么”

缺点：

- 与 A 股/披露/公司侧关系会偏弱
- 候选发现和证据追溯不够稳

### 方案 C：双层 provider + 小模型分类器

做法：

- 同时实现：
  - `EventSearchProvider`
  - `DisclosureSearchProvider`
- 再引入：
  - `RetrievalStrategyClassifier`
  - `ContextRetrievalPlanner`

优点：

- 能同时处理事件背景与公司披露两类信息需求
- 比“全规则”更灵活
- 比“全自由大模型”更可控
- 与现有 orchestrator / capability 分层风格最一致

缺点：

- 比单 provider 方案多一层设计
- 需要定义统一结果结构和预算语义

## 推荐方案

采用 **方案 C：双层 provider + 小模型分类器**。

决策理由：

1. `event_impact_analysis` 的核心问题不是单一数据源缺失，而是“事件理解”和“公司披露理解”同时存在
2. 检索策略属于小标签分类问题，适合由小模型承担，而不适合继续扩张规则词表
3. 当前 `ExternalContextRetriever` 已经为上层隔离了 orchestrator 边界，适合在其下方增加可插拔 provider 和 planner
4. 该方案既能保持首版免费可用，又为未来接入 `CNINFO Data Service` 等更强 provider 留出升级位

## 目标架构

```text
query + router_result + session_context
                |
                v
    RetrievalStrategyClassifier
                |
                v
      ContextRetrievalPlanner
                |
                v
       collect_event_context
        |         |         |
        v         v         v
  EventSearch  Disclosure  Local RAG(optional)
```

### 上层保持不变

上层 orchestrator 仍只依赖：

- `ExternalContextRetriever.retrieve_event_context(...)`
- `ExternalContextRetriever.discover_candidates(...)`

不要求 orchestrator 感知具体 provider。

### 新增下层组件

- `RetrievalStrategyClassifier`
- `ContextRetrievalPlanner`
- `EventSearchProvider`
- `DisclosureSearchProvider`
- `DualSourceExternalContextRetriever`（真实实现 `ExternalContextRetriever`）

## 组件设计

### 1. `RetrievalStrategyClassifier`

职责：

- 只负责判断 `collect_event_context` 本轮应该采取哪种主检索策略

输入：

- `query`
- `router_result.intent`
- `router_result.entities`
- 可选 `session_context.active_topic`

输出：

```python
{
  "strategy": "event_primary" | "disclosure_primary" | "dual_primary",
  "confidence": "high" | "medium" | "low",
  "reason": "..."
}
```

约束：

- 只允许输出上述 3 个策略标签
- 不参与事件总结
- 不参与股票判断
- 不参与证据检索

失败处理：

- 若分类器调用失败或输出非法标签，系统回退到保守默认值：
  - `event_primary`

### 2. `ContextRetrievalPlanner`

职责：

- 把分类器输出翻译成本轮 `collect_event_context` 的执行计划

输入：

- `query`
- `router_result`
- `session_context`
- classifier 输出

输出：

```python
{
  "mode": "event_primary",
  "steps": [
    {"source": "event_search", "budget": 1},
    {"source": "disclosure_search", "budget": 1, "when": "if_weak"}
  ],
  "allow_local_rag": False
}
```

职责边界：

- planner 只规划“调谁、顺序、预算、是否允许补 RAG”
- 不直接访问网络
- 不直接做结果合并

### 3. `EventSearchProvider`

首版推荐实现：

- `GdeltEventSearchProvider`

职责：

- 查询外部世界事件背景
- 返回近期新闻/公共资讯片段
- 生成轻量 `summary_hint`
- 提供 `supporting_points`
- 必要时抽取显式出现的候选公司/板块提示

返回结构建议：

```python
{
  "items": [
    {
      "title": "...",
      "source": "gdelt",
      "publish_date": "2026-07-02",
      "url": "...",
      "snippet": "...",
      "company_names": [],
      "themes": ["航运", "油运"]
    }
  ],
  "summary_hint": "...",
  "supporting_points": ["...", "..."],
  "evidence_refs": ["gdelt:item_001"],
  "candidate_hints": ["航运", "油运"],
  "source_status": {"gdelt_used": True}
}
```

非职责：

- 不给结构化财务指标
- 不直接决定最终股票池
- 不替代 `retrieve_evidence`

### 4. `DisclosureSearchProvider`

首版推荐实现：

- `OfficialDisclosureSearchProvider`

内部来源：

- 巨潮资讯
- 上交所公告页

职责：

- 查询公告、披露、公司侧材料
- 补充事件与上市公司之间的连接
- 在候选池不足时支持候选发现
- 为后续 `retrieve_evidence` 提供外部官方补证入口

返回结构建议：

```python
{
  "items": [
    {
      "title": "...",
      "source": "cninfo",
      "publish_date": "2026-07-01",
      "url": "...",
      "snippet": "...",
      "company_codes": ["600123"],
      "company_names": ["某公司"],
      "themes": ["航运"]
    }
  ],
  "summary_hint": "...",
  "supporting_points": ["...", "..."],
  "evidence_refs": ["cninfo:announcement_001"],
  "candidates": ["中远海能"],
  "source_status": {"cninfo_used": True, "sse_used": False}
}
```

### 5. `DualSourceExternalContextRetriever`

职责：

- 作为 `ExternalContextRetriever` 的真实实现
- 内部组合：
  - classifier
  - planner
  - event provider
  - disclosure provider
- 对上层暴露：
  - `retrieve_event_context(...)`
  - `discover_candidates(...)`

## `collect_event_context` 策略模式

本设计正式定义三种策略模式。

### `event_primary`

适用：

- query 以外部事件为中心
- 重点先搞清楚“发生了什么”

推荐计划：

1. `EventSearchProvider` 1 次
2. 若结果弱，则 `DisclosureSearchProvider` 1 次补充
3. 默认不查本地 RAG
4. 仅在需要本地可追溯证据时才补 1 次本地 RAG

### `disclosure_primary`

适用：

- query 以公司公告、财报、扩产、订单、业绩等披露类材料为中心

推荐计划：

1. `DisclosureSearchProvider` 1 次
2. 若结果弱，则 `EventSearchProvider` 1 次补充
3. 默认不查本地 RAG
4. 仅在需要正文证据片段时才补 1 次本地 RAG

### `dual_primary`

适用：

- query 明确同时需要：
  - 事件背景
  - A 股/公司/板块影响

示例：

- `红海局势升级利好哪些A股航运股`
- `关税升级对哪些消费电子公司冲击最大`

推荐计划：

1. `EventSearchProvider` 1 次
2. `DisclosureSearchProvider` 1 次
3. 若两边合并后上下文已足够，直接结束
4. 默认不再自动补本地 RAG

## `collect_event_context` 成功与提前结束条件

### 成功条件

满足以下任一即可视为“上下文足够”：

- 合并后能稳定产出：
  - `event`
  - `themes`
  - `time_scope`
  - `context_summary`
- 且至少具备：
  - 2 条可用 `supporting_points`
  - 或 2 个可引用 `evidence_refs`

### 提前结束

当主源或双主源已经满足成功条件时：

- 本轮不再默认查本地 RAG
- 直接进入上下文合并与 stage 输出

### Local RAG 的触发条件

只有在以下场景下才允许补一次本地 RAG：

- 外部结果已拿到背景，但缺本地可追溯证据
- 用户问法显式偏：
  - `A股`
  - `哪些公司`
  - `公告`
  - `证据`
- 需要把事件与本地 corpus 中已解析的公司材料连接起来

## `collect_event_context` 输出结构

推荐保持与现有 runner 风格对齐：

```python
{
  "event_context": {
    "event": "红海局势升级",
    "themes": ["航运", "油运"],
    "time_scope": "recent",
    "context_summary": "...",
    "supporting_points": ["...", "..."],
    "evidence_refs": ["gdelt:item_001", "cninfo:announcement_002"],
    "candidate_hints": ["中远海能", "招商轮船", "航运"]
  },
  "event_entities": {
    "event": "红海局势升级",
    "themes": ["航运", "油运"],
    "time_scope": "recent"
  },
  "source_status": {
    "strategy": "dual_primary",
    "event_search": "success",
    "disclosure_search": "weak",
    "local_rag": "skipped"
  }
}
```

## `discover_candidates(...)` 设计

当 `analyze_targets` 发现候选池为空或过弱时：

- 只允许补 1 轮有界候选发现检索

推荐来源优先级：

1. `DisclosureSearchProvider`
2. 必要时消费 `EventSearchProvider` 中显式出现的公司/板块提示

原则：

- 先补搜索
- 不强行编股票
- 仍无可靠候选就诚实降级

成功输出：

```python
{
  "candidates": ["中远海能", "招商轮船"],
  "source_status": {
    "disclosure_search": "success"
  }
}
```

失败语义：

- 没有明确公司或板块可提取：`empty`
- 只有模糊主题：`weak`
- 请求失败：`error`

## 降级与失败语义

统一采用以下状态：

- `success`
- `weak`
- `empty`
- `error`

阶段级结果采用：

- `success`
- `partial`
- `degraded`
- `failed`

### `collect_event_context`

- 外部事件有结果、披露无结果：可继续，必要时标记 `local_support_missing`
- 外部事件弱、披露补到：可继续
- 双主源都弱：`degraded`
- 双主源都空且无法形成最小上下文：`failed`

### `analyze_targets`

- 候选池不足时先补 1 轮候选发现检索
- 补检索后仍无可靠候选：`degraded`
- `target_scope` 与 `ranked_targets` 允许为空
- 必须显式告诉用户当前只能确认事件背景，尚不能可靠识别具体标的

## 与现有系统的衔接

### 与 orchestrator

- orchestrator 不直接感知具体 provider
- 仍通过 `ExternalContextRetriever` 与 stage runner 交互

### 与 `collect_event_context` runner

- runner 不再自己硬编码“先外部、再本地 RAG”的固定顺序
- 改为消费：
  - classifier 输出
  - planner 计划
  - provider 结果

### 与 `retrieve_evidence`

- 不改变其核心职责
- 仍由它承担“重证据补强”
- `collect_event_context` 只负责轻量上下文建立

### 与 structured data

- 本设计不直接扩张结构化指标查询范围
- 结构化数据只在后续 `retrieve_evidence` 阶段作为补强能力存在

## 首版实现建议

### 阶段 1

补齐：

- `RetrievalStrategyClassifier`
- `ContextRetrievalPlanner`
- `GdeltEventSearchProvider`
- `OfficialDisclosureSearchProvider`
- `DualSourceExternalContextRetriever`

### 阶段 2

改造：

- `collect_event_context` runner
- `analyze_targets` 的候选发现调用点
- trace / observation 中增加策略与 source status

### 阶段 3

补齐：

- 单测
- 端到端集成测试
- 首批事件分析评测样本

## 测试策略

首版至少覆盖：

1. classifier 能稳定输出三类策略标签
2. classifier 非法输出会回退到 `event_primary`
3. `event_primary` 时仅调用事件 provider
4. `disclosure_primary` 时仅调用披露 provider
5. `dual_primary` 时并行或顺序调用双主源，且默认不查 RAG
6. 主源已足够时提前结束
7. 主源不足时才补本地 RAG
8. 候选池不足时会触发 1 轮候选发现检索
9. 候选发现后仍不足时 `analyze_targets` 返回 `degraded`
10. 端到端 `event_impact_analysis` 能消费真实 external provider 结果

## 设计结论

`event_impact_analysis` 的下一阶段演进重点，不是再增加新的 stage，而是为已有 `collect_event_context` 补齐“真实、免费、可扩展”的外部上下文检索层。

推荐落地方式是：

- 用 `RetrievalStrategyClassifier` 决定检索起手式
- 用 `ContextRetrievalPlanner` 控制预算与补源逻辑
- 用双层 provider 分别承担：
  - 事件理解
  - 披露理解
- 保持本地 RAG 为条件触发补充源，而非固定必经步骤

这条路线比“继续堆规则词表”更稳，也比“放任大模型自由决定一切”更可控，是当前仓库状态下最平衡的方案。
