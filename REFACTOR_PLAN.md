# FinSight 控制面重构改动清单

日期：2026-07-09
状态：待执行
范围：删 planner、合并 synthesize_*、新增 general_finance_qa 轻路径、收紧 out_of_scope

## 0. 目标态

```
router → classifier（仅 event 触发）→ orchestrator（查表 + 执行）
```

- router 只做意图识别，输出 `intent` + `entities` + `constraints` + `needs`
- classifier 只对 `event_impact_analysis` 做 strategy 三分类，非 event 类不经过
- orchestrator 内置 `(intent, strategy) → (stages, stage_constraints)` 查表函数，吸收原 planner 职责
- 删除 `PlannerService` / `Plan` 契约 / LLM planner / rule planner
- `synthesize_brief_answer` / `synthesize_event_answer` / `synthesize_report` 合并为 `synthesize_answer`，按 `response_mode` 切换 prompt 模板
- 新增 `general_finance_qa` intent + `direct` response_mode，承接泛财经常识问题，LLM 直答不走检索
- 收紧 `out_of_scope` 判定，泛财经问题不再被打成 out_of_scope

最终 stage 清单（6 个）：

```
query_structured_data
collect_event_context
analyze_targets
retrieve_evidence
synthesize_answer
（guardrail 短路，不算 stage）
```

最终 (intent, strategy) → stages 映射：

| intent | strategy | stages | response_mode |
| --- | --- | --- | --- |
| `metric_lookup` | - | `query_structured_data → synthesize_answer` | `brief_answer` |
| `general_finance_qa` | - | `synthesize_answer` | `direct` |
| `event_impact_analysis` | `event_primary` | `collect_event_context → synthesize_answer` | `event_answer` |
| `event_impact_analysis` | `disclosure_primary` | `collect_event_context → retrieve_evidence → synthesize_answer` | `report` |
| `event_impact_analysis` | `dual_primary` | `collect_event_context → analyze_targets → retrieve_evidence → synthesize_answer` | `report` |
| `evidence_lookup` | - | `retrieve_evidence → synthesize_answer` | `report` |
| `out_of_scope` | - | guardrail 短路 | - |

## 1. shared 层契约改动

### 1.1 新增

- `shared/enums/intent.py` 新增 `GENERAL_FINANCE_QA = "general_finance_qa"`
- `shared/enums/response_mode.py` 新增：
  - `EVENT_ANSWER = "event_answer"`
  - `DIRECT = "direct"`
- `shared/enums/stage_name.py` 新增 `SYNTHESIZE_ANSWER = "synthesize_answer"`

### 1.2 删除

- `shared/contracts/plan.py` 整文件删除
- `shared/enums/stage_name.py` 删除：
  - `SYNTHESIZE_BRIEF_ANSWER`
  - `SYNTHESIZE_EVENT_ANSWER`
  - `SYNTHESIZE_REPORT`
- `shared/enums/response_mode.py` 保留 `REPORT` / `BRIEF_ANSWER`，新增 `EVENT_ANSWER` / `DIRECT`（不删除旧值）

### 1.3 调整

- `shared/contracts/final_response.py` 不动（契约保留，但 reporting 层会变轻使用）
- `shared/contracts/router_result.py` 不动（字段不变）
- `shared/contracts/analysis_request.py` / `analysis_response_envelope.py` 不动

## 2. router 层改动

### 2.1 `backend/src/finsight_agent/control_plane/router/rules.py`

- `route_with_rules` 新增 `general_finance_qa` 分支：
  - 判别条件：金融领域 query 但不属于 metric / event / evidence 任一类型
  - 保守 fallback：出现具体公司名 + 财务词 → 仍走 `metric_lookup`；出现"某公司公告/业绩预告"字样 → 仍走 `event_impact_analysis`
- `_is_out_of_scope` 收紧：
  - 只保留真正不支持的场景：非金融问题、投资建议/荐股、恶意 query
  - 删除"未被前面规则命中就走 out_of_scope"的兜底逻辑，改为"未被命中走 general_finance_qa"
- 抽取 `_extract_topics` 用于 general_finance_qa 的 entities.topics 字段
- 删除 `reason_code: unsupported_request_shape` 兜底分支

