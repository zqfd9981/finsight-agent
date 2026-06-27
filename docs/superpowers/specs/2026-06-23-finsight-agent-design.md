# FinSight Agent 设计草稿

日期：2026-06-23
状态：草稿，持续更新

## 1. 项目定位

FinSight Agent 是一个以 A 股事件影响分析为场景的 AI Agent 展示项目。

项目的首要目标不是做一个泛化金融问答系统，也不是做简单的 ChatPDF，而是展示以下三类能力：

- Agent 系统设计能力：语义路由、任务拆解、状态管理、loop 和质量校验
- RAG 工程能力：PDF 解析、父子块、Hybrid Retrieval、Rerank、引用回填
- 业务建模能力：事件影响链分析、概念映射、候选标的筛选、年报与公告验证

项目长期目标是逐步演进为可上线系统，但首阶段优先保证可复现、可演示、可评测。

## 2. 版本规划

### V1：可复现 Agent MVP

目标：

- 跑通中文自然语言输入
- 支持单轮分析与围绕当前分析结果的多轮追问
- 跑通事件影响分析主链路
- 支持新闻触发分析、本地知识库验证、报告输出、trace 展示和基础评测

### V2：路由与工具增强

目标：

- 扩展结构化工具能力
- 增强候选标的筛选、排序、对比
- 优化多轮 follow-up 的增量规划

### V3：高级 RAG 完整化

目标：

- 系统化引入 Parent-Child Chunking
- 强化 Query Rewrite、Hybrid Retrieval、Fusion、Rerank
- 完善检索评测与引用回填

### V4：业务推理增强

目标：

- 扩展更复杂的业务推理逻辑
- 增强概念映射与跨主题迁移能力
- 引入更多分析模式

### V5：上线化

目标：

- 缓存、日志、配置化、监控、错误恢复
- 前后端升级与部署能力
- 从 showcase 演进到可上线系统

## 3. V1 范围定义

### 输入与语言

- 只支持中文 Query
- 输入形态为自然语言自由输入

### 主场景

- 事件影响分析 + 年报/公告验证

示例：

- 某国际事件对哪些 A 股板块和公司有实质影响
- 某行业或概念板块下，哪些公司更可能受益或受损
- 某个判断能否在公司披露材料中找到证据支撑

### 主题范围

- 主深挖主题：航运 / 油气 / 化工
- 副主题：新能源 / 锂电 / 光伏

### 数据策略

- 实时层：新闻与事件信息在线获取
- 验证层：本地固定知识库

### 知识库范围

- 年报
- 半年报
- 重要公告

### 多轮能力

支持多轮，但不是无限开放式聊天。

多轮会话默认继承：

- 当前问题
- 候选标的
- 关键证据
- 执行轨迹

追问处理策略：

- 局部展开时走增量规划
- 问题改道时触发重新规划

## 4. V1 核心架构

顶层采用：

- LLM 语义识别
- 结构化输出
- 工作流骨架执行
- 低置信度回退

### 主链路

```text
用户 Query
  -> Semantic Router
  -> Planner
  -> Executor
     -> News Search
     -> Concept Mapper
     -> Structured Finance Tool
     -> Advanced RAG Pipeline
  -> Critic / Verifier
  -> Report Generator + Trace Panel
```

### 关键原则

- 不使用关键词 if-else 作为主路由策略
- 不在 V1 采用完全自由规划
- 使用 LLM 进行语义识别和结构化判别
- 一旦识别为某一问题类型，执行层走稳定工作流骨架
- 当路由置信度不足时，进入澄清、降级或范围提示

## 5. V1 核心模块职责

### Session Manager

负责多轮状态管理，保存并继承：

- current_query
- parsed_intent
- selected_theme
- candidate_stocks
- retrieved_evidence
- plan_steps
- critic_notes
- final_report

### Semantic Router

负责把用户 Query 转成结构化判别结果，例如：

- intent
- entities
- constraints
- follow_up_type
- confidence

V1 的 Router 输出采用三层结构，而不是平铺成一大组无边界字段：

- 第一层：问题类型
- 第二层：语义对象
- 第三层：执行需求

推荐分层如下：

Layer 1：这是什么问题

- intent
- follow_up_type
- confidence

Layer 2：这次问题在说什么

