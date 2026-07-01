# Session Context Follow-up Implementation Plan

日期：2026-07-01  
状态：已完成

## 1. 目标

基于 `Session Context Follow-up Design` 落地首版会话短期记忆闭环：

- 让统一后端入口在 follow-up 请求中真实加载 `SessionContext`
- 让首轮和后续轮次都能把最近 1 个有效 turn snapshot 写回本地持久化
- 让 router 在真实 API 路径下消费会话上下文，而不再只依赖单测构造
- 以结构化执行产物抽取 `SessionContext`，不引入 LLM 作为主抽取器
- 首版使用文件型 `SessionRepository`，不引入数据库依赖

## 2. 设计决策摘要

本计划实现时需要坚持以下决策：

- 内部持久化对象使用 `SessionSnapshot`
- 共享给 router / planner / workbench 的对象仍然是 `SessionContext`
- 首版只保留最近 1 个有效 turn snapshot
- `SessionContext` 由结构化 extractor 生成
- 统一入口负责 session 的 load / save 生命周期
- 历史缺失时保守回退为 `session_context=None`
- 首版 repository 使用本地 JSON 文件，不引入 sqlite 或其他数据库

## 3. 预计改动文件

### 新增文件

- `backend/src/finsight_agent/control_plane/session/models.py`
  - 定义 `SessionSnapshot`
- `backend/src/finsight_agent/control_plane/session/extractor.py`
  - 从结构化执行产物抽取 `SessionContext`
- `tests/unit/test_session_context_extractor.py`
  - 覆盖字段提取规则
- `tests/unit/test_session_repository.py`
  - 覆盖文件型存取与缺失降级
- `tests/unit/test_workbench_session_flow.py`
  - 覆盖统一入口的 session load/save 闭环

### 修改文件

- `backend/src/finsight_agent/control_plane/session/repository.py`
  - 从占位文件实现为文件型 repository
- `backend/src/finsight_agent/control_plane/session/service.py`
  - 从骨架实现为统一入口可消费的 session service
- `backend/src/finsight_agent/control_plane/session/compressor.py`
  - 补入模板化 `history_summary` 生成逻辑
- `backend/src/finsight_agent/workbench_backend_api/service.py`
  - 接入 session load / save 生命周期
- `tests/integration/test_metric_lookup_placeholder.py`
  - 调整或补充首轮 / follow-up API 路径的 session 断言
- `tests/unit/test_project_skeleton.py`
  - 补充 session 模块文件存在性与基础导入验证

## 4. 任务拆分

### Task 1：建立 `SessionSnapshot` 模型与文件型 repository

目标：

- 把 `control_plane/session/` 从占位骨架变成最小可用的存储层
- 明确首版持久化不是数据库，而是本地 JSON 文件

实施内容：

- 新增 `SessionSnapshot`
- 实现 `SessionRepository.load(session_id)` / `save(snapshot)`
- 约定本地存储目录，例如 `runtime/session_state/`
- 每个 session 一个 JSON 文件

关键要求：

- 查不到文件时返回 `None`
- 不伪造空 snapshot
- 读写路径可通过构造参数注入，便于单测使用临时目录

建议测试：

- `test_repository_returns_none_when_snapshot_missing`
- `test_repository_can_save_and_load_snapshot`
- `test_repository_overwrites_same_session_id_snapshot`

### Task 2：实现结构化 `SessionContextExtractor`

目标：

- 从已有结构化执行产物中稳定生成 `SessionContext`
- 不依赖 LLM 自由总结

实施内容：

- 新增 `SessionContextExtractor`
- 输入至少支持：
  - `AnalysisRequest`
  - `RouterResult`
  - `Plan`
  - `OrchestrationResult`
- 输出：
  - `SessionContext`
  - 或直接辅助构造 `SessionSnapshot`

字段规则：

- `active_topic`
  - 按 `intent + entities + summary` 模板化生成
- `active_candidates`
  - 从 `router_result.entities`、`final_response.report_blocks`、evidence target 里抽取
  - 最多保留前 3 个
- `key_evidence_refs`
  - 从 retrieval/evidence 结果中抽取
  - 最多保留前 5 个
- `history_summary`
  - 模板化 1 到 2 句
- `available_follow_ups`
  - 规则生成，不使用模型

建议测试：

- `test_extractor_builds_metric_lookup_context`
- `test_extractor_builds_evidence_lookup_context`
- `test_extractor_limits_candidate_and_evidence_counts`
- `test_extractor_handles_missing_fields_with_partial_degrade`

### Task 3：补全 session service，编排 load / save 生命周期

目标：

- 让统一入口能通过一个明确的 session service 读写快照

实施内容：

- 在 `control_plane/session/service.py` 实现：
  - `load_context(session_id) -> SessionContext | None`
  - `build_or_update_snapshot(...) -> SessionSnapshot | None`
  - `save_snapshot(snapshot) -> None`
- 内部组合 `SessionRepository` 与 `SessionContextExtractor`

关键要求：

- 只有在能形成稳定结果时才更新 snapshot
- `out_of_scope` 不覆盖已有有效上下文
- 不完整字段按字段级降级，而不是整体抛弃

建议测试：

- `test_load_context_returns_none_for_missing_session`
- `test_service_builds_snapshot_from_successful_turn`
- `test_service_skips_overwrite_for_out_of_scope_turn`
- `test_service_does_not_overwrite_on_unrecoverable_failure`