### 2.2 `backend/src/finsight_agent/control_plane/router/llm.py`

- LLM router 的 prompt / schema 同步新增 `general_finance_qa` intent 选项
- LLM router 失败时 fallback 到规则，规则已支持 general_finance_qa

### 2.3 `backend/src/finsight_agent/control_plane/router/prompts/system.txt`

- system prompt 补充 general_finance_qa 的判别说明和示例

### 2.4 `backend/src/finsight_agent/control_plane/router/service.py`

- 无需改动（service 层只是组合 rules + llm）

## 3. planner 层改动（整体删除）

### 3.1 删除整个目录

- `backend/src/finsight_agent/control_plane/planner/` 整目录删除
  - `service.py` / `rules.py` / `llm.py` / `schema.py`
  - `prompts/system.txt`
  - `examples/`（若存在）

### 3.2 保留的能力迁移

原 `build_plan_with_rules` 里的 stage 编排逻辑迁移到 orchestrator 层（见 §4.1），具体包括：

- `metric_lookup` → `[query_structured_data, synthesize_answer]` + stage_constraints
- `event_impact_analysis` 按 strategy 分叉的三套 stages
- `evidence_lookup` → `[retrieve_evidence, synthesize_answer]` + stage_constraints
- `out_of_scope` → guardrail 短路标记
- 新增 `general_finance_qa` → `[synthesize_answer]` + `response_mode=direct`

原 `stage_constraints` 里的 `retrieval_budget` / `time_hint` / `target_scope` / `strategy` / `strategy_confidence` / `strategy_reason` / `preferred_output` 等字段全部平移到 orchestrator 查表函数的输出。

### 3.3 删除 LLM planner 能力

- `build_plan_with_llm` / `_reconcile_llm_plan` / `_merge_stage_constraints` / `_is_safe_constraint_override` 全部删除
- `feature_flags.llm_planner_enabled` 删除
- 环境变量 `FINSIGHT_LLM_PLANNER_ENABLED` 废弃

## 4. orchestrator 层改动

### 4.1 新增 stage 映射表

新建 `backend/src/finsight_agent/control_plane/orchestrator/stage_planner.py`：

```python
def resolve_stages(
    router_result: RouterResult,
    strategy_payload: dict[str, str] | None,
) -> tuple[list[str], dict[str, dict[str, object]], str]:
    """(intent, strategy) → (stages, stage_constraints, response_mode)"""
```

- 输入：`RouterResult` + `strategy_payload`
- 输出：`stages` 列表 + `stage_constraints` 字典 + `response_mode`
- 逻辑平移自 `planner/rules.py` 的 `build_plan_with_rules`
- 新增 `general_finance_qa` 分支返回 `[synthesize_answer]` + `response_mode=direct`

### 4.2 `orchestrator/service.py` 改造

- `OrchestratorService.execute` 签名改为接收 `stages` + `stage_constraints`，不再接收 `Plan`
- 内部 `for stage_name in plan.stages` 改为 `for stage_name in stages`
- `plan.stage_constraints.get(stage_name, {})` 改为 `stage_constraints.get(stage_name, {})`
- `result.trace_blocks.append(build_execution_trace_block(result))` 不动
- 删除对 `Plan` 的所有引用

### 4.3 `orchestrator/stage_runners/__init__.py` 改造

- 删除 `synthesize_brief_answer` / `synthesize_event_answer` / `synthesize_report` 三个 runner 的导出
- 新增 `synthesize_answer` runner 导出
- `STAGE_RUNNERS` 字典更新为 6 个 stage

### 4.4 stage_runners 合并

#### 删除

- `stage_runners/synthesize_brief_answer.py`
- `stage_runners/synthesize_event_answer.py`
- `stage_runners/synthesize_report.py`

#### 新增 `stage_runners/synthesize_answer.py`

```python
def run_synthesize_answer_stage(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object] | None,
    execution_state: dict[str, StageExecutionResult],
    reporting_service: ReportingService,
) -> StageExecutionResult:
    response_mode = str((stage_constraints or {}).get("response_mode") or "brief_answer")
    # 按 response_mode 分支：
    #   direct       → 只用 query + router entities，不读 execution_state
    #   brief_answer → 读 query_structured_data 结果
    #   event_answer → 读 collect_event_context 结果
    #   report       → 读 retrieve_evidence + analyze_targets + collect_event_context 结果
    # 统一调 reporting_service.build_response(response_mode=...)
```

