# FinSight V1 共享 Contract 文档

日期：2026-06-24
状态：生效中
适用范围：FinSight Agent V1 并行开发

## 1. 文档目的

这份文档是 FinSight Agent V1 跨模块共享对象的单一事实来源。

它回答 5 个问题：

- 这个对象叫什么
- 谁拥有它的语义主权
- 谁生产它、谁消费它
- 哪些字段是必填的
- 降级时这个对象应该如何表达

本文件不替代各 capability spec 的业务 requirement。它只负责统一跨模块接口口径，降低并行开发中的联调歧义。

## 2. 统一约定

### 2.1 字段约定

- 所有共享对象默认采用 JSON 可序列化结构
- 字段命名优先使用 `snake_case`
- 所有对象都允许包含 `version` 字段，V1 固定为 `v1`
- 所有对象都允许包含 `notes` 或 `debug_meta` 作为可选调试信息，但下游不得依赖它们作为核心逻辑字段

### 2.2 状态约定

- `success`：对象已完整满足当前阶段主用途
- `partial`：对象可继续被消费，但信息不完整
- `degraded`：对象只能支持降级推进或有限展示
- `failed`：对象未能产出可继续消费的主结果

### 2.3 变更约定

- required field 变更必须经过该对象 owner 审核
- 新增 optional field 可以先局部试用，但不得要求下游立即依赖
- 破坏性变更必须在评审中明确影响 producer 和 consumer

## 3. 对象目录总览

| 对象 | Owner | 主要 Producer | 主要 Consumer |
| --- | --- | --- | --- |
| `RouterResult` | `semantic-routing-and-planning` | router | planner, orchestrator, trace |
| `Plan` | `semantic-routing-and-planning` | planner | orchestrator, trace |
| `SessionContext` | `conversation-session-state` | session manager | router, planner, workbench |
| `StageObservation` | `event-analysis-orchestration` | orchestrator | report, trace, session |
| `EvidenceBundle` | `evidence-retrieval-pipeline` | retrieval pipeline | report, critic, trace |
| `FinalResponse` | `report-trace-and-evaluation` | report generator | workbench, evaluation |
| `TraceBlock` | `report-trace-and-evaluation` | report/trace layer | workbench, evaluation |
| `GuardrailOrErrorResponse` | `report-trace-and-evaluation` | report/response layer | workbench, evaluation |
| `AnalysisRequest` | `workbench-backend-api-boundary` | workbench client | backend API |
| `AnalysisResponseEnvelope` | `workbench-backend-api-boundary` | backend API | workbench client |

## 4. `RouterResult`

### 4.1 Owner / Producer / Consumer

- Owner：`semantic-routing-and-planning`
- Producers：router
- Consumers：planner、orchestrator、trace layer

### 4.2 必填字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `version` | string | contract 版本，V1 固定为 `v1` |
| `intent` | string | 当前轮次的主任务类型，V1 推荐值见 4.3 |
| `follow_up_type` | string | 当前轮次与历史轮次的关系 |
| `confidence` | string | 路由置信度，建议 `high / medium / low` |
| `entities` | object | 提取出的核心语义对象 |
| `needs` | array | 本轮需要调用的能力标签 |
| `constraints` | object | 执行约束，如时间、范围、输出偏好 |

### 4.3 V1 intent 枚举

- `metric_lookup`：单个结构化事实查询，例如某公司某年净利润、营收或行业归属
- `event_impact_analysis`：围绕某个事件分析其可能影响的主题、行业或公司
- `evidence_lookup`：围绕已知公司、候选对象或 claim 查找支持证据
- `out_of_scope`：当前 V1 不支持的问题

### 4.4 降级语义

- 当用户问题超范围时，`intent` 必须为 `out_of_scope`
- 当历史上下文不足时，`follow_up_type` 可以保守回退为 `none` 或 `redirect`
- 不允许在 `confidence=low` 时伪装为高确定性正常路由

### 4.5 Mock Payload：事件影响分析

```json
{
  "version": "v1",
  "intent": "event_impact_analysis",
  "follow_up_type": "none",
  "confidence": "high",
  "entities": {
    "event": "红海航运扰动",
    "themes": ["航运", "油运"],
    "time_scope": "近期"
  },
  "needs": ["news_search", "concept_mapping", "rag_retrieval"],
  "constraints": {
    "time_hint": "recent",
    "preferred_output": "report"
  }
}
```

### 4.6 Mock Payload：简单结构化查询

```json
{
  "version": "v1",
  "intent": "metric_lookup",
  "follow_up_type": "none",
  "confidence": "high",
  "entities": {
    "company": "宁德时代",
    "metric": "net_profit",
    "time_scope": "2024_annual"
  },
  "needs": ["structured_data_query"],
  "constraints": {
    "preferred_output": "brief_answer"
  }
}
```

## 5. `Plan`