- entities
- themes
- target_stocks
- time_scope
- `entities` 在 `collect_event_context` 阶段进一步收敛为结构化的 `event_entities`，并采用分层 schema，而不是把固定字段与扩展字段平铺混排。
  ```json
  {
    "core": {
      "event_name": "",
      "event_type": "",
      "time_scope": "",
      "regions": [],
      "themes": [],
      "organizations": [],
      "companies": []
    },
    "extensions": {
      "commodities": [],
      "policies": [],
      "routes": [],
      "facilities": [],
      "products": [],
      "countries": [],
      "supply_chain_nodes": [],
      "financial_metrics": []
    },
    "gaps": [],
    "confidence": ""
  }
  ```
  这样设计的含义是：`core` 负责稳定骨架，`extensions` 承载按事件类型稀疏出现的扩展字段，`gaps` 显式记录缺失或不明确的信息，`confidence` 为后续补检索、补抽取或降级回答提供依据。

Layer 3：系统接下来需要做什么

- needs
- constraints
- preferred_output

这样设计的原因是：

- Layer 1 负责主工作流路由
- Layer 2 负责承载事件、主题、公司、时间等核心语义对象
- Layer 3 负责为后续工具调用和检索链路提供执行导向
- 避免 Router 同时承担分类器、实体抽取器和完整 Planner 的全部职责

V1 的 needs 不采用过细的工具名枚举，而采用能力模块级别的设计：

- news_search
- rag_retrieval
- structured_finance_lookup
- concept_mapping

各类型含义如下：

- news_search：获取外部事件背景、近期进展与新闻事实
- rag_retrieval：从年报、半年报、公告等本地知识库中召回文本证据
- structured_finance_lookup：查询结构化字段、财务指标、行业与概念归属等数据
- concept_mapping：把事件、概念、产业链语义映射到 A 股主题、板块和公司宇宙

V1 不再把以下动作作为 needs：

- candidate_screening
- citation_verification

原因是这两者更适合作为 Planner / Executor 层的步骤动作，而不是 Router 层的基础能力标签。

V1 的 intent 不采用过度细碎的枚举，也不收缩到只剩一个总类，而采用中等复杂度设计：

- event_impact_analysis
- evidence_lookup
- comparative_analysis
- out_of_scope

各类型含义如下：

- event_impact_analysis：从事件出发，分析影响链条、筛选候选标的，并回到年报 / 公告做验证
- evidence_lookup：重点是找出处、展开证据、核对原文，而不是重新执行完整事件分析
- comparative_analysis：围绕已有候选对象做比较、排序、解释差异
- out_of_scope：超出 V1 深度能力边界，需要拒答、降级或提示范围

这几个 intent 与 follow_up_type 是两个不同维度：

- intent 表示这轮任务本质上是什么
- follow_up_type 表示这轮与上一轮的关系，例如 drilldown / compare / expand / redirect

V1 的 follow_up_type 先收敛为 5 类：

- none
- drilldown
- compare
- expand
- redirect

各类型含义如下：

- none：首轮问题，或当前问题不依赖上一轮上下文
- drilldown：对上一轮结论、引用或证据做进一步展开
- compare：围绕上一轮候选对象做比较、排序或差异解释
- expand：沿当前分析方向扩展到相邻主题、相邻公司或更大范围
- redirect：虽然处于同一会话中，但用户实际上已经切换问题方向，应重新规划

### Planner

基于意图类型和上下文，生成可执行步骤骨架。
V1 以事件影响分析工作流为主，不追求无限制通用规划。

V1 的主 Planner Step 先收缩为 4 类主阶段：

- `collect_event_context`
- `analyze_targets`
- `retrieve_evidence`
- `synthesize_report`

各主步骤的含义如下：

- `collect_event_context`：先澄清外部事件本身，包括新闻检索、事件摘要、时间范围识别和初步影响链假设。
- `analyze_targets`：将事件语义映射到 A 股世界，并在这一步内部完成 `concept mapping`、`candidate screening` 以及初步范围收缩。
- `retrieve_evidence`：围绕目标公司或主题执行年报/公告检索，内部包含 `query rewrite`、`hybrid retrieval`、`rerank`、`parent expand` 以及局部证据核验 loop。
- `synthesize_report`：把事件背景、影响链条、候选标的和证据收束成最终分析报告，同时输出引用和不确定性说明。