- `response_mode` 从 `stage_constraints` 读取（由 stage_planner 写入）
- 4 种分支的 context 组装逻辑分别平移自原 3 个 runner + 新增 direct 分支
- 统一返回 `StageExecutionResult(output_payload={"final_response": ...})`

### 4.5 `orchestrator/policies.py` 不动

- `should_short_circuit` 仍只对 `out_of_scope` 短路
- `build_guardrail_response` 不动

### 4.6 `orchestrator/trace_builder.py` 调整

- 删除对 `Plan` 的引用
- trace block 里原本展示 `plan_id` / `stages` 的位置改为展示 `stages` + `response_mode`

## 5. workbench_backend_api 层改动

### 5.1 `workbench_backend_api/service.py` 改造

- 删除 `PlannerService` import 和依赖注入
- 删除 `self._planner_service` 字段
- `_execute_request` 流程改为：
  ```
  router_result = router_service.route(...)
  strategy_payload = classify_event_strategy(...)   # 仅 event 触发
  stages, stage_constraints, response_mode = stage_planner.resolve_stages(
      router_result, strategy_payload
  )
  orchestration_result = orchestrator_service.execute(
      request=...,
      router_result=router_result,
      stages=stages,
      stage_constraints=stage_constraints,
      session_context=session_context,
      event_callback=event_callback,
  )
  ```
- trace block 里 `planning` 块的 payload 改为展示 `stages` + `response_mode` + `strategy`，不再展示 `plan_id`
- 删除对 `Plan` / `plan` 的所有引用

### 5.2 `_classify_event_strategy` 不动

- classifier 调用逻辑保留
- 仅 `event_impact_analysis` 触发，其他 intent 返回 None

## 6. reporting 层改动

### 6.1 `capabilities/reporting/service.py` 改造

- 新增统一入口 `build_response(response_mode: str, session_id: str, context: dict) -> FinalResponse`
- 内部按 `response_mode` 分支：
  - `direct` → 调 `final_answer_writer` 用 direct prompt，`report_blocks=[]`
  - `brief_answer` → 调 `final_answer_writer` 用 brief prompt，`report_blocks=[]`
  - `event_answer` → 调 `final_answer_writer` 用 event prompt，`report_blocks=[]`
  - `report` → 调 `final_answer_writer` 用 report prompt + 拼 `report_blocks`
- 保留 `build_brief_response` / `build_report_response` 作为内部 helper（或直接删除，统一走 `build_response`）
- `_fallback_answer_markdown` 保留，但 fallback 输出变轻：不再强制拼 "Notes:" / "Next:" 空话

### 6.2 `capabilities/reporting/final_answer_writer.py` 改造

- `write_answer` 新增 `prompt_name` 参数（或 `response_mode` 参数），按模式选择不同 system prompt
- `LlmClient.complete_json` 的 `prompt_name` 按 response_mode 区分

### 6.3 `capabilities/reporting/prompts/` 新增

- `prompts/system.txt` 保留为共用 base system prompt（角色、边界、风格）
- 新增：
  - `prompts/direct_answer.txt` — 泛财经常识直答，不引用证据
  - `prompts/brief_answer.txt` — 指标类简短答复
  - `prompts/event_answer.txt` — 事件类答复，基于 event_context
  - `prompts/report_answer.txt` — 证据型报告，基于 evidence_items + event_context

每个 prompt 模板明确：
- 输入字段
- 输出格式（`answer_markdown` + 可选 `answer_confidence`）
- 风格约束（不编造数字、不编造公司名、证据不足时诚实标注）

## 7. feature_flags 改动

### 7.1 `config/feature_flags.py`

- 删除 `llm_planner_enabled`
- 保留 `llm_router_enabled`

## 8. config 改动

### 8.1 `config/app.yaml`

