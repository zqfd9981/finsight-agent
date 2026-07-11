# FinSight Query Routing 与 Stage Flow 业务说明

日期：2026-07-08

## 1. 这份文档是写给谁看的

这不是一份 OpenSpec 设计稿，也不是研发实现细节清单。

这份文档的目标是：

- 用业务语言说明 FinSight 里不同类型 query 应该怎么走链路
- 明确当前这次改造完成后的目标架构
- 保留链路、字段、query 类型、职责边界和中间对象的完整说明
- 避免后续又退回到“先保留旧链路、以后再补”的口径

## 2. 一步到位的总原则

### 2.1 `event_impact_analysis` 不能先固定 stage 再分类

这次改造完成后的原则是：

- 对于 `intent = event_impact_analysis`
- 必须先做 retrieval strategy classify
- 再由 orchestrator 的 stage_planner 根据 classifier label 编排 stage

也就是：

`router -> retrieval strategy classifier -> orchestrator (stage lookup) -> stage execution`

而不是：

`router -> planner 固定四段 -> collect_event_context 内部再分类`

### 2.2 `event_primary / disclosure_primary / dual_primary` 不只是检索标签

改造完成后，这 3 个 label 同时承担两层职责：

- 决定外部上下文优先从哪里获取
- 决定后续 stage 应该如何编排

### 2.3 `collect_event_context` 只负责收集上下文，不再负责决定 strategy

改造完成后：

- `collect_event_context` 不再内部调用 strategy classifier
- 它只消费上游已经确定好的 `strategy`
- 它只负责按 strategy 执行新闻搜索、公告搜索或双源搜索，并输出统一 `event_context`

### 2.4 `retrieve_evidence` 是本地 RAG，不是外部搜索

`retrieve_evidence` 的职责必须保持明确：

- 它查的是本地入库文档、公告正文、财报 chunk
- 它负责提供公司级、正文级、证据级支撑
- 它不负责补外部事件背景

### 2.5 这次改造要直接落到正式目标态

这次文档口径保留的就是正式目标态，而不是过渡态：

- classifier 前移
- orchestrator stage_planner 按 classifier label 分叉
- `synthesize_answer` 作为统一 stage 按 `response_mode` 分发
- `collect_event_context` 去掉内部分类职责
- `event_impact_analysis` 不再统一固定四段链路

## 3. 当前业务里存在的顶层能力

### 3.1 顶层 intent

当前共享枚举里有 5 个 intent：

- `metric_lookup`
- `event_impact_analysis`
- `evidence_lookup`
- `general_finance_qa`
- `out_of_scope`

可以简单理解为：

- `metric_lookup`：问一个结构化数值
- `event_impact_analysis`：问一个事件或事件影响
- `evidence_lookup`：要证据、原文、依据
- `general_finance_qa`：问一个泛财经常识问题（宏观机制、概念解释）
- `out_of_scope`：超出能力范围

### 3.2 当前 stage 体系

当前保留的正式 stage 包括：

- `query_structured_data`
- `collect_event_context`
- `analyze_targets`
- `retrieve_evidence`
- `synthesize_answer`

业务上可以这样理解：

- `query_structured_data`：查结构化指标
- `collect_event_context`：补外部事件背景
- `analyze_targets`：从事件背景收缩到板块、公司、标的候选
- `retrieve_evidence`：去本地证据库补公司/公告/正文证据
- `synthesize_answer`：统一综合阶段，按 `response_mode`（direct / brief_answer / event_answer / report）切换 prompt 模板

### 3.3 当前外部上下文的两类来源

当前外部上下文天然分成两类来源：

- 新闻搜索 `event_search`
- 公告搜索 `disclosure_search`

因此真正需要通过这次改造明确的，不是“接口要不要拆”，而是：

- 什么场景优先走事件背景
- 什么场景优先走公告背景
- 什么场景需要双源结合

## 4. query 类型与正式链路

为了让链路更清楚，这里不只看顶层 `intent`，而是看用户到底在问什么类型的问题。

### 4.1 `metric_lookup`

示例：

- `宁德时代 2024H1 利润多少`
- `贵州茅台 2024 营收是多少`

正式链路：

`query_structured_data -> synthesize_answer` (response_mode=brief_answer)

这类 query 不需要：

