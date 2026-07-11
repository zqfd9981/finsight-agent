# FinSight V1 项目状态

日期：2026-07-09
状态：控制面、结构化数据、证据检索、事件主链与检索策略分类器均已形成首版可运行闭环，项目进入”能力增强、评测补强与稳定性优化”阶段；控制面已完成 planner 合并 + synthesize 精简 + 泛财经轻路径重构。

## 总览

当前已经完成这些关键闭环：

- shared contracts、统一 API boundary、trace/envelope 已稳定落地
- `semantic-routing-and-planning` 已稳定输出 `RouterResult`，planner 层已合并入 orchestrator 的 stage 查表函数
- retrieval facade 已稳定返回结构化 `RetrievalResult`
- `structured-market-data-support` 已完成”本地指标库 + 外部 fallback”首版闭环
- orchestrator 已接通三条真实执行链：
  - `metric_lookup`
  - `evidence_lookup`
  - `event_impact_analysis`
- `event_impact_analysis` 已接入首版真实双层外部检索：
  - `Bocha` 事件搜索
  - `CNInfo + SSE` 官方披露搜索
- `RetrievalStrategyClassifier` 已从 stub 升级到真实微调模型，主流程按 query 分布真实选择三类策略
- `event_impact_analysis` 已新增首版评测样本与 replay 回放框架
- Streamlit 内部工作台已具备首版三视图骨架：
  - `分析视图`
  - `调试视图`
  - `评测视图`

## 里程碑

| 里程碑 | 状态 | 说明 |
| --- | --- | --- |
| M1 Contract Ready | 完成 | contracts 与 API boundary 已稳定 |
| M2 Semantic Routing Ready | 完成 | routing / planning 已能稳定驱动真实链路 |
| M3 Retrieval Pipeline Ready | 完成 | 本地 retrieval 闭环已稳定 |
| M4 Response Ready | 完成 | response / trace / envelope 已稳定 |
| M5 Structured Data Ready | 完成 | `metric_lookup` 已不再依赖占位结果 |
| M6 Event Chain Ready | 完成 | `event_impact_analysis` 四阶段主链已接通 |
| M7 External Context Ready | 完成首版 | 双层外部检索已接入事件链 |
| M8 Event Eval Ready | 完成首版 | 事件样本、回放与最小检查闭环已落地 |
| M9 Workbench Runnable | 完成首版 | 后端 FastAPI 入口 + Streamlit 工作台已可一键启动；见 [operations/workbench-runbook.md](operations/workbench-runbook.md) |
| M10 Event Search Replace | 完成首版 | 事件搜索 provider 由 GDELT 整体替换为博查（Bocha）Web Search API；新增 `EventSearchProvider` Protocol 抽象边界；新增护栏测试防 GDELT 回潮；见 [specs/2026-07-06-bocha-event-search-replace-gdelt-design.md](../superpowers/specs/2026-07-06-bocha-event-search-replace-gdelt-design.md) |
| M11 Strategy Classifier Trained | 完成首版 | `RetrievalStrategyClassifier` 从 stub 升级到 StructBERT 中文 base 微调三分类器；301 条标注 / test acc 93.18% / per-class F1 0.88-1.00；失败回退到 stub；见 [specs/2026-07-07-retrieval-strategy-classifier-training-design.md](../superpowers/specs/2026-07-07-retrieval-strategy-classifier-training-design.md) |
| M12 Control Plane Collapse | 完成 | 删除 planner 层，stage 编排职责合并入 orchestrator 的 `resolve_stages` 查表函数；3 个 synthesize_* stage 合并为 1 个 `synthesize_answer` 按 `response_mode` 分发；新增 `general_finance_qa` 轻路径 + `direct` response_mode；收紧 `out_of_scope` 判定；新增 4 个 reporting prompt 模板 |

## 本轮新增成果

- 新增 `RetrievalStrategyClassifier` 抽象与 stub/fallback
- 新增 `ContextRetrievalPlanner`
- 新增双层外部检索组合器 `DualSourceExternalContextRetriever`
- 新增真实 provider：
  - `BochaEventSearchProvider`
  - `CninfoContextSearchProvider`
  - `SseContextSearchProvider`
  - `OfficialDisclosureSearchProvider`
- 事件搜索 provider 由 GDELT 整体替换为博查（Bocha）Web Search API：
  - 新增 `EventSearchProvider` Protocol 抽象边界（与现有 `ExternalContextRetriever` Protocol 同侧）
  - `OrchestratorService` 默认装配改用 Bocha；缺失 `BOCHA_API_KEY` 时构造期抛 `RuntimeError`
  - 删除 GDELT 源码、单测、根目录 2 个 ad-hoc 脚本
  - 新增护栏测试 `test_no_gdelt_references_in_production.py` 防止 GDELT 回潮
  - 新增根目录 `test_bocha.py` 冒烟脚本（不进 CI）
