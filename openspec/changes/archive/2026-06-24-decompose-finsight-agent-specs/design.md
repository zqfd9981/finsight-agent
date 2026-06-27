## 背景

当前仓库只有一份 `FinSight Agent` 设计稿和基础 OpenSpec 目录，尚未建立正式 capability specs。原始设计稿已经覆盖了 V1 范围、架构、RAG 策略、guardrails 与评测思路，但这些内容仍按“整机视角”组织，不利于并行开发。

这次变更的目标不是直接写实现代码，而是把 V1 收敛成后续实现能够复用的规格边界。拆分时需要同时满足三件事：

- 每个 spec 都能独立回答“这个能力做什么、不做什么、如何验收”
- 不同开发 lane 能在 mock 契约下先行实现，而不是互相阻塞
- 核心依赖关系保持单向，避免 Session、Router、Retriever、UI 彼此交叉耦合

## 目标与非目标

**目标：**
- 把 V1 设计稿拆成 7 个可归档的 capability specs
- 明确 capability 之间的接口边界和推荐依赖方向
- 为后续并行开发提供分 lane 的实施起点
- 让后续针对具体 capability 的实现 change 可以直接基于这些能力规格写实现任务

**非目标：**
- 不在本次变更中确定所有字段级 JSON Schema 细节
- 不在本次变更中直接实现 LangGraph、FastAPI、Streamlit 或检索代码
- 不提前把 V2+ 能力纳入 V1 spec 范围
- 不把所有内部类、函数和数据库表结构拍死

## 关键决策

### 决策：将 V1 技术栈作为实现基线显式冻结

本次 change 的 capability spec 主要回答“系统要做什么”，而 V1 的具体技术路线需要在 design 中作为实现基线显式固定，后续 `/opsx:apply` 与实现阶段必须默认遵守以下约束：

- Agent 编排基线：`LangGraph`
- 后端 API 基线：`FastAPI`
- 前端工作台基线：`Streamlit`
- 会话与结构化存储基线：`SQLite`
- 向量检索基线：`Qdrant`
- Embedding 基线：`BGE-M3`
- Rerank 基线：`bge-reranker`
- PDF 解析基线：`MinerU + pdfplumber`
- 外部信息基线：`Tavily + AKShare`

这些技术选型在 V1 阶段不是可随意替换的候选项，而是默认实现基线。除非后续通过新的 OpenSpec change 明确修改，否则实现阶段不应擅自改成其他主框架，例如把 `LangGraph` 替换为自写 agent loop、把 `Qdrant` 替换为其他向量库、或把 `Streamlit` 替换成另一套前端框架。

原因：
- 这份设计稿本身就已经包含较明确的技术路线
- 若不冻结实现基线，并行开发时容易出现各 lane 在不同技术假设下分别推进
- V1 的重点是可复现、可演示、可评测，而不是同时比较多套技术路线

备选方案：
- 把技术栈完全留到实现阶段再决定。未采用，因为这会让后续 specs 和 tasks 虽然边界清晰，但实现方向容易漂移。

### 决策：按“可独立验收的能力域”拆分，而不是按技术组件名拆分

选择 7 个 capability：`analysis-workbench`、`conversation-session-state`、`semantic-routing-and-planning`、`event-analysis-orchestration`、`evidence-retrieval-pipeline`、`structured-market-data-support`、`report-trace-and-evaluation`。

原因：
- 用户视角、产品视角和工程视角都能对齐这些边界
- 每个 capability 都可以用接口 mock 提前开发
- 避免出现“前端 spec”“后端 spec”“数据库 spec”这类过于技术层面的切分，导致职责含混

备选方案：
- 按技术栈拆成前端 / 后端 / 数据 / 检索 / 评测。未采用，因为它会把单个业务链路切散，验收口径不稳定。
- 按 LangGraph 节点逐个拆更细 spec。未采用，因为粒度过细，会让 specs 数量膨胀并提高协作成本。

### 决策：把并行开发建立在契约优先的依赖图上

推荐依赖关系如下：

```text
conversation-session-state
semantic-routing-and-planning
structured-market-data-support
evidence-retrieval-pipeline
        \        |        /
      event-analysis-orchestration
                |
  report-trace-and-evaluation
                |
      analysis-workbench
```

解释：
- `event-analysis-orchestration` 消费 session、router/planner、structured data、retrieval 四类能力，因此它是后端主集成点
- `report-trace-and-evaluation` 位于 orchestrator 之后，因为它消费标准 observation
- `analysis-workbench` 虽然最终面向用户，但可以只依赖后端响应契约，因此能与核心后端并行开发

备选方案：
- 先做 orchestrator，再倒推出其他模块接口。未采用，因为这会让主链路承担过多设计决策，阻塞并行实现。

### 决策：将 `conversation-session-state` 作为显式 capability，而不是隐式附属能力