- 新闻
- 公告
- 事件背景
- 候选标的
- 公司证据检索

### 4.2 `event_context_answer`

示例：

- `红海局势最近怎么了`
- `红海局势升级对 A 股哪些板块有影响`

目标：

- 要事件背景
- 要事件演化
- 要影响链条
- 可能要板块级归纳
- 不要求系统收缩到具体公司

正式链路：

`router -> event_impact_analysis -> classifier(event_primary) -> orchestrator (stage lookup) -> collect_event_context -> synthesize_answer` (response_mode=event_answer)

关键点：

- 搜完事件背景后通常就可以答
- 不应该进入 `analyze_targets`
- 不应该默认进入 `retrieve_evidence`

### 4.3 `target_discovery`

示例：

- `红海局势升级利好哪些 A 股航运股`
- `关税升级对哪些消费电子公司冲击更大`

目标：

- 不是只理解事件
- 而是要从事件进一步收缩到具体板块、公司、标的

正式链路：

`router -> event_impact_analysis -> classifier(dual_primary) -> orchestrator (stage lookup) -> collect_event_context -> analyze_targets -> retrieve_evidence -> synthesize_answer` (response_mode=report)

关键点：

- `analyze_targets` 是必要步骤
- `retrieve_evidence` 也是必要步骤
- 这是完整重链路真正该出现的场景

### 4.4 `disclosure_interpretation`

示例：

- `宁德时代扩产公告意味着什么`
- `某公司业绩预告是否释放积极信号`
- `某公司回购公告怎么看`

目标：

- 解读公司公告、业绩预告、公司内生事件
- 重点是正式披露了什么、释放了什么信号

正式链路：

`router -> event_impact_analysis -> classifier(disclosure_primary) -> orchestrator (stage lookup) -> collect_event_context -> retrieve_evidence -> synthesize_answer` (response_mode=report)

关键点：

- 目标公司通常已经明确
- 重点是公告和公司证据
- 不应进入 `analyze_targets`

### 4.5 `evidence_lookup`

示例：

- `中远海能受益的依据是什么`
- `把这个判断的证据展开`

目标：

- 直接索要证据

正式链路：

`router -> evidence_lookup -> retrieve_evidence -> synthesize_answer` (response_mode=report)

关键点：

- 不需要事件背景
- 不需要候选池
- 重点是证据补全和证据组织

### 4.6 `general_finance_qa`

示例：
- `降息对债市意味着什么`
- `半导体周期一般怎么走`
- `人民币贬值压力从哪来`

目标：
- 用金融常识直接回答
- 不需要检索结构化数据、事件背景或本地证据

正式链路：
`router -> general_finance_qa -> orchestrator (stage lookup) -> synthesize_answer (response_mode=direct)`

关键点：
- 单 stage 直答
- 不进入任何检索阶段
- `out_of_scope` 只对投资建议/荐股/股价预测触发，泛财经问题不再被拒答

## 5. `event_impact_analysis` 的正式总流程

改造完成后的总流程应是：

`router -> intent=event_impact_analysis -> retrieval strategy classifier -> orchestrator (stage lookup) -> stage execution`

其中：

- router 负责顶层 `intent` 和基础 entities 抽取
- classifier 负责判断 `event_primary / disclosure_primary / dual_primary`
- planner 负责根据 classifier label 生成 stage 列表
- stage runner 只执行，不再补做路径判断

### 5.1 classifier 的位置

classifier 应该位于 router 之后、orchestrator 之前，而不是 `collect_event_context` 内部。

这是这次文档要保留的正式口径，不是可选项。

### 5.2 `collect_event_context` 的职责边界

改造完成后，`collect_event_context` 的职责是：

- 接收 `query`、`event`、`themes`、`time_scope`、`strategy`
- 根据 strategy 决定使用：
  - `event_search`
  - `disclosure_search`
  - 或双源都用
- 合并结果，输出统一 `event_context`

它不再负责：

- 自己调用 classifier
- 自己决定 stage 走向

## 6. classifier label 与 stage 链路的正式映射

### 6.1 `event_primary`

适合：

- `红海局势最近怎么了`
- `红海局势升级对 A 股哪些板块有影响`

必须映射到：

`collect_event_context -> synthesize_answer` (response_mode=event_answer)