- `collect_event_context` 从”固定外部 + 固定本地 RAG”改为”条件 RAG”
- `OrchestratorService` 默认装配真实 dual-source external retriever
- 新增 `event_eval` 模块：
  - fixture schema
  - replay result schema
  - replay runner
  - 确定性 checks
- 新增 Streamlit 工作台最小可视化骨架：
  - `分析视图` 复用统一 `analysis/turns` 入口
  - `调试视图` 可查看 route / plan / execution
  - `评测视图` 可查看 replay summary、records 与 checks
- 当前可批量观察：
  - `intent`
  - 检索策略
  - 是否降级
  - 候选数量
  - 证据引用数量
- 检索策略分类器已从 stub 升级到真实微调模型：
  - 训练子项目 `backend/training/finsight_agent_training/retrieval_strategy_classifier/`
  - 预训练起点：`alibaba-pai/structbert-base-zh`
  - 训练数据：301 条人工标注样本（event 87 / disclosure 99 / dual 115）
  - 切分：train 206 / val 51 / test 44
  - 离线评测：test accuracy **93.18%** / per-class F1 0.88-1.00（CI gate 0.85/0.80）
  - 运行时 `TrainedRetrievalStrategyClassifier` 懒加载 + 失败回退到 stub
  - `event_eval/fixtures/event_cases_v1.jsonl` 6 条 E2E 命中 4 条（含 2 条边界分歧）
  - trace `source_status` 透传 `strategy_reason` / `strategy_confidence` / `strategy_source`

### 控制面重构成果

- 删除 `planner/` 整目录与 `shared/contracts/plan.py`
- 新增 `orchestrator/stage_planner.py` 提供 `resolve_stages` 纯查表函数
- 3 个 synthesize_* runner 合并为 1 个 `synthesize_answer`，按 `response_mode`（direct / brief_answer / event_answer / report）分发
- 新增 `general_finance_qa` intent + `direct` response_mode，泛财经常识问题走 LLM 直答轻路径
- 收紧 `out_of_scope`，只对投资建议/荐股/股价预测触发
- 新增 4 个 reporting prompt 模板 + reporting service 统一 `build_response` 入口
- stage 数从 7 → 6，intent 数从 4 → 5

## 当前重点风险

### 1. 真实外部检索已接入，首版评测基线已建立

影响：
- `Bocha` 与官方披露站检索已能被控制面消费
- 且现在已经可以用 replay 样本批量验证命中质量、弱结果降级与不同事件类型的稳定性

### 2. 事件评测仍处于首版基线阶段

影响：
- 当前已具备首批事件样本、回放入口与最小检查项
- 但样本量、弱结果覆盖、误判门槛和长期趋势分析仍需继续扩展
- `RetrievalStrategyClassifier` 上线后，`event_eval` replay 是观测策略分布变化与误判回放的关键工具

### 3. 事件搜索单点依赖博查（Bocha）

影响：
- `event_impact_analysis` 的外部事件背景完全依赖博查 Web Search API；key 缺失 / 配额耗尽 / 429 限流时降级到披露源 + 本地 RAG，但仍可能出现事件背景薄弱
- 当前未做重试 / 缓存 / 熔断；首次查询期失败语义清晰，但长期稳定性需要更多真实流量验证

### 4. 分类器在边界样本上的判断仍可优化

影响：
- `event_eval/fixtures/event_cases_v1.jsonl` 的 6 条 canonical 样本 E2E 命中 4 条，剩余 2 条集中在 event→disclosure 与 dual→disclosure 边界
- 这两条 query 在 themes 包含具体行业（如”航运””消费电子”）时，模型偏向 disclosure_primary；属可辩护判断，但与原 label 略偏
- 不阻塞主流程；后续可通过补”含具体行业主题的 event_primary / dual_primary”样本回炉

### 5. 控制面重构后 general_finance_qa 路由边界需持续观察

影响：
- 泛财经问题与 metric_lookup / event_impact_analysis 的边界依赖 router 规则保守 fallback，具体公司+财务词仍走 metric_lookup，公告类走 event_impact_analysis，但边界 query 可能误判

## 下一阶段建议

1. 扩展 `event_impact_analysis` 评测样本规模，补更多弱结果与误判场景；用 `replay_event_cases` 跨 PR 对比策略分布
2. 为分类器补”含具体行业主题的 event_primary / dual_primary”边界样本，重训 + 再评测
3. 为外部检索补缓存、超时与失败降级策略
4. 扩展结构化数据覆盖范围，补更多公司、指标与期间
