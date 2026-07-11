## Why

FinSight Agent V1 的控制面在重构前是三层结构 `router → planner → orchestrator`，但 planner 层（[backend/src/finsight_agent/control_plane/planner/](backend/src/finsight_agent/control_plane/planner/)）的实际影响力为零：planner 内部走 LLM 生成 plan，可一旦产出的 stages 与受支持集合不一致就会退回 rule-based 兜底，等于 LLM 分支从未真正生效，却要承担一轮额外的延迟与 prompt 维护成本。与此同时，原 `synthesize_brief_answer` / `synthesize_event_answer` / `synthesize_report` 三个 stage 的执行代码高度重复，彼此之间只是 prompt 模板不同，维护三套 runner 与三套契约枚举带来大量冗余 diff。更严重的是泛财经问题（如"降息对债市意味着什么"）被 router 一律打成 `out_of_scope` 直接拒答，既损害用户体验也浪费了 LLM 直答能力。本 change 在分支 `refactor/control-plane-collapse` 上一次性删 planner、合并 synthesize、新增轻路径，把控制面收敛为目标态 `router → classifier（仅 event 触发）→ orchestrator（查表 + 执行）`。

## What Changes

- 删除 planner 目录 [backend/src/finsight_agent/control_plane/planner/](backend/src/finsight_agent/control_plane/planner/)，原 stage 编排职责迁移到 orchestrator 层的纯查表函数。
- 删除 [shared/contracts/plan.py](shared/contracts/plan.py)（`Plan` 契约），stage 编排结果改为以 `(stages, stage_constraints, response_mode)` 三元组在 orchestrator 内部传递，不再跨模块暴露 plan 骨架。
- 新增 [backend/src/finsight_agent/control_plane/orchestrator/stage_planner.py](backend/src/finsight_agent/control_plane/orchestrator/stage_planner.py)：纯查表函数 `resolve_stages(router_result, strategy_payload) -> (stages, stage_constraints, response_mode)`，不调用 LLM，吸收原 planner 全部职责。
- 合并原 `synthesize_brief_answer` / `synthesize_event_answer` / `synthesize_report` 三个 stage 为单个 [backend/src/finsight_agent/control_plane/orchestrator/stage_runners/synthesize_answer.py](backend/src/finsight_agent/control_plane/orchestrator/stage_runners/synthesize_answer.py)，内部按 `response_mode`（`direct` / `brief_answer` / `event_answer` / `report`）切换 prompt 模板；删除原三个 runner。
- 新增 `general_finance_qa` intent 与 `response_mode=direct`，承接泛财经常识问题，LLM 直答不走检索，对应 stage 清单为单 stage `synthesize_answer`。
- 收紧 `out_of_scope`：仅对非金融问题、投资建议/荐股、股价预测触发；泛财经问题改走 `general_finance_qa`。
- 新增 4 个 reporting prompt 模板，分别覆盖 `direct` / `brief_answer` / `event_answer` / `report` 四种 `response_mode`，由 reporting service 按 `response_mode` 分发。
- 删除原 planner 相关 feature_flag 与 workbench 入口对 planner 的调用，workbench service / config 同步收敛。

最终 stage 清单收敛为 6 个：`query_structured_data`、`collect_event_context`、`analyze_targets`、`retrieve_evidence`、`synthesize_answer`（guardrail 短路不算 stage）。

## Capabilities

### New Capabilities

<!-- 本 change 不新增 capability。控制面收敛归属既有 capability。 -->

### Modified Capabilities

- `semantic-routing-and-planning`：删除 `Planner 输出稳定的 V1 计划骨架` 与 `Planner 显式编码步骤约束` 两个 Requirement；在 `语义路由输出结构化意图结果` 下新增 `general_finance_qa` scenario 并收紧 `out_of_scope` scenario；在 `Router 将追问类型作为独立维度处理` 的 redirect scenario 中把 "planner 重建主计划" 改为 "orchestrator 重新解析 stage 列表"；新增 `Orchestrator 通过查表解析 stage 列表` 与 `泛财经常识问题走轻路径直答` 两个 Requirement。
- `event-analysis-orchestration`：上下游关系把 `plan` 替换为 `stages`、`stage_constraints`；`Orchestrator 每轮执行单一主计划` 的 scenario 把 planner 引用改为 stage_planner、`四阶段` 改为 `多阶段`、超范围标记改为仅由 router 触发；`Orchestrator 支持有限的步骤级回退` 中 `synthesize_report` 改为 `synthesize_answer`。

## Impact

- 受影响 spec：
  - `openspec/specs/semantic-routing-and-planning/spec.md`（删除 2 Requirement / 新增 2 Requirement / 修改 2 Requirement）
  - `openspec/specs/event-analysis-orchestration/spec.md`（修改 2 Requirement + 上下游关系）
- 受影响代码骨架：
  - `backend/src/finsight_agent/control_plane/planner/`（整目录删除）
  - `backend/src/finsight_agent/control_plane/orchestrator/`（新增 `stage_planner.py`、新增 `synthesize_answer.py` runner、删除原 3 个 synthesize runner、改造 service）
  - `shared/contracts/plan.py`（删除）及 `shared/enums/` 下 stage_name / response_mode / intent 枚举（新增 general_finance_qa、direct、synthesize_answer；删除旧 3 个 synthesize stage 枚举）
  - workbench 入口与 `config/` 下 planner feature_flag / 配置项
  - reporting service 新增 4 个 prompt 模板
- 受影响测试：
  - 8 个测试文件需同步调整（planner 单测移除、stage_planner 单测新增、synthesize_answer 单测合并、workbench 装配测试更新、router 规则测试更新 general_finance_qa / out_of_scope 边界）
- 风险已知项：
  - router 对 `general_finance_qa` 与 `metric_lookup` / `event_impact_analysis` 边界可能误判，需补 router 评测样本
  - `synthesize_answer` 单 runner 内按 `response_mode` 分支，4 个模板共存可能让该 runner 趋于臃肿，后续若分支继续扩张需考虑拆分
  - `Plan` 契约删除影响面需排查所有跨模块引用，避免遗留 import