### 5.1 Owner / Producer / Consumer

- Owner：`semantic-routing-and-planning`
- Producers：planner
- Consumers：orchestrator、trace layer

### 5.2 必填字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `version` | string | contract 版本 |
| `plan_id` | string | 计划唯一标识 |
| `intent` | string | 与 `RouterResult.intent` 对齐 |
| `stages` | array | 有序阶段列表，允许长路径与短路径 |
| `stage_constraints` | object | 分阶段执行约束 |
| `response_mode` | string | 最终响应模式，如 `report / brief_answer` |

### 5.3 V1 阶段约定

- `event_impact_analysis` 默认走四阶段主链路：`collect_event_context`、`analyze_targets`、`retrieve_evidence`、`synthesize_report`
- `evidence_lookup` 允许跳过 `collect_event_context` 和 `analyze_targets`
- `metric_lookup` 允许使用短路径：`query_structured_data`、`synthesize_brief_answer`
- 顶层 `stages` 只能从当前 V1 已约定的阶段名中取值，不允许临时发明新的顶层阶段

### 5.4 降级语义

- 超范围任务不生成常规四阶段计划
- 允许生成缩减版计划，但必须显式说明跳过了哪些阶段
- 不允许把局部 step 内部动作伪装成顶层 stage

### 5.5 Mock Payload：事件影响分析

```json
{
  "version": "v1",
  "plan_id": "plan_001",
  "intent": "event_impact_analysis",
  "stages": [
    "collect_event_context",
    "analyze_targets",
    "retrieve_evidence",
    "synthesize_report"
  ],
  "stage_constraints": {
    "collect_event_context": {
      "time_hint": "recent",
      "retrieval_budget": 3
    },
    "retrieve_evidence": {
      "retrieval_budget": 4
    }
  },
  "response_mode": "report"
}
```

### 5.6 Mock Payload：简单结构化查询快路径

```json
{
  "version": "v1",
  "plan_id": "plan_002",
  "intent": "metric_lookup",
  "stages": [
    "query_structured_data",
    "synthesize_brief_answer"
  ],
  "stage_constraints": {
    "query_structured_data": {
      "time_hint": "2024_annual"
    },
    "synthesize_brief_answer": {
      "preferred_output": "brief_answer"
    }
  },
  "response_mode": "brief_answer"
}
```

## 6. `SessionContext`

### 6.1 Owner / Producer / Consumer

- Owner：`conversation-session-state`
- Producers：session manager
- Consumers：router、planner、workbench

### 6.2 必填字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `version` | string | contract 版本 |
| `session_id` | string | 会话标识 |
| `active_topic` | string | 当前有效主题 |
| `active_candidates` | array | 当前活跃候选对象 |
| `key_evidence_refs` | array | 当前有效关键证据引用 |
| `history_summary` | string | 压缩后的历史摘要 |
| `available_follow_ups` | array | 当前允许的追问方向 |

### 6.3 降级语义

- 当历史丢失时，必须显式返回缺失状态，而不是拼凑不存在的上下文
- `history_summary` 可以为空，但必须说明原因

### 6.4 Mock Payload

```json
{
  "version": "v1",
  "session_id": "sess_001",
  "active_topic": "红海航运扰动对 A 股航运链的影响",
  "active_candidates": ["中远海能", "招商轮船"],
  "key_evidence_refs": ["ev_001", "ev_007"],
  "history_summary": "上一轮已完成事件背景分析与候选标的初筛。",
  "available_follow_ups": ["drilldown", "compare", "expand"]
}
```

## 7. `StageObservation`

### 7.1 Owner / Producer / Consumer

- Owner：`event-analysis-orchestration`
- Producers：orchestrator
- Consumers：report、trace、session

### 7.2 必填字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `version` | string | contract 版本 |
| `observation_id` | string | observation 标识 |
| `stage_name` | string | 阶段名称 |
| `status` | string | `success / partial / degraded / failed` |
| `input_summary` | object | 输入摘要 |
| `key_outputs` | object | 阶段关键输出 |
| `confidence_signals` | object | 置信度信号 |
| `evidence_refs` | array | 相关证据引用 |

### 7.3 降级语义

- `status=degraded` 时必须补充阻塞原因
- `status=partial` 时必须说明哪些结果仍可继续消费

### 7.4 Mock Payload

```json
{
  "version": "v1",
  "observation_id": "obs_001",
  "stage_name": "collect_event_context",
  "status": "success",
  "input_summary": {
    "query": "红海事件利好哪些 A 股公司"
  },
  "key_outputs": {
    "event_summary": "红海航运扰动抬升了部分航运链运价预期。"
  },
  "confidence_signals": {
    "context_confidence": "medium"
  },
  "evidence_refs": ["news_001", "news_002"]
}
```

## 8. `EvidenceBundle`

### 8.1 Owner / Producer / Consumer

