## 1. 规格拆解产出

- [x] 1.1 将原始设计稿拆解为 `analysis-workbench` spec，明确工作台交互、trace 展示、追问体验与降级展示边界
- [x] 1.2 将原始设计稿拆解为 `conversation-session-state` spec，明确多轮会话状态、上下文压缩与 follow-up 继承边界
- [x] 1.3 将原始设计稿拆解为 `semantic-routing-and-planning` spec，明确 intent 判别、follow-up type 与 V1 四阶段 plan 边界
- [x] 1.4 将原始设计稿拆解为 `event-analysis-orchestration` spec，明确主计划执行、局部重试、步骤级回退与 observation 边界
- [x] 1.5 将原始设计稿拆解为 `evidence-retrieval-pipeline` spec，明确混合检索、query 增强、rerank 与 citation 组装边界
- [x] 1.6 将原始设计稿拆解为 `structured-market-data-support` spec，明确主题映射、候选筛选与基础结构化字段边界
- [x] 1.7 将原始设计稿拆解为 `report-trace-and-evaluation` spec，明确报告结构、trace 输出、guardrail 与 V1 评测边界

## 2. 边界与依赖收敛

- [x] 2.1 复核 7 个新增 capability spec，确认每个 spec 都只有单一且清晰的职责边界
- [x] 2.2 在每个 spec 中补充重点关注点、非职责范围和上下游关系，避免后续实现时职责漂移
- [x] 2.3 复核 proposal、design 与 specs 之间的一致性，确认 capability 命名、边界与技术基线没有漂移
- [x] 2.4 复核 spec 拆分是否适合并行开发，确认没有遗漏新的 capability 或出现职责交叉

## 3. 设计基线冻结

- [x] 3.1 在 design 中明确 spec 与 design 的分工，避免后续把实现细节提前写成代码或契约文件
- [x] 3.2 在 design 中冻结 V1 技术基线，包括 `LangGraph`、`FastAPI`、`Streamlit`、`SQLite`、`Qdrant`、`BGE-M3`、`bge-reranker`、`MinerU + pdfplumber`、`Tavily + AKShare`
- [x] 3.3 在 design 中冻结 V1 检索强约束，包括 `Hybrid Retrieval`、`SQLite FTS5`、`RRF`、`Parent-Child Chunking`、`Query Rewrite` 与条件触发的 `HyDE / Query2Doc`
- [x] 3.4 在 design 中明确本次 change 属于“spec 拆解与沉淀”，而不是业务实现 change，避免 apply 阶段越界

## 4. 说明与校验

- [x] 4.1 产出可视化说明文档，帮助后续理解 7 个 spec 的重点关注点与相互关系
- [x] 4.2 复核主基线 `openspec/specs` 当前为空这一状态是否符合本阶段预期，并记录后续同步动作
- [x] 4.3 运行 OpenSpec 校验，确认 change artifacts 合法
- [x] 4.4 确认没有额外实现文件、测试骨架、contract、fixture 等越界内容残留在仓库中

## 5. 归档准备

- [x] 5.1 确认这次 change 已经完整表达“如何拆 spec”，可以进入 `sync-specs` 或 `archive`
- [x] 5.2 记录本次反思：以后对文档型 change 不再误用 apply 去生成实现代码