其中，`collect_event_context` 的输入边界先收敛为轻量模式，不直接吞入完整历史会话。V1 推荐输入包括：

- `raw_query`
- `session_context`
- `time_hint`
- `retrieval_budget`

这里的 `session_context` 不直接传整段历史对话，而是只传与当前问题相关的压缩摘要，用于承接多轮分析工作台中的必要上下文，避免噪声扩散和 token 膨胀。

其中，`time_hint` 不收敛为单一字符串，而设计为轻量时间约束对象，用于同时表达：

- 用户显式提到的时间范围
- 系统默认采用的检索时间窗
- 当前是否允许回看较老事件或历史背景

这样设计的目的，是让 `collect_event_context` 同时服务于新闻检索边界和后续报告中的时间解释，而不是把时间理解成必须精确命中的单字段。

其中，`retrieval_budget` 不作为业务语义字段理解，而作为 `collect_event_context` 的轻量执行约束集合，用于限制该步骤内部的检索探索边界。它主要约束：

- 新闻检索轮数上限
- Query Rewrite / HyDE 等增强手段的触发上限
- 单步允许的局部重试次数
- 最终带回的新闻证据数量

这样设计的目标，是在允许 Step 内部探索与重试的同时，避免无限检索、无限重写和无限回退，使延迟、成本与 trace 复杂度都保持在可控范围内。

`collect_event_context` 的主输出先收敛为两块：

- `event_context`
- `event_entities`

其中：

- `event_context` 负责描述“这件事发生了什么”，更偏向事件摘要、新闻证据、时间解释和初步影响链。
- `event_entities` 负责描述“这件事里有哪些结构化对象”，更偏向供后续 `analyze_targets` 消费的实体骨架。

V1 中，`event_context` 至少包含以下 5 类字段：

- `event_summary`
- `time_interpretation`
- `news_evidence`
- `impact_hypotheses`
- `context_confidence`

它们分别用于表达：

- `event_summary`：当前事件背景的压缩摘要
- `time_interpretation`：系统如何理解新闻时间、事件时间与时间不确定性
- `news_evidence`：支撑事件背景判断的新闻证据集合
- `impact_hypotheses`：当前阶段形成的初步影响链假设
- `context_confidence`：当前事件上下文抽取与整合结果的整体置信度

其中，`impact_hypotheses` 不设计为单一自然语言段落，而设计为“初步影响链假设列表”。每条假设至少包含：

- 影响对象
- 影响方向
- 影响机制
- `target_scope`
- 置信度

其中，`target_scope` 用于表达这条假设初步指向的对象范围，例如：

- 行业 / 主题
- 产业链环节
- 公司集合范围

每条 `impact_hypothesis` 还应带有轻量的 `supporting_evidence_refs`，用于回指本轮 `news_evidence` 中支撑该假设形成的新闻证据集合。V1 不要求它像最终 RAG 引用那样精细到页码或段落，但需要保证后续步骤能够追溯“这条初步影响假设最初是基于哪些新闻形成的”。

这样设计的目的，是让 `collect_event_context` 的输出可以被后续 `analyze_targets` 直接消费，而不是在步骤之间反复从自由文本中重新解析“可能利好什么、可能冲击什么、为什么会这样”。

这样收缩的原因是：

- 让 Planner Step 更像“任务阶段”，而不是工具名或过细的检索内部动作。
- 避免 Plan 层和 Needs 层出现过多一一对应，使结构更清晰。
- 保留 Step 内部探索、重试和局部回退的空间，不在 V1 过早拆成过多主节点。

V1 的执行模型采用：

- 每轮用户输入只生成一个主 intent
- 每轮用户输入只生成一个主 plan
- 按主 plan 进入内部 loop 执行

V1 不采用频繁整轮重规划，而采用三层 loop 设计：

- 主 plan 层：决定本轮任务要经过哪些主要步骤，整体保持稳定
- step 内部层：允许单个步骤内部进行有限次探索、补检索、query rewrite、重试
- step 间局部回退层：当后续步骤发现前序结果不足时，允许有限回退到关键前一步补做，而不是整轮推翻重来

这种设计的目标是：

