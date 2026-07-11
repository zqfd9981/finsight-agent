## 1. Shared 层契约改动

- [x] 1.1 在 `shared/enums/intent.py` 新增 `GENERAL_FINANCE_QA` 枚举值
- [x] 1.2 在 `shared/enums/response_mode.py` 新增 `DIRECT` 枚举值（direct / brief_answer / event_answer / report 四值齐备）
- [x] 1.3 在 `shared/enums/stage_name.py` 新增 `SYNTHESIZE_ANSWER`，删除 `SYNTHESIZE_BRIEF_ANSWER` / `SYNTHESIZE_EVENT_ANSWER` / `SYNTHESIZE_REPORT` 三个旧枚举
- [x] 1.4 删除 `shared/contracts/plan.py` 及其在 `shared/contracts/__init__.py` 的导出
- [x] 1.5 验证 `python -m unittest tests.unit.test_project_skeleton -v` 仍通过
- [x] 1.6 Commit: `refactor(shared): add general_finance_qa/direct enums and drop Plan contract`

## 2. Orchestrator 层改动

- [x] 2.1 新增 `backend/src/finsight_agent/control_plane/orchestrator/stage_planner.py`，实现纯查表函数 `resolve_stages(router_result, strategy_payload) -> (stages, stage_constraints, response_mode)`，覆盖 metric_lookup / general_finance_qa / evidence_lookup / event_impact_analysis(三 strategy 分叉) / out_of_scope
- [x] 2.2 新增 `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/synthesize_answer.py`，内部按 `response_mode` 分发 4 个 prompt 模板
- [x] 2.3 改造 `orchestrator/service.py`：用 `resolve_stages` 替换原 planner 调用，按返回的 stages 执行 stage_runners
- [x] 2.4 删除原 `synthesize_brief_answer.py` / `synthesize_event_answer.py` / `synthesize_report.py` 三个 runner
- [x] 2.5 更新 `stage_runners/__init__.py` 注册表，指向新的 `synthesize_answer`
- [x] 2.6 验证 `python -m unittest tests.unit.test_orchestrator_service tests.unit.test_stage_planner -v` 通过
- [x] 2.7 Commit: `refactor(orchestrator): add stage_planner lookup and merge synthesize stages`

## 3. 删 planner + 改 workbench 入口

- [x] 3.1 删除整个 `backend/src/finsight_agent/control_plane/planner/` 目录
- [x] 3.2 删除 planner 相关 feature_flag 与配置项（`config/` 下）
- [x] 3.3 改造 workbench service：移除对 `PlannerService` 的装配与调用，直接 `RouterService → OrchestratorService`（orchestrator 内部查表）
- [x] 3.4 改造 `config/app.yaml` 等配置入口，移除 planner 段
- [x] 3.5 验证 `python -m unittest tests.unit.test_workbench_backend_api_service tests.unit.test_project_skeleton -v` 通过
- [x] 3.6 Commit: `refactor(control-plane): remove planner layer and rewire workbench entry`

## 4. 新增轻路径 + reporting 多模板

- [x] 4.1 在 router rules 中新增 `general_finance_qa` 路由规则，承接泛财经常识问题
- [x] 4.2 收紧 `out_of_scope` 规则：仅对非金融问题、投资建议/荐股、股价预测触发
- [x] 4.3 新增 4 个 reporting prompt 模板，分别覆盖 `direct` / `brief_answer` / `event_answer` / `report`
- [x] 4.4 改造 reporting service，按 `response_mode` 分发对应 prompt 模板
- [x] 4.5 验证 `python -m unittest tests.unit.test_router_rules tests.unit.test_reporting_service -v` 通过
- [x] 4.6 Commit: `feat(router): add general_finance_qa light path and tighten out_of_scope`

## 5. Tests 调整

- [x] 5.1 删除 `tests/unit/test_planner_*.py` 相关 planner 单测
- [x] 5.2 新增 `tests/unit/test_stage_planner.py` 覆盖 5 条 (intent, strategy) → stages 映射 + out_of_scope 短路
- [x] 5.3 合并原 3 个 synthesize 单测为 `tests/unit/test_synthesize_answer_runner.py`，覆盖 4 个 response_mode 分支
- [x] 5.4 更新 `tests/unit/test_workbench_backend_api_service.py` 装配断言（去掉 planner，改验 stage_planner）
- [x] 5.5 更新 `tests/unit/test_router_rules.py`，新增 general_finance_qa case 与收紧后的 out_of_scope 边界 case
- [x] 5.6 更新 `tests/unit/test_orchestrator_service.py`，把 planner mock 替换为 stage_planner 直接调用
- [x] 5.7 更新 `tests/unit/test_project_skeleton.py`，移除对已删 planner 文件 / 旧 synthesize runner 的存在性断言
- [x] 5.8 更新 `tests/integration/test_backend_api_app.py`，确认 envelope 在 general_finance_qa 路径下可端到端产出
- [x] 5.9 验证 `python -m unittest discover tests -v` 全绿
- [x] 5.10 Commit: `test: sync 8 test files to collapsed control plane`

## 6. 文档与 spec

- [x] 6.1 更新 `openspec/specs/semantic-routing-and-planning/spec.md`（删 2 planner Requirement、新增 2 Requirement、修改 router/follow-up Requirement）
- [x] 6.2 更新 `openspec/specs/event-analysis-orchestration/spec.md`（上下游关系 + 2 Requirement 修改）
- [x] 6.3 新增 change proposal：`openspec/changes/2026-07-09-collapse-planner-and-synthesize-stages/`（proposal / design / tasks / spec delta）
- [x] 6.4 更新 `docs/finsight/modules/control-plane-status.md`，反映控制面收敛为 router → classifier → orchestrator
- [x] 6.5 更新 `docs/finsight/project-status.md`，追加控制面重构里程碑
- [x] 6.6 验证 `python -m unittest tests.unit.test_project_skeleton -v` 通过
- [x] 6.7 Commit: `docs: update specs and add collapse-planner change proposal`