### Task 4：把 session 生命周期接入 `WorkbenchBackendApiService`

目标：

- 让统一入口真实消费 session，而不是只透传 `session_id`

实施内容：

- 在 `WorkbenchBackendApiService.__init__` 中注入 `SessionService`
- 请求进入时：
  - 生成或读取 `session_id`
  - 加载 `SessionContext`
  - 传给 `RouterService.route(...)`
- 请求结束时：
  - 根据 `request`、`router_result`、`plan`、`orchestration_result` 构造 snapshot
  - 保存 snapshot

关键要求：

- 首轮请求无 `session_id` 时生成稳定 id
- follow-up 请求有 `session_id` 时优先复用
- 历史不存在时按 `session_context=None` 降级

建议测试：

- `test_workbench_generates_session_id_for_first_turn`
- `test_workbench_loads_existing_session_context_for_follow_up`
- `test_workbench_saves_snapshot_after_successful_turn`
- `test_workbench_degrades_when_session_snapshot_missing`

### Task 5：补充统一入口和集成路径验证

目标：

- 证明真实 API 路径下，session 已经不是“只在单测里存在的假对象”

实施内容：

- 调整现有 integration test 或补新集成测试
- 至少覆盖：
  - first turn 生成 session
  - follow-up 复用 session
  - evidence follow-up 可从历史上下文继承 target 或 topic

建议测试：

- `test_first_turn_persists_session_snapshot`
- `test_follow_up_request_uses_persisted_session_context`
- `test_follow_up_without_snapshot_degrades_without_fabricating_history`

### Task 6：同步状态文档与实现计划状态

目标：

- 在实现完成后同步文档口径

实施内容：

- 更新：
  - `docs/finsight/project-status.md`
  - `docs/finsight/modules/control-plane-status.md`
  - `docs/finsight/modules/data-evidence-status.md`
  - 本计划文档状态

更新重点：

- `conversation-session-state` 从“未开始”推进到“首版已接线”
- evidence follow-up 在线链路 blocker 变化
- 下一阶段未完成事项，例如 richer rolling summary 或 event follow-up 深化

## 5. 测试策略

首版建议按三层测试推进：

### 单元测试

- `SessionRepository`
- `SessionContextExtractor`
- `SessionService`
- `WorkbenchBackendApiService` 的 session 分支逻辑

### 集成测试

- 统一 API 首轮 -> 写入 snapshot
- 统一 API follow-up -> 读取 snapshot -> router 使用上下文

### 回归关注点

- 不能破坏现有 `metric_lookup` 快路径
- 不能破坏现有 `evidence_lookup` 主路径
- 不能让缺失 snapshot 的 follow-up 变成伪造上下文

## 6. 风险与实现注意事项

### 风险 1：把 session 逻辑塞进 orchestrator

应避免：

- 在 orchestrator 内部直接 load/save session
- 让 stage runner 直接持有 repository

因为 session 主权应留在统一入口与 session service。

### 风险 2：过早引入数据库

应避免：

- 为首版 snapshot 引入 sqlite schema、migration 或复杂事务逻辑

因为当前需求只需要按 `session_id` 读取最近 1 条 snapshot，本地 JSON 文件足够支撑。

### 风险 3：让 LLM 成为唯一抽取器

应避免：

- 直接把整轮 request/response 丢给 LLM 生成 `SessionContext`

因为这会降低可测性，并带来历史幻造风险。

## 7. 验收标准

本计划完成后，应达到以下效果：

1. 首轮请求能生成并持久化 `SessionSnapshot`
2. follow-up 请求能真实加载 `SessionContext`
3. router 的 follow-up 判别开始在线上真实消费 session
4. evidence follow-up 能在真实 API 路径下复用上一轮上下文
5. 历史缺失时系统不会伪造会话上下文
6. 首版不引数据库，仍可稳定完成本地闭环

## 8. 后续建议

在本计划完成后，可按优先级继续推进：

1. 把 `history_summary` 从模板化摘要演进为 `rolling_summary`
2. 让 planner 在部分 follow-up 场景也显式消费 session 衍生约束
3. 评估是否需要记录最近 2 到 3 轮 turn snapshots
4. 等会话分析需求变复杂后，再考虑 sqlite 或更正式的存储层

## 9. 实际完成情况

- 已新增 `SessionSnapshot` 与文件型 `SessionRepository`
- 已实现结构化 `SessionContextExtractor`
- 已实现首版 `SessionService`
- 已将 session load / save 生命周期接入 `WorkbenchBackendApiService`
- 已让真实 API 路径支持首轮 snapshot 持久化与 follow-up 上下文复用
- 已保持现有 `metric_lookup` / `evidence_lookup` / orchestrator 回归通过

## 10. 本轮验证

已通过的关键验证命令：

- `python -m unittest tests.unit.test_session_repository tests.unit.test_session_context_extractor tests.unit.test_workbench_session_flow tests.unit.test_project_skeleton tests.integration.test_metric_lookup_placeholder -v`
- `python -m unittest tests.unit.test_semantic_routing_and_planning tests.unit.test_orchestrator_service tests.unit.test_orchestrator_stage_runners tests.unit.test_trace_builder tests.unit.test_session_repository tests.unit.test_session_context_extractor tests.unit.test_workbench_session_flow tests.unit.test_project_skeleton tests.integration.test_metric_lookup_placeholder -v`

最终结果：

- 61 个相关测试全部通过
- 统一入口的真实 follow-up 路径已开始消费 `SessionContext`
