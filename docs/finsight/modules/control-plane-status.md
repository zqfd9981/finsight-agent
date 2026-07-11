# 控制面状态

日期：2026-07-09
当前状态：进行中
阶段结论：控制面已完成三类主链的首版真实编排，并已具备事件样本回放能力，当前重点从“主链接线”转向“检索质量、分类器与评测增强”；控制面已完成 planner 合并 + synthesize 精简 + 泛财经轻路径重构。

## 模块范围

- `semantic-routing-and-planning`
- `conversation-session-state`
- `event-analysis-orchestration`

## 当前能力

### 1. Router / Classifier / Orchestrator

- `RouterService` 已稳定输出 5 个 intent：metric_lookup / event_impact_analysis / evidence_lookup / general_finance_qa / out_of_scope
- classifier（仅 event_impact_analysis 触发）已稳定输出 3 类 strategy：event_primary / disclosure_primary / dual_primary
- orchestrator 的 `stage_planner.resolve_stages` 纯查表函数已替代原 PlannerService，输出 (stages, stage_constraints, response_mode)

### 2. Orchestrator

- `OrchestratorService` 已稳定执行：
  - `query_structured_data`
  - `collect_event_context`
  - `analyze_targets`
  - `retrieve_evidence`
  - `synthesize_answer`
- 已支持：
  - `out_of_scope` 短路
  - `StageObservation`
  - execution trace
  - retrieval facade 懒加载与生命周期关闭

### 3. Session

- `SessionContext` 已接入统一入口
- 已支持：
  - snapshot 持久化
  - follow-up 上下文加载
  - rolling summary

### 4. 事件主链新增能力

- `event_impact_analysis` 已具备完整四阶段执行链
- `collect_event_context` 已改为：
  - 双层外部检索优先
  - 本地 RAG 条件补充
- `analyze_targets` 已支持：
  - 候选池不足时补 1 轮候选发现检索
  - 仍不足时诚实降级，不伪造股票池

### 5. Streamlit 内部工作台

- 已具备三类视图骨架：
  - `分析视图`
  - `调试视图`
  - `评测视图`
- `分析视图` / `调试视图` 复用统一 `analysis/turns` 入口
- `评测视图` 复用 `event_eval` fixtures、replay 与 checks

### 6. 可启动状态（change `make-workbench-runnable` 之后）

- 工作台已具备可启动入口：
  - 后端 `python scripts/run_workbench_backend.py`（默认 127.0.0.1:8000）
  - 前端 `python -m streamlit run frontend/streamlit_app/streamlit_entry.py`（默认 127.0.0.1:8501）
- 一键起两端：`./scripts/run_workbench.sh`（POSIX / Git Bash）
- 端口由 `config/app.yaml` 中 `app.workbench.backend_port` / `frontend_port` 驱动，前端 `backend_base_url` 也从同段读
- 完整启动 / 故障排查见 [operations/workbench-runbook.md](../operations/workbench-runbook.md)

## 本轮新增

- 新增 `RetrievalStrategyClassifier` 抽象与 stub/fallback
- 新增 `ContextRetrievalPlanner`
- 新增 `DualSourceExternalContextRetriever`
- `OrchestratorService` 默认装配真实 dual-source external retriever
- 新增 `event_impact_analysis` replay 回放框架，可批量观察策略、降级与候选结果
- 事件搜索 provider 由 GDELT 整体替换为博查（Bocha）Web Search API：
  - 新增 `EventSearchProvider` Protocol 抽象边界（与现有 `ExternalContextRetriever` Protocol 同侧，符合 consumer-owned 风格）
  - `OrchestratorService` 默认装配改用 `BochaEventSearchProvider`；缺失 `BOCHA_API_KEY` 时构造期抛 `RuntimeError`
  - 删除 GDELT 源码、单测、根目录 2 个 ad-hoc 脚本
  - 新增护栏测试 `test_no_gdelt_references_in_production.py` 扫描 `backend/src/finsight_agent/` 防 GDELT 回潮
  - 新增根目录 `test_bocha.py` 冒烟脚本（不进 CI）

### 控制面重构成果

- 删除 planner 层，stage 编排职责合并入 orchestrator 的 `resolve_stages` 查表函数
- 3 个 synthesize_* stage 合并为 1 个 `synthesize_answer`，按 `response_mode` 分发
- 新增 `general_finance_qa` 轻路径，泛财经常识问题走 LLM 直答
- 收紧 `out_of_scope`，只对投资建议/荐股/股价预测触发
- 新增 4 个 reporting prompt 模板 + reporting service 统一 `build_response` 入口

## 活跃任务状态

| 任务 | 状态 | 说明 |
| --- | --- | --- |
| `semantic-routing-and-planning` 首版规则实现 | 已完成 | 已稳定驱动真实主链，planner 已合并入 orchestrator |
| `SessionContext` 首版真实接线 | 已完成 | follow-up 已可真实续接 |
| `event_impact_analysis` 首版四阶段接线 | 已完成 | 事件链可真实执行 |
| 双层外部上下文检索接入 | 已完成首版 | 已接入 Bocha（替换原 GDELT）+ 官方披露搜索；新增 `EventSearchProvider` Protocol 抽象边界 |
| 事件分析评测样本与回放 | 已完成首版 | 可批量回放事件 query，并观测策略与降级结果 |
| Streamlit 调试/评测工作台 | 已完成首版 | 已具备分析、调试、评测三视图骨架 |
| 检索策略分类器训练 | 未开始实现 | 已单独拆成训练子项目，不阻塞主链 |
| 事件分析评测集扩展 | 进行中 | 已有首版基线，后续继续补样本与误判场景 |
| `general_finance_qa` 轻路径 | 已完成 | 泛财经常识问题走 LLM 直答 |

## 当前风险

1. classifier 已升级到 StructBERT 微调模型（93.18% test acc），但边界样本仍可优化。
2. 双层外部检索虽然已建立 replay 基线，但样本规模和弱结果覆盖仍不足。
3. `analyze_targets` 已可批量回放，但目标发现质量仍需更多真实事件样本观察。
4. 事件搜索单点依赖博查：未做重试 / 缓存 / 熔断；key 缺失或 429 限流时降级到披露源 + 本地 RAG，事件背景可能偏薄；详见 [operations/workbench-runbook.md §5.2](../operations/workbench-runbook.md)。
5. general_finance_qa 路由边界需持续观察。

## 下一步建议

1. 扩展 `event_impact_analysis` 评测样本与误判回放集
2. 按独立计划推进分类器训练与离线评测
3. 评估是否需要缓存、超时控制与 provider 级别熔断
