## 背景与动机

当前 `FinSight Agent` 设计稿已经覆盖产品范围、Agent 架构、RAG 策略、结构化数据、前端工作台与评测，但仍是单篇设计文档，难以直接转化为可并行实现的工程任务。现在需要把 V1 拆成边界清晰、依赖可控、可独立验收的 OpenSpec 能力规格，避免实现阶段出现“大 spec 带来大耦合”。

## 变更内容

- 将 `FinSight Agent` V1 拆分为 7 个能力规格，覆盖工作台、会话状态、路由规划、事件分析编排、证据检索、结构化数据与报告评测。
- 为每个能力规格定义输入输出边界、V1 范围、降级行为和最小验收场景。
- 在设计文档中补充并行开发分层、依赖图和推荐实现顺序，确保不同开发者可在 mock 契约下并行推进。
- 在任务清单中按“先复核边界、再补强文档、后同步主基线”的方式拆分本次文档型 change 的收口工作。

## 能力范围

### 新增能力
- `analysis-workbench`: 定义 Streamlit 工作台、主分析视图、trace 视图和与后端契约对接的 V1 交互能力。
- `conversation-session-state`: 定义多轮会话状态模型、上下文继承、追问分类输入和状态读写约束。
- `semantic-routing-and-planning`: 定义 Router 的结构化输出、follow-up 识别和 Planner 主步骤骨架。
- `event-analysis-orchestration`: 定义事件分析主链路的执行编排、步骤间 observation 传递和局部回退规则。
- `evidence-retrieval-pipeline`: 定义本地知识库检索、Hybrid Retrieval、rerank、parent expand 与引用装配能力。
- `structured-market-data-support`: 定义主题/行业/概念/基础财务指标查询与候选对象筛选支持能力。
- `report-trace-and-evaluation`: 定义最终报告、trace 展示、guardrails 输出和 V1 评测集组织方式。

### 修改能力
- 无。

## 影响范围

- 影响 `openspec/specs/` 的未来能力基线与后续实现顺序。
- 为 LangGraph、FastAPI、Streamlit、SQLite、Qdrant、MinerU、Tavily、AKShare 等技术选型建立明确责任边界。
- 约束后续模块接口、测试分层、mock 策略和并行开发协作方式。