原因：
- 多轮追问是 V1 的显式目标，不是附属特性
- follow-up 分类、上下文压缩、候选对象继承都依赖稳定的 session contract
- 若把它埋在 orchestrator 或 UI 内部，后续接口会快速失控

备选方案：
- 将 session 细节并入 workbench 或 orchestrator。未采用，因为这会让“状态定义”和“流程执行”混在一起。

### 决策：将评测与 guardrails 与报告能力放在同一 capability

原因：
- 三者都消费同一批标准 observation 和最终响应结构
- degraded response 的稳定性本质上既是产品输出问题，也是评测对象
- 这样能让“可展示”与“可评测”共享同一验收边界

备选方案：
- 单独再拆 `guardrails` 和 `evaluation` 两个 spec。未采用，因为在 V1 阶段这会过碎，且依赖对象完全重合。

### 决策：任务顺序采用“先契约，后各 lane 并行，最后主链集成”

推荐实施阶段：

1. 先固定 capability specs、API contract、stage observation contract
2. 并行推进四条 lane：
   - session + router/planner
   - retrieval pipeline
   - structured market data
   - workbench UI（基于 mock response）
3. 再实现 orchestration 集成
4. 最后接 report/trace/guardrails/evaluation 验收

原因：
- 这样依赖最少，等待最短
- UI 和后端基础能力不互相阻塞
- retrieval 与 structured data 都能独立跑样例和测试

### 决策：本次 change 属于“文档型规格沉淀”，不是产品实现 change

本次 `decompose-finsight-agent-specs` 的目标是把设计稿拆成可归档的 capability spec，并校准 proposal、design、specs、tasks 之间的一致性；它不是直接产出 `contract`、`fixture`、`skeleton code` 或测试工程骨架的实现 change。

因此，本次 change 的 `tasks.md` 应只覆盖以下类型的动作：

- 复核 7 个 spec 的职责边界与依赖关系
- 补强 spec 中的重点关注点、非职责范围、上下游说明
- 冻结 design 中的 V1 技术基线与检索强约束
- 准备后续 `sync-specs` / `archive` 所需的检查项

而以下内容不应在本次 change 中产生：

- `contracts/`、`fixtures/`、`tests/`、`finsight_agent/` 等实现目录
- 任何 JSON Schema、API mock payload、LangGraph skeleton、FastAPI/Streamlit 代码
- 为了“让 apply 看起来有产出”而额外发明的实现文件

### 决策：将检索策略作为 V1 的强实现约束，而不是可选优化项

虽然 capability spec 主要描述行为，但对于 `evidence-retrieval-pipeline`，下列实现路线在 V1 中应视为默认且强约束的方案：

- 检索策略采用 `Hybrid Retrieval`，即 `dense retrieval + sparse retrieval + fusion`
- sparse retrieval 基线采用 `SQLite FTS5`
- fusion 基线采用 `RRF`
- rerank 放在 fusion 之后执行
- 文档切片采用 `Parent-Child Chunking`
- 默认启用轻量 `Query Rewrite`
- `HyDE / Query2Doc` 作为条件触发增强，而不是默认主链路
- 最终证据装配需要支持 citation metadata 与 parent context 回填

原因：
- 这些并不只是“底层实现细节”，它们已经直接影响证据质量、trace 结构、评测口径和最终报告可解释性
- 若把这些约束留空，后续即使表面满足 spec，也可能实现成纯向量检索、无 rewrite、无 rerank 或无 parent expand 的弱化版本

备选方案：
- 仅在 spec 中保留“能检索到证据”这一层行为要求。未采用，因为这会让 V1 的核心展示能力被过度抽象，失去原始设计稿最关键的工程特色。

## 风险与权衡

- [Risk] `event-analysis-orchestration` 仍然是集成热点，后续实现时容易重新吸收过多职责 → Mitigation: 强制要求 orchestrator 只消费 contract，不持有底层数据定义主权。
- [Risk] `report-trace-and-evaluation` 把三个关注点放在同一 capability，后续可能变大 → Mitigation: 仅在 V1 保持合并；若 V2 引入自动化评测平台，再拆分为独立 spec。
- [Risk] `analysis-workbench` 依赖后端响应契约，如果契约晚定会拖慢前端 → Mitigation: 在后续具体实现 change 中优先冻结最小 response contract 与 mock payload。
- [Risk] `structured-market-data-support` 与 `evidence-retrieval-pipeline` 都会参与候选筛选，边界可能模糊 → Mitigation: 明确前者负责结构化映射与筛选字段，后者只负责文档证据验证。
- [Risk] capability 数量过少会导致 spec 过重，过多会导致协作碎片化 → Mitigation: 当前保持 7 个能力域，后续仅在单个 spec 出现明显双重职责时再继续细分。
- [Risk] 后续实现人员如果只读 `spec.md` 不读 `design.md`，仍可能忽略技术基线 → Mitigation: 在后续具体实现 change 中先把 design 中的技术基线转写为实现任务和接口检查项。

## 能力边界复核

### analysis-workbench