- 保持执行链路清晰、可解释、可追踪
- 支持检索失败、证据不足、引用矛盾等情况下的局部修正
- 避免 V1 过早演化成不稳定的自发散式重规划 Agent

### Executor

执行工具和 RAG 调用，并把结果写入标准 observation。

### Advanced RAG Pipeline

负责：

- Query Rewrite
- Dense Retrieval
- Sparse Retrieval
- Fusion
- Rerank
- Parent Expand
- Citation Assembly

### Critic / Verifier

负责检查：

- 是否回答了用户问题
- 关键结论是否有引用
- 逻辑链是否断裂
- 证据之间是否存在明显冲突

### Report Generator

负责生成分析报告主视图，以及中间 trace 的可视化展示。

## 6. V1 输出形态

### 主输出

分析报告型输出，建议包括：

- 结论摘要
- 影响链条
- 候选标的 / 板块
- 年报 / 公告证据
- 不确定性说明

### 辅助输出

可展开 trace 面板，展示：

- 路由结果
- 计划步骤
- 检索证据
- rerank 结果
- critic 校验记录

## 7. V1 技术选型

- Agent 编排：LangGraph
- 后端 API：FastAPI
- 前端工作台：Streamlit
- 会话与结构化存储：SQLite
- 向量检索：Qdrant
- Embedding：BGE-M3
- Rerank：bge-reranker
- 主推理模型：云端 LLM API
- PDF 解析：MinerU + pdfplumber
- 外部信息：Tavily + AKShare

### 检索策略

V1 不采用纯向量检索，而采用 Hybrid Retrieval 思路：

- Dense Retrieval：Qdrant
- Sparse Retrieval：SQLite FTS5 实现的 BM25 / 关键词检索
- Query Rewrite：默认启用轻量改写
- Fusion：RRF
- Rerank：bge-reranker
- Parent Expand：子块召回，父块回填

### V1 Query Rewrite 策略

V1 纳入轻量 Query Rewrite，但不做重型多轮 Query Decomposition。

推荐做法：

- 保留用户原始 Query
- 额外生成少量面向检索的改写查询
- 改写查询可分别偏向新闻检索、公告/年报检索和结构化工具检索

这样做的目标是：

- 提升口语化 Query 的检索稳定性
- 提升事件型 Query 到知识库语料的命中率
- 在不显著增加复杂度的情况下增强 Hybrid Retrieval

### V1 HyDE / Query2Doc 策略

V1 接受 HyDE / Query2Doc 作为检索增强技术，但不作为所有 Query 的默认主链路。

建议策略：

- 轻量 Query Rewrite 默认开启
- HyDE / Query2Doc 作为条件触发增强

更适合触发 HyDE / Query2Doc 的情况包括：

- Query 过于口语化或抽象
- 初始检索质量较差
- 追问场景中用户表达较短、指代较强

这样设计的原因是：

- Rewrite 成本低、收益稳定，适合作为默认能力
- HyDE / Query2Doc 收益可能明显，但也可能把模型先验引入检索
- 对金融场景而言，V1 更强调可控、可解释、可评测，而不是一开始把所有高级增强默认打开

V1 不为 HyDE / Query2Doc 单独引入复杂分类器。
在首版中，更适合使用简单、可解释的触发规则，例如：

- Query 很短且指代较强
- 初始检索结果相关性明显较差
- follow-up 追问省略严重
- 事件型 Query 过于抽象、缺少明确检索术语

### V1 切片策略

V1 采用 Parent-Child Chunking，但不做过于复杂的多套文档切片规则。

V1 统一面向 PDF 解析结果，采用简化的两级切片策略：

- Parent：优先按解析出的结构块切分
- Parent 兜底：当结构不可靠时，退回段落簇切分
- Child：默认以单段或相邻 1 到 2 段为主，不采用句子级作为默认粒度
- 表格：V1 仅做轻量支持，不做重型结构重建

这里的“结构块”不强求必须是标准章节 / 小节，也可以是：

- 标题下的一组连续段落
- 一张表格及其邻近说明
- 一个完整事项段

这里的“段落簇”指连续 2 到 4 个语义相近段落组成的块。
这里的 child 设计为中等偏细粒度，目标是在召回精度、rerank 稳定性和证据语义完整性之间取得平衡。