- `control_plane.prompts.planner_system_prompt_path` 删除
- 新增 `reporting.prompts` 下的多模板路径：
  ```yaml
  reporting:
    prompts:
      final_answer_writer_system_prompt_path: prompts/system.txt
      direct_answer_prompt_path: prompts/direct_answer.txt
      brief_answer_prompt_path: prompts/brief_answer.txt
      event_answer_prompt_path: prompts/event_answer.txt
      report_answer_prompt_path: prompts/report_answer.txt
  ```

### 8.2 `backend/src/finsight_agent/config/settings.py`

- 删除 `planner_system_prompt_path` 字段
- 新增 `direct_answer_prompt_path` / `brief_answer_prompt_path` / `event_answer_prompt_path` / `report_answer_prompt_path` 字段

## 9. fixtures 改动

### 9.1 `fixtures/contracts/plan.metric_lookup.json`

- 删除（Plan 契约已废弃）

### 9.2 新增 fixtures

- `fixtures/contracts/router_result.general_finance_qa.json` — general_finance_qa 路由结果样例
- `fixtures/contracts/stage_plan.*.json` — 各 (intent, strategy) 组合的 stages + stage_constraints + response_mode 样例（替代原 plan fixtures）

## 10. tests 改动

### 10.1 删除

- `tests/unit/test_semantic_routing_and_planning.py` 中 planner 相关测试用例删除或重写
- `tests/unit/test_final_answer_writer.py` 中按旧单 prompt 的测试用例调整

### 10.2 新增

- `tests/unit/test_stage_planner.py` — 测试 `resolve_stages` 函数覆盖所有 (intent, strategy) 组合
- `tests/unit/test_router_general_finance_qa.py` — 测试 general_finance_qa 判别和 fallback 逻辑
- `tests/unit/test_synthesize_answer_stage.py` — 测试 4 种 response_mode 分支
- `tests/unit/test_out_of_scope_tightened.py` — 测试泛财经问题不再被 out_of_scope

### 10.3 调整

- `tests/unit/test_orchestrator_service.py` — 改为传 `stages` + `stage_constraints`，不再传 `Plan`
- `tests/unit/test_orchestrator_stage_runners.py` — 删除旧 synthesize_* runner 测试，新增 synthesize_answer 测试
- `tests/unit/test_workbench_session_flow.py` — 删除 plan 相关断言，改为 stages + response_mode 断言
- `tests/integration/test_workbench_end_to_end.py` — 同步调整
- `tests/integration/test_event_analysis_replay_smoke.py` — 同步调整
- `tests/integration/test_event_impact_analysis_flow.py` — 同步调整

## 11. openspec 改动

### 11.1 `openspec/specs/semantic-routing-and-planning/spec.md`

- 重命名 spec 为 `semantic-routing-and-orchestration`（或保留名字但删除 planner 部分）
- 删除所有 planner / Plan 相关 requirement
- 新增 router 输出 general_finance_qa 的 requirement
- 新增 orchestrator stage 查表的 requirement

### 11.2 `openspec/specs/event-analysis-orchestration/spec.md`

- 删除对 Plan 的引用
- stage 列表更新为 6 个
- synthesize_* 合并说明

### 11.3 新增 change proposal

- `openspec/changes/2026-07-09-collapse-planner-and-synthesize-stages/`
  - `proposal.md` — 本次重构动机和范围
  - `design.md` — 删 planner / 合并 synthesize / 加轻路径的设计决策
  - `tasks.md` — 本清单的 openspec 版本
  - `specs/` — 受影响 spec 的 diff

## 12. docs 改动

### 12.1 `docs/finsight/project-status.md`

- 新增里程碑 M12：控制面重构（planner 合并 + 轻路径 + stage 精简）
- 更新当前能力清单：stage 数从 7 → 6，intent 从 4 → 5

### 12.2 `docs/finsight/query-routing-and-stage-flow-business-note.md`

- 删除 §5 "classifier 的位置" 中"位于 planner 之前"的表述
- 改为"位于 router 之后、orchestrator 之前"
- 更新 §11 目标状态：删除 planner 层，更新 stage 体系

### 12.3 `docs/finsight/modules/control-plane-status.md`

- 删除"Router / Planner"小节中 Planner 相关内容
- 改为"Router / Classifier / Orchestrator"三层说明

## 13. 执行顺序建议

按依赖关系分 4 批，每批做完跑一次测试：