### 6.2 `disclosure_primary`

适合：

- `宁德时代扩产公告意味着什么`
- `某公司业绩预告是否释放积极信号`

必须映射到：

`collect_event_context -> retrieve_evidence -> synthesize_answer` (response_mode=report)

### 6.3 `dual_primary`

适合：

- `红海局势升级利好哪些 A 股航运股`

必须映射到：

`collect_event_context -> analyze_targets -> retrieve_evidence -> synthesize_answer` (response_mode=report)

这意味着：

- classifier 不再只是“搜什么源”的提示器
- classifier 已经正式成为 planner 的路径选择输入

## 7. 新闻搜索与公告搜索的职责分工

### 7.1 新闻搜索负责什么

新闻搜索负责：

- 近期事件发生了什么
- 事件如何演化
- 市场通常如何理解影响链条

适用于：

- 国际局势
- 宏观事件
- 行业突发
- 政策变化

### 7.2 公告搜索负责什么

公告搜索负责：

- 公司正式披露了什么
- 标题、数字、时间点、措辞意味着什么
- 公告级事实发现

适用于：

- 扩产公告
- 业绩预告
- 回购、减持、定增、重组
- 公司内生重大事项

### 7.3 双源都需要的场景

典型场景是：

- 外部事件先影响行业
- 再落到具体上市公司

例如：

- `红海局势升级利好哪些 A 股航运股`

这时：

- 新闻负责提供外部事件背景
- 公告和公司文档负责验证公司侧受益逻辑

## 8. 关键中间字段应该承载什么

这一节保留字段级说明和举例。

### 8.1 `RouterResult`

建议业务理解：

- `intent`
  - 第一层大分流
- `follow_up_type`
  - 多轮场景附加信号
- `entities`
  - 本轮 query 抽出的关键语义实体
- `constraints`
  - planner 可消费的执行提示

示例：

```json
{
  "intent": "event_impact_analysis",
  "follow_up_type": "none",
  "confidence": "high",
  "entities": {
    "event": "红海局势升级",
    "themes": ["航运", "油运"],
    "time_scope": "recent"
  },
  "needs": ["news_search", "concept_mapping", "rag_retrieval"],
  "constraints": {
    "time_hint": "recent",
    "preferred_output": "report"
  }
}
```

### 8.2 classifier 输出 `strategy_payload`

建议至少保留：

- `strategy: str`
  - 值域：`event_primary | disclosure_primary | dual_primary`
- `confidence: str`
  - 值域：`high | medium | low`
- `reason: str`
  - 调试和回放用

示例：

```json
{
  "strategy": "dual_primary",
  "confidence": "high",
  "reason": "query asks for affected A-share shipping stocks, so both event background and company-side validation are needed"
}
```

### 8.3 stage_planner 输出 (stages, stage_constraints, response_mode)

说明：`Plan` 契约已删除，以下改为 `stage_planner.resolve_stages` 的查表输出。

建议业务理解：

- `intent`
- `stages`
- `stage_constraints`
- `response_mode`

其中最关键的是：

- `stages`
  - 决定实际执行链路
- `stage_constraints`
  - 决定每个 stage 的预算、模式和提示

改造完成后，stage_planner 查表输出必须已经体现 classifier 带来的 stage 分叉。

#### `event_primary` 示例

```json
{
  "intent": "event_impact_analysis",
  "stages": [
    "collect_event_context",
    "synthesize_answer"
  ],
  "stage_constraints": {
    "collect_event_context": {
      "time_hint": "recent",
      "retrieval_budget": 3,
      "strategy": "event_primary",
      "strategy_confidence": "high",
      "strategy_reason": "event background question"
    },
    "synthesize_answer": {
      "preferred_output": "brief_answer",
      "response_mode": "event_answer"
    }
  },
  "response_mode": "event_answer"
}
```

#### `disclosure_primary` 示例

```json
{
  "intent": "event_impact_analysis",
  "stages": [
    "collect_event_context",
    "retrieve_evidence",
    "synthesize_answer"
  ],
  "stage_constraints": {
    "collect_event_context": {
      "time_hint": "recent",
      "retrieval_budget": 3,
      "strategy": "disclosure_primary",
      "strategy_confidence": "high",
      "strategy_reason": "disclosure interpretation question"
    },
    "retrieve_evidence": {
      "retrieval_budget": 4
    },
    "synthesize_answer": {
      "preferred_output": "report",
      "response_mode": "report"
    }
  },
  "response_mode": "report"
}
```