V1 不采用以下做法作为默认主策略：

- 纯固定长度切片
- 默认句子级切片
- 针对不同文档维护多套复杂切片规则

这样设计的原因是：

- 保留 Parent-Child Chunking 的核心价值
- 避免对 PDF 结构质量做过强假设
- 控制 V1 的实现复杂度
- 为后续版本的表格增强和结构增强保留空间

### V1 Sparse Retrieval 实现

V1 的稀疏检索层使用 SQLite FTS5。

选择原因：

- 与 V1 已选的 SQLite 技术栈一致
- 单机开发成本低
- 足够支持首版的术语命中、字段命中和关键词检索
- 适合作为 Hybrid Retrieval 的稀疏召回层

V1 不引入 Elasticsearch、OpenSearch 等更重的搜索系统。
后续版本再根据语料规模、复杂查询和部署需求，决定是否升级稀疏检索实现。

### V1 Fusion 策略

V1 的 dense retrieval 和 sparse retrieval 结果使用 RRF 进行融合。

选择原因：

- RRF 实现简单，适合作为 V1 的稳定基线
- RRF 依据排名进行融合，不依赖不同检索分数的直接可比性
- 适合 BM25 与 dense retrieval 的混合召回场景
- 能较稳定地提升多路召回结果的整体质量

V1 不采用基于原始检索分数的复杂加权融合作为默认方案。

### V1 Rerank 策略

V1 的 rerank 放在 fusion 之后执行。

推荐流程：

- Dense Retrieval
- Sparse Retrieval
- RRF Fusion
- 对 child chunks 做 rerank
- 再执行 Parent Expand

这样设计的原因是：

- dense 与 sparse 先完成候选合并
- reranker 能在统一候选池上进行更准确的排序
- child chunk 粒度更细，适合做相关性精排
- parent chunk 体积较大，不适合作为 V1 rerank 的主对象

因此 V1 的 rerank 目标是：

- 对融合后的 child chunks 做精排
- 选出最能支撑当前问题的少量高质量证据片段
- 再把这些片段对应的 parent 上下文回填给后续生成与引用链路

### V1 Parent Expand 与 Parent 粒度

V1 的 parent expand 不是“命中 child 后回填整章”，而是：

- child 命中后，回填其对应的完整 parent 单元
- 如果多个 child 属于同一个 parent，则做去重合并
- 最终只把少量高质量 parent 提供给 LLM

这里的“完整 parent”指的是“完整回填一个受控大小的语义单元”，而不是回填整章或超大章节块。

parent 的设计原则：

- parent 必须足够完整，能为 child 提供必要上下文
- parent 也必须受控，不能大到显著推高 prompt token 成本
- 如果解析出的结构块过大，应在建库阶段进一步切分为多个 parent
- V1 默认采用中等尺度的 parent，不走偏小或偏大的极端策略

因此，V1 的 parent 更适合定义为：

- 一个小节下的连续 2 到 5 段
- 一张表格及其紧邻说明
- 一个公告事项段及其相邻解释段

而不是：

- 整个章节
- 超长的多页文本块

这一设计的核心目标是同时满足：

- Parent Expand 后上下文完整
- prompt token 成本可控
- 最终引用和证据回填更自然

具体的 token / 字数阈值不在当前阶段先拍死，后续应结合建库样本、rerank 效果和 prompt 预算做小规模基准测试后确定。

## 8. 结构化数据层

V1 采用中量版结构化数据层，支持：

- 股票主题、行业、概念筛选
- 部分核心财务指标查询
- 基础排序、过滤、对比

V1 不追求一开始做成完整 XBRL 财务数据库。

## 9. 评测策略

V1 从第一天就建设评测体系。

评测维度至少包括：

- 路由正确率
- 检索质量
- 引用完整性
- 最终答案质量

评测形式：

- 构建标准 Query 集
- 构建黄金证据和参考答案
- 支持人工评分与半自动评分结合

## 10. 待继续明确的问题

- Router 的具体字段枚举与 JSON Schema 如何定义
- Planner Step 的 JSON Schema 如何定义
- Follow-up classifier 的标签集合与判定逻辑
- Parent-Child Chunking 的具体长度阈值如何确定
- Qdrant collection 与 metadata filter 设计
- V1 首批标准 Query 集如何选取
- V1 语料导入与索引构建流水线如何组织