- 重点关注：用户输入、结果展示、trace 展示、追问体验、降级态体验
- 非职责范围：不负责 router 判别、不负责检索细节、不负责会话压缩策略本身
- 上游输入：后端统一 response contract、session id、trace 数据
- 下游输出：用户 query、追问、会话标识

### conversation-session-state

- 重点关注：会话状态持久化、上下文压缩、活跃候选对象与关键证据继承
- 非职责范围：不负责 intent 判别、不直接规划步骤、不负责报告展示
- 上游输入：用户轮次、上一轮 observation、报告摘要
- 下游输出：压缩后的 `session_context`

### semantic-routing-and-planning

- 重点关注：intent 判别、follow-up type 判别、四阶段 V1 plan、步骤级约束
- 非职责范围：不执行检索、不直接筛公司、不产出最终报告正文
- 上游输入：query、`session_context`
- 下游输出：router result、plan skeleton、stage constraints

### event-analysis-orchestration

- 重点关注：主计划执行、步骤内有界探索、步骤级有限回退、标准化 observation
- 非职责范围：不拥有 session/retrieval/structured data/report 的细节主权
- 上游输入：router result、plan、session context、structured data、retrieval outputs
- 下游输出：stage observations、degraded observations、最终编排结果

### evidence-retrieval-pipeline

- 重点关注：Hybrid Retrieval、Parent-Child Chunking、RRF、rerank、citation metadata
- 非职责范围：不负责主题映射、不负责会话状态、不决定最终报告结构
- 上游输入：claim、company/topic target、retrieval hints
- 下游输出：evidence bundle、support strength、parent context

### structured-market-data-support

- 重点关注：主题/行业/概念/候选公司映射、基础财务与分类字段筛选、对比字段
- 非职责范围：不做全文证据验证、不扩张为重型投研数据库
- 上游输入：event entities、impact hypotheses、candidate narrowing requests
- 下游输出：主题集合、候选对象集合、排序/过滤字段

### report-trace-and-evaluation

- 重点关注：稳定报告结构、trace 输出、guardrail 降级结构、golden query 评测
- 非职责范围：不重新路由、不重复检索、不替代 orchestrator 做流程决策
- 上游输入：stage observations、evidence bundle、critic notes
- 下游输出：最终 response、trace blocks、evaluation rubrics

## Spec 与 Design 的分工

为了避免后续把实现细节提前写成代码或契约文件，本次 change 采用以下分工：

- `spec.md`：回答“系统必须做什么、边界在哪里、最小验收场景是什么”
- `design.md`：回答“为什么这样拆、V1 技术基线是什么、并行开发如何组织、有哪些风险与约束”
- `tasks.md`：回答“为了把这次文档型 change 收口，需要复核和补强哪些文档任务”

以下内容不在本次 change 中固化：

- 字段级 JSON Schema
- 具体 HTTP API 细节
- 数据库表结构
- LangGraph 节点代码
- 检索 pipeline 的实现代码与 fixture

这些内容如需落地，应在后续针对具体 capability 的实现 change 中继续展开。

## 迁移计划

1. 先将本次 change 作为新的 V1 规格基线提交。
2. 后续先执行 `sync-specs` 或 `archive`，把这批 delta specs 同步到主基线 `openspec/specs/`。
3. 再针对具体 capability 或实现批次新开 change，使用 `/opsx:apply` 进入真实实现任务拆解。
4. 若某个 capability 在实现中证明过大，再通过新的 change 继续细分，而不是直接篡改边界。

## 主基线同步准备

- 当前 `openspec/changes/decompose-finsight-agent-specs/specs/` 中存在 7 个 delta spec，`openspec/specs/` 为空是当前阶段的预期状态。
- 在执行 `sync-specs` 前，应确认 7 个 spec 的命名、职责边界、技术基线引用和最小场景已经稳定。
- 在执行 `archive` 时，应优先选择“先同步 spec，再归档 change”的路径，避免主基线继续为空。
- 可视化说明文件已经存在于 `visual/finsight-spec-map.html`，可作为后续同步与评审时的辅助材料，但它不属于主 spec 基线的一部分。

## 反思记录

- 对文档型 change，`apply` 不应被机械理解为“开始写实现代码”。
- 只有当 `tasks.md` 明确指向产品实现、且用户也明确要进入实现阶段时，才应生成代码、contract、fixture 或测试骨架。
- 对类似“拆 spec”“沉淀规格”“归档同步”的 change，应优先把工作收敛在 `proposal/design/specs/tasks` 与必要的说明文档中。

## 待确认问题

- Router 与 Planner 的字段 schema 是否要在下一次 change 中单独固化为 JSON Schema artifact。
- Workbench 与后端之间是否需要先定义同步 HTTP contract，再决定是否引入流式更新。
- Retrieval pipeline 的 citation 元数据是否需要在 V1 就固定到页码级，还是先停留在 chunk 级。
- Structured market data 的首批字段列表是否需要单独成为数据契约 spec。