- Owner：`evidence-retrieval-pipeline`
- Producers：retrieval pipeline
- Consumers：report、critic、trace

### 8.2 必填字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `version` | string | contract 版本 |
| `bundle_id` | string | bundle 标识 |
| `target_ref` | string | 被验证对象 |
| `claim` | string | 当前要支撑的判断 |
| `support_strength` | string | `strong / partial / weak` |
| `evidence_items` | array | 证据片段列表 |
| `retrieval_notes` | object | 检索过程备注 |

### 8.3 降级语义

- 证据不足时必须使用 `partial` 或 `weak`
- 不允许用“有引用”伪装成“已验证”

### 8.4 Mock Payload

```json
{
  "version": "v1",
  "bundle_id": "bundle_001",
  "target_ref": "中远海能",
  "claim": "公司可能受益于航运景气提升",
  "support_strength": "partial",
  "evidence_items": [
    {
      "source_id": "annual_report_2025",
      "excerpt": "公司主营油运与能源运输业务。",
      "parent_ref": "parent_001"
    }
  ],
  "retrieval_notes": {
    "dense_hits": 6,
    "sparse_hits": 9
  }
}
```

## 9. `FinalResponse`

### 9.1 Owner / Producer / Consumer

- Owner：`report-trace-and-evaluation`
- Producers：report generator
- Consumers：workbench、evaluation

### 9.2 必填字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `version` | string | contract 版本 |
| `response_type` | string | `success / degraded / guardrail / error` |
| `session_id` | string | 会话标识 |
| `summary` | string | 结论摘要 |
| `report_blocks` | array | 报告区块 |
| `uncertainty_notes` | array | 不确定性说明 |
| `next_actions` | array | 建议下一步 |

### 9.3 降级语义

- `response_type=degraded` 时 `summary` 仍需可读
- 不允许把空响应包装成成功响应

### 9.4 Mock Payload

```json
{
  "version": "v1",
  "response_type": "success",
  "session_id": "sess_001",
  "summary": "航运链条受益方向更明确，候选对象应先聚焦油运与航运运营商。",
  "report_blocks": [
    {
      "title": "候选方向",
      "content": "优先关注油运与航运运营商。"
    }
  ],
  "uncertainty_notes": [
    "当前结论主要依赖事件背景和有限年报证据。"
  ],
  "next_actions": [
    "继续 drilldown 单家公司公告证据"
  ]
}
```

## 10. `TraceBlock`

### 10.1 Owner / Producer / Consumer

- Owner：`report-trace-and-evaluation`
- Producers：report/trace layer
- Consumers：workbench、evaluation

### 10.2 必填字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `version` | string | contract 版本 |
| `block_type` | string | 如 `routing`、`planning`、`retrieval` |
| `title` | string | 展示标题 |
| `status` | string | 当前 trace 状态 |
| `payload_summary` | object | 摘要化 payload |
| `raw_refs` | array | 原始对象引用 |

### 10.3 降级语义

- 降级轮次必须至少有一个 trace block 说明停止位置和原因

### 10.4 Mock Payload

```json
{
  "version": "v1",
  "block_type": "routing",
  "title": "路由结果",
  "status": "success",
  "payload_summary": {
    "intent": "event_impact_analysis",
    "follow_up_type": "none"
  },
  "raw_refs": ["router_result_001"]
}
```

## 11. `GuardrailOrErrorResponse`

### 11.1 Owner / Producer / Consumer

- Owner：`report-trace-and-evaluation`
- Producers：report/response layer
- Consumers：workbench、evaluation

### 11.2 必填字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `version` | string | contract 版本 |
| `response_type` | string | 固定为 `guardrail` 或 `error` |
| `reason_code` | string | 阻塞原因代码 |
| `progress_state` | string | 当前推进到哪一步 |
| `partial_answer` | string | 当前还能给出的部分结论 |
| `suggested_next_actions` | array | 用户下一步建议 |
| `trace_refs` | array | 相关 trace 引用 |

### 11.3 降级语义

- `error` 不等于“无信息”，仍需保留用户可读解释
- `guardrail` 不等于“拒绝回答”，应说明当前可推进边界

### 11.4 Mock Payload

```json
{
  "version": "v1",
  "response_type": "guardrail",
  "reason_code": "insufficient_event_context",
  "progress_state": "collect_event_context",
  "partial_answer": "当前只能判断航运链条可能相关，但无法稳定收敛到公司级结论。",
  "suggested_next_actions": [
    "补充更具体的事件名称或时间范围"
  ],
  "trace_refs": ["trace_guardrail_001"]
}
```

## 12. 当前并行开发使用规则

- 下游团队只允许依赖本文列出的 required fields
- optional field 可以补充，但不得成为联调前置条件
- 如果某对象 mock payload 已冻结，下游可以先基于 mock 开发
- 如果 required field 尚未冻结，该对象不能视为 `contract ready`