## 11. 失败降级与 Guardrails

V1 的失败处理与 guardrails 先按 4 类收敛，而不是把所有异常情况混在一起处理。

### 11.1 信息不足型

指系统没有拿到足够可靠的外部事件背景，例如：

- 新闻结果过少
- 新闻时间信息不清晰
- 事件表述过于模糊

此时系统不应直接输出强结论，而应：

- 明确说明事件背景不充分
- 输出低置信度初步判断
- 必要时引导用户补充更具体的事件描述

### 11.2 映射失败型

指系统基本理解事件，但无法稳定映射到主题、产业链或候选公司范围，例如：

- 事件过于宏观
- 概念映射冲突
- 主题范围过宽

此时系统不应硬筛具体公司，而应：

- 先停留在主题 / 板块层
- 输出候选方向而非公司级结论
- 显式说明尚未进入公司级验证

### 11.3 证据不足型

指系统已经形成分析对象，但年报 / 公告证据不足以支撑某个结论，例如：

- RAG 召回弱
- 证据只能部分支撑 claim
- 引用与结论不完全对齐

此时系统应：

- 降低结论强度
- 将该判断标记为推测性或待验证
- 避免把证据不足的判断写成确定结论

### 11.4 超范围型

指用户问题超出 V1 的深度能力边界，例如：

- 要求短线股价预测
- 要求完整估值模型
- 要求全市场实时覆盖

此时系统应：

- 明确说明当前范围不支持
- 给出可支持的替代路径
- 不假装已经具备超范围能力

V1 的总体原则是：

- 能降级就降级
- 不能可靠降级就明确收口
- 不在证据不足时硬答

V1 的降级输出建议采用统一结构，而不是按失败类型随意变化表达方式。统一输出至少应覆盖：

- 当前结论能推进到哪一步
- 当前无法继续推进的是哪一步
- 原因是什么
- 用户还可以如何继续

这样设计的好处是，即使系统未能完成完整分析，也仍然保持产品体验上的稳定性、可解释性和 Agent 感，而不是突然退化成一句模糊的“无法回答”。

## 12. 评测与验收思路

V1 的评测框架先按 4 个维度组织，而不只评“最终答案像不像”。评测需要同时观察系统是否走对链路、是否拿到了足够可用的证据、是否形成了可靠输出，以及在失败时是否能稳定收口。

### 12.1 路由与任务识别

这一维度用于评估：

- Router 是否正确识别当前 query 的 `intent`
- 是否正确判断 `follow_up_type`
- 是否选择了合理的主路径或主计划骨架

这一维度的意义在于：如果第一步任务理解就走错，后续检索、RAG 和报告生成即使做得再好，也会建立在错误路径之上。

### 12.2 检索与证据质量

这一维度用于评估：

- 新闻检索是否拿到了关键事件背景
- Hybrid Retrieval 是否召回了足够相关的年报 / 公告证据
- rerank 后的证据是否真正支撑当前问题
- parent expand 后的上下文是否足以支撑生成与引用

这一维度不只看“找到了东西”，而是看“找回来的东西能不能组成一条可用证据链”。

### 12.3 最终答案质量

这一维度用于评估：

- 最终分析报告是否回答了用户的核心问题
- 结论、影响链条、候选对象和证据是否组织清楚
- 引用是否完整、自然、可追溯
- 是否对不确定性给出合理说明

这一维度对应的是用户最终看到的交付质量。

### 12.4 降级与边界处理

这一维度用于评估：

- 信息不足时，系统是否主动降低结论强度
- 映射失败时，系统是否停留在主题 / 板块层，而不是硬给公司级结论
- 证据不足时，系统是否显式标注待验证或推测性判断
- `out_of_scope` 时，系统是否能清晰收口，而不是假装自己具备该能力

这一维度的目标是评估：系统在无法完整解决问题时，是否仍然像一个可信、克制、可解释的 Agent。

### 12.5 V1 人工评分方式

V1 的人工评测不应依赖“凭感觉打分”，而应采用：

- 小规模 `golden queries`
- 每题一份 `rubric`
- 多维度 `0 / 1 / 2` 打分