### 批次 1：shared 层（契约基础）
1. 新增枚举值（intent / response_mode / stage_name）
2. 删除 `Plan` 契约
3. 删除旧 synthesize stage 枚举
4. 跑测试，预期大量失败（planner / synthesize 相关）

### 批次 2：orchestrator 层（吸收 planner 职责）
5. 新增 `stage_planner.py`（`resolve_stages` 函数）
6. 新增 `synthesize_answer.py` stage runner
7. 改造 `orchestrator/service.py`（接收 stages 而非 Plan）
8. 更新 `stage_runners/__init__.py`
9. 删除旧 3 个 synthesize runner
10. 跑测试，修复 orchestrator 相关失败

### 批次 3：删 planner + 改 workbench 入口
11. 删除 `planner/` 整目录
12. 删除 `feature_flags.llm_planner_enabled`
13. 改造 `workbench_backend_api/service.py`（删 planner 依赖，改用 stage_planner）
14. 删除 `config/app.yaml` 中 planner prompt 路径
15. 跑测试，修复 workbench 相关失败

### 批次 4：新增轻路径 + reporting 多模板
16. 新增 `general_finance_qa` 路由规则
17. 收紧 `out_of_scope` 判定
18. 新增 reporting prompt 模板（direct / brief / event / report）
19. 改造 `reporting/service.py` 和 `final_answer_writer.py` 支持多模板
20. 新增 fixtures
21. 跑全量测试
22. 新增 / 调整单测和集成测试

### 批次 5：文档与 spec
23. 更新 openspec specs
24. 新增 change proposal
25. 更新 docs（project-status / business-note / control-plane-status）

## 14. 风险与回退

### 14.1 主要风险

1. **router 误判 general_finance_qa**：具体公司 + 财务词的 query 被误判为泛财经，导致该走 metric_lookup 的走了 direct。缓解：保守 fallback 规则 + 单测覆盖边界。
2. **synthesize_answer 分支过多**：4 种 response_mode 在单文件内分支，可能变臃肿。缓解：context 组装逻辑抽成 helper，prompt 选择逻辑独立。
3. **Plan 契约删除影响面**：trace block / session snapshot / workbench 前端可能依赖 plan_id 或 plan 结构。缓解：执行前先 grep 全仓 `Plan` / `plan_id` / `planner` 引用。
4. **LLM planner 删除后的能力损失**：当前 LLM planner 实际影响力为零（stages 不一致就退回 rule），删除无实际损失，但要在文档里说明。

### 14.2 回退策略

- 批次 1-3 完成后若测试大面积失败，可回退到 `Plan` 契约 + `PlannerService`，保留 `stage_planner.py` 作为实验
- 批次 4 的轻路径是纯新增，不破坏已有链路，可独立回退
- reporting 多模板改动可独立回退（保留旧的单 prompt 路径）

## 15. 验收标准

执行完成后应满足：

1. `planner/` 目录不存在
2. `shared/contracts/plan.py` 不存在
3. `feature_flags.llm_planner_enabled` 不存在
4. `stage_runners/` 下只有 6 个 stage runner（含 `synthesize_answer`）
5. 新增 `general_finance_qa` intent，泛财经 query 不再被 out_of_scope
6. `out_of_scope` 只对非金融 / 荐股 / 恶意 query 触发
7. `reporting/prompts/` 下有 4 个 response_mode 模板 + 1 个 system.txt
8. 全量测试通过（`pytest tests/`）
9. 工作台可启动（`scripts/run_workbench_backend.py` + streamlit entry）
10. 5 类 query（metric / general / event / evidence / out_of_scope）各能跑通一条 demo

## 16. 不在本次范围

以下事项已讨论但不在本次改动清单内，后续单独评估：

- classifier 是否合并进 router（结论：不合并，保留三层）
- `retrieve_evidence` 空结果时的局部 re-plan loop
- 外部检索（Bocha / CNInfo）的缓存 / 重试 / 熔断
- 回答质量 rubric 评测（建议下一阶段单独做）
- demo 语料扩展（半导体 10 家 → 跨行业覆盖）
- `DualSourceExternalContextRetriever` 升级为并行 agent（LangGraph）