#### `dual_primary` 示例

```json
{
  "intent": "event_impact_analysis",
  "stages": [
    "collect_event_context",
    "analyze_targets",
    "retrieve_evidence",
    "synthesize_answer"
  ],
  "stage_constraints": {
    "collect_event_context": {
      "time_hint": "recent",
      "retrieval_budget": 3,
      "strategy": "dual_primary",
      "strategy_confidence": "high",
      "strategy_reason": "target discovery question"
    },
    "analyze_targets": {
      "target_scope": ["航运"]
    },
    "retrieve_evidence": {
      "retrieval_budget": 4
    },
    "synthesize_answer": {
      "preferred_output": "report",
      "response_mode": "report"
    }
  },
  "response_mode": "report"
}
```

### 8.4 `collect_event_context` 的核心输出 `event_context`

这一层不建议做得过重，最合适的是轻结构。

示例：

```json
{
  "event": "红海局势升级",
  "themes": ["航运", "油运"],
  "time_scope": "recent",
  "context_summary": "红海局势近期升级，多家船公司继续绕行，航线时效拉长，运价存在上行压力。",
  "supporting_points": [
    "部分航线继续绕行",
    "运价和运输时效受到影响"
  ],
  "evidence_refs": ["bocha:item_001", "cninfo:123456"],
  "candidate_hints": ["航运", "港口", "油运"]
}
```

这里最重要的是：

- `context_summary`
  - 给后续 LLM 看的主内容
- `supporting_points`
  - 给 trace 和回答引用看的摘要支点
- `evidence_refs`
  - 用于回溯来源
- `candidate_hints`
  - 仅在需要继续做标的发现时使用

### 8.5 `analyze_targets` 的输出

这一层和 `event_context` 不一样，应该继续保持结构化。

建议保留：

- `target_scope: list[str]`
- `ranked_targets: list[object]`
- `open_questions: list[str]`
- `confidence: str`
- `analysis_mode: str`

其中 `ranked_targets` 的单项建议至少包括：

- `target`
- `target_type`
- `impact_direction`
- `reasoning_summary`
- `confidence`

示例：

```json
{
  "target_scope": ["航运", "油运"],
  "ranked_targets": [
    {
      "target": "中远海能",
      "target_type": "company",
      "impact_direction": "positive",
      "reasoning_summary": "油运链条对航线绕行和运价弹性更敏感。",
      "confidence": "medium"
    }
  ],
  "open_questions": [
    "运价上行是否足以传导到具体公司盈利"
  ],
  "confidence": "medium",
  "analysis_mode": "llm_constrained"
}
```

### 8.6 `retrieve_evidence` 的输出

业务理解：

- 这一层的结果是公司、公告、内部证据块集合
- 不负责事件背景补全
- 只负责围绕目标补证据

因此它输出里最关键的不是摘要，而是：

- `retrieval_result`
- `evidence_refs`

## 9. 最终喂给 LLM 的内容粒度

最终喂给 LLM 的内容，不应只是标题，也不应直接灌全文。

最合适的粒度是：

- 标题级别：用于召回、粗筛、排序
- 正文摘要级别：用于主推理
- 正文片段级别：用于校验和引用

对应到系统里：

- `collect_event_context`
  - 输出自然语言 `context_summary`
- `analyze_targets`
  - 消费 `context_summary` 和候选信息
- `synthesize_answer`
  - 基于 `response_mode`（event_answer / report / brief_answer / direct）切换 prompt，基于事件摘要和证据完成回答

所以事件背景层最适合：

- “轻结构 + 摘要 string”

而不是：

- 很重的 rigid schema

## 10. router 的边界

### 10.1 当前规则 router 的主要风险

例如：

- `某公司业绩预告是否释放积极信号`

这类 query 在规则 router 下有两个风险：

- 可能直接识别不出来
- 如果带了具体公司名和 `净利润/营收` 等词，也可能被误导到 `metric_lookup`

这说明：

- router 在“查数值”和“解读公告”之间的边界处理仍然偏弱

### 10.2 这次改造对 router 的要求