这种设计的目标是，把人工评估从“主观喜欢 / 不喜欢”转成“按明确标准判断”。

V1 的每条 `golden query` 不一定需要一份唯一标准长答案，但至少应包含：

- 该题的核心任务类型
- 预期应走的主要链路或大致路径
- 关键评分维度
- 每个维度的 `0 / 1 / 2` 判断标准

可优先采用的评分维度示例包括：

- 路由是否正确
- 事件背景是否充分
- 候选方向或候选公司是否合理
- 证据是否直接且有支撑力
- 不确定性处理是否合理

V1 的人工评测应优先追求：

- 标准稳定
- 缺陷可定位
- 后续可复用

而不是一开始就追求大而全的标准问答集或完全自动化 benchmark。

### 12.6 黄金题分桶

V1 的 `golden queries` 应先按场景类型分桶，而不是把所有题目混在一个集合里。这样做的目的是：

- 让评测集对应 V1 的核心能力结构
- 方便后续定位是哪一类场景出现质量问题
- 方便后续按场景扩展，而不是重写整个评测集

V1 首批评测题库可先按下列 4 类组织：

- 首轮事件分析题
- 证据展开题
- 对比分析题
- 超范围 / 降级题

V1 首批 `golden queries` 的规模建议先控制在 `12` 条左右。这个规模足以覆盖上述 4 类题型，又不会让首版人工评测负担过重，比较适合作为可迭代的起点。

这四类题型分别对应：

- 主线新建分析能力
- 多轮 `drilldown` 能力
- `comparative_analysis` 能力
- `guardrails` 与失败处理能力

## 13. 非目标与风险边界

V1 的设计需要通过明确非目标来保护范围，避免在实现阶段不断膨胀并稀释展示重点。以下能力不属于 V1 的核心交付目标：

### 13.1 不做全市场深度覆盖

V1 虽然可以具备全 A 股元数据层，但不承诺对所有主题、所有公司都具备同等深度的年报 / 公告验证能力。深度能力主要聚焦已确认的主主题与辅主题。

### 13.2 不做完整投研平台

V1 的目标是展示 Agent、RAG 和业务建模能力，而不是一次性做成完整投研终端。因此不追求资讯流、自选股、组合管理、回测、交易执行等外围能力。

### 13.3 不做高频实时性承诺

V1 可以接入实时新闻，但不承诺毫秒级或分钟级的全市场事件监控，也不承诺公告 / 财报实时全量同步更新。重点是“真实感 + 可复现”，而不是“极速行情系统”。

### 13.4 不做重型财务引擎或估值系统

V1 会有结构化数据查询和基础筛选能力，但不做完整 XBRL 勾稽、三表建模、DCF / 可比估值引擎，也不做严肃量化研究平台。

### 13.5 不做开放式通用金融聊天机器人

V1 不是一个什么都答的泛金融助手。它优先支持“事件影响分析 + 年报 / 公告验证 + 多轮追问”这条主链，超出范围的问题应降级或收口，而不是硬答。

## 14. 开放问题与待确认项

这份设计稿的目标是完成范围收敛与架构定向，而不是在探索阶段拍死所有实现细节。因此，在进入正式 spec 与 implementation plan 之前，仍保留以下几类待确认问题：

### 14.1 数据与语料侧

包括但不限于：

- 首批主主题与辅主题的样本公司具体如何选择
- 年报 / 公告的首批覆盖年份范围如何确定
- 新闻源、概念映射源与结构化数据源的最终组合如何落定

### 14.2 RAG 调优侧

包括但不限于：

- `parent / child` 的最终粒度阈值如何结合样本测试确定
- `SQLite FTS5` 的中文检索效果是否需要额外增强
- HyDE / Query2Doc 的触发阈值和触发条件如何进一步校准

### 14.3 Agent 策略侧

包括但不限于：

- 各主步骤的局部重试上限如何设定
- `follow_up_type` 中 `redirect` 与 `expand` 的边界如何进一步细化
- 何时直接降级、何时继续补检索或补验证的策略如何统一

### 14.4 评测与产品化侧

包括但不限于：

- 首批约 `12` 条黄金题的具体题目如何分配
- `trace` 面板最终展示到什么粒度
- V2 起是否引入更多自动化评测辅助能力