这次文档口径不要求先把 router 全面 LLM 化。

这次改造只要求做到：

- router 继续稳定产出顶层 `intent`
- `intent = event_impact_analysis` 时，系统必须立刻进入 classifier
- classifier 结果必须真正影响 planner

也就是说，这次的一步到位目标是：

- 先把“分类前移 + planner 分叉 + stage 重构”做完整

而不是：

- 在同一次改造里把 router 一并重做

## 11. 这次改造完成后的目标状态

### 11.1 执行框架目标

- 保留现有顶层 intent
- 对 `event_impact_analysis` 引入“先分类、后规划”
- 让 planner 正式按 classifier label 分叉
- 去掉 `collect_event_context` 内部的 classifier 调用

### 11.2 stage 体系目标

- 保留：
  - `query_structured_data`
  - `collect_event_context`
  - `analyze_targets`
  - `retrieve_evidence`
  - `synthesize_answer`

### 11.3 query 路径目标

- `metric_lookup`
  - `query_structured_data -> synthesize_answer` (response_mode=brief_answer)
- `general_finance_qa`
  - `synthesize_answer` (response_mode=direct)
- `event_primary`
  - `collect_event_context -> synthesize_answer` (response_mode=event_answer)
- `disclosure_primary`
  - `collect_event_context -> retrieve_evidence -> synthesize_answer` (response_mode=report)
- `dual_primary`
  - `collect_event_context -> analyze_targets -> retrieve_evidence -> synthesize_answer` (response_mode=report)
- `evidence_lookup`
  - `retrieve_evidence -> synthesize_answer` (response_mode=report)

### 11.4 职责边界目标

- 新闻搜索负责事件背景
- 公告搜索负责正式披露发现
- `retrieve_evidence` 负责本地正文证据
- `analyze_targets` 只在真正需要从事件走向标的时出现

### 11.5 这次改造不再保留的旧逻辑

改造完成后，不应再保留以下逻辑作为主路径：

- `event_impact_analysis` 统一固定四段链路
- `collect_event_context` 内部再决定 strategy
- `event_primary` 也默认进入 `analyze_targets`
- `disclosure_primary` 也默认进入候选池

## 12. 最实用的总表

| 用户问题类型 | 典型 query | 是否需要新闻 | 是否需要公告 | 是否需要候选池 | 是否需要公司证据 | 正式链路 |
| --- | --- | --- | --- | --- | --- | --- |
| `metric_lookup` | 宁德时代 2024H1 利润多少 | 否 | 否 | 否 | 否 | `query_structured_data -> synthesize_answer` |
| `event_context_answer` | 红海局势最近怎么了 | 是 | 视情况 | 否 | 否 | `collect_event_context -> synthesize_answer` |
| `event_context_answer` | 红海局势升级对 A 股哪些板块有影响 | 是 | 视情况 | 否 | 否 | `collect_event_context -> synthesize_answer` |
| `target_discovery` | 红海局势升级利好哪些 A 股航运股 | 是 | 是 | 是 | 是 | `collect_event_context -> analyze_targets -> retrieve_evidence -> synthesize_answer` |
| `disclosure_interpretation` | 宁德时代扩产公告意味着什么 | 否或弱需要 | 是 | 否 | 是 | `collect_event_context -> retrieve_evidence -> synthesize_answer` |
| `disclosure_interpretation` | 某公司业绩预告是否释放积极信号 | 否或弱需要 | 是 | 否 | 是 | `collect_event_context -> retrieve_evidence -> synthesize_answer` |
| `evidence_lookup` | 中远海能受益的依据是什么 | 否 | 否 | 否 | 是 | `retrieve_evidence -> synthesize_answer` |
| `general_finance_qa` | 降息对债市意味着什么 | 否 | 否 | 否 | 否 | `synthesize_answer` |

## 13. 用这份文档看后续改造时，只需要先回答 4 个问题

1. 这条 query 到底是在要数值、背景、板块、标的，还是证据？
2. 外部上下文应以新闻为主、公告为主，还是双源都要？
3. 这次是否真的需要 `analyze_targets`？
4. 这次最终应给 LLM 喂的是事件摘要、公司证据，还是两者都要？

只要这 4 个问题先答清楚，stage 编排就不容易再失控。
