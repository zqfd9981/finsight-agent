# Retrieval Strategy Classifier Training Design

## 背景

截至 2026-07-02，FinSight 已经完成以下与事件链路相关的基础能力：

- `event_impact_analysis` 四阶段主链已可执行
- `collect_event_context` 已有真实 stage runner，但外部检索仍主要依赖空实现
- 最新设计已将外部检索拆成两层：
  - `EventSearchProvider`
  - `DisclosureSearchProvider`
- 最新设计同时引入了一个新的控制面决策点：
  - `RetrievalStrategyClassifier`

该分类器的职责非常克制：它只负责判断 `collect_event_context` 的检索起手式，输出固定三类策略标签：

- `event_primary`
- `disclosure_primary`
- `dual_primary`

这不是一个开放式生成任务，而是一个中文短文本三分类任务。当前主流程不应被这项训练工作阻塞，因此需要把它设计成一个可并行推进的独立子项目：

- 主流程可以继续使用 stub / fallback
- 训练子项目可以独立积累数据、离线训练、离线评测
- 训练完成后再以可插拔方式接入控制面

## 目标

本设计的目标是定义一个独立、可训练、可评测、可渐进集成的 `RetrievalStrategyClassifier` 训练方案，重点包括：

- 明确分类任务边界与标签定义
- 明确首版模型形态与输入表示
- 定义数据集格式、标注规范、质检流程
- 定义训练、验证、评测、打包与接入边界
- 明确如何在不阻塞主流程的前提下推进该子项目

## 非目标

- 本轮不直接实现训练代码
- 不在本设计中绑定任何商业 API 推理依赖
- 不把分类器扩展成 planner、summarizer 或 target analyzer
- 不要求首版覆盖所有事件类型和所有问法变体
- 不要求首版直接训练多头任务

## 首版核心决策

### 1. 分类器独立于主流程推进

主流程继续保留保守 fallback，不等待训练完成。

也就是说：

- 训练未完成时，控制面仍可运行
- 分类器接入是增量增强，不是主流程前置条件

### 2. 正式模型采用 `StructBERT + 单头 3 分类`

首版正式模型选型：

- 中文编码器模型：`StructBERT`
- 任务头：单头分类头
- 标签集合：
  - `event_primary`
  - `disclosure_primary`
  - `dual_primary`

不推荐首版直接做多头，原因是当前最关键问题只有一个：先查什么。若一开始加入多头，会把任务从单一策略分类扩张成多任务学习，导致标注、训练和误差分析复杂度不必要上升。

### 3. `Qwen2.5-0.5B-Instruct` 仅作为冷启动辅助

`Qwen2.5-0.5B-Instruct` 不作为正式线上分类器，而作为以下用途的辅助工具：

- 预标注候选样本
- 生成困难问法改写
- 生成边界样本候选

最终真标签必须经过人工校正，不能直接把伪标签视为训练真值。

### 4. 首版只训练主标签，不训练独立 confidence 头

首版模型输出只有一个离散标签，不单独训练：

- `confidence`
- `needs_local_rag`
- `query_type`

如需近似置信度，先使用 softmax 概率分布或 top1/top2 margin 作为推理辅助特征，而不是把它变成额外监督任务。

## 任务定义

### 分类目标

给定：

- 用户 query
- `RouterResult` 中的结构化字段
- 可选 `SessionContext` 轻量字段

分类器需要预测 `collect_event_context` 的首选检索策略：

#### `event_primary`

优先查事件搜索层。

适用问题特征：

- 核心在于理解外部事件本身
- 更像“最近发生了什么”“这个事件本身怎么发展”
- 没有强烈公司披露中心

示例：

- `红海局势最近发生了什么`
- `美国新关税政策主要影响哪些方向`

#### `disclosure_primary`

优先查披露搜索层。

适用问题特征：

- 核心在于公司公告、财报、业绩预告、披露事项
- 问题主语通常已明确落在单个公司或少数公司

示例：

- `宁德时代扩产公告意味着什么`
- `这家公司业绩预告是否超预期`

#### `dual_primary`

事件搜索层与披露搜索层都应作为主源。

适用问题特征：

- 问题同时需要理解事件背景与 A 股/公司影响
- 常见于“某外部事件会影响哪些公司/板块”

示例：

- `红海局势升级利好哪些A股航运股`
- `关税升级对哪些出口链公司冲击最大`

## 输入表示设计

### 输入来源

首版输入只使用轻量、稳定、已结构化的字段：

- `query`
- `intent`
- `event`
- `themes`
- `target`
- `time_scope`
- 可选 `session_topic`

其中来源分别为：

- `query`：`AnalysisRequest.query`
- `intent`：`RouterResult.intent`
- `event/themes/target/time_scope`：`RouterResult.entities`
- `session_topic`：`SessionContext.active_topic`

### 输入模板

首版不直接喂大段 JSON，而统一序列化为短文本模板：

```text
[QUERY]
红海局势升级利好哪些A股航运股？

[INTENT]
event_impact_analysis

[EVENT]
红海局势升级

[THEMES]
航运, 油运

[TARGET]
A股航运股

[TIME_SCOPE]
recent

[SESSION_TOPIC]
无
```

设计理由：

- 稳定
- 可调试
- 适合 encoder 分类
- 更容易做数据集版本管理

### 缺失字段填充

若某字段缺失，统一填 `无`，而不是留空。

原因：

- 避免序列结构漂移
- 降低训练样本格式不一致

## 数据集设计

### 推荐规模

首版有效标注样本目标：

- 最低可用：`300`
- 推荐首版：`600`
- 上限预期：`800`

### 类别分布

三类尽量均衡，推荐目标：

- `event_primary`：200
- `disclosure_primary`：200
- `dual_primary`：200

若冷启动阶段无法完全均衡，允许：

- 每类不少于 120
- 但不得让任何单类超过总量的 50%

### 数据来源

首版数据源按优先级分三层：

#### 1. 真实历史 query

优先级最高。

来源包括：

- 真实用户问法
- 历史调试 query
- 现有测试与 demo 请求

优势：

- 最贴近真实分布
- 能覆盖口语化、模糊问法

#### 2. 基于现有测试样本的人工改写

从已有以下来源扩展：

- `tests/integration/test_event_impact_analysis_flow.py`
- `tests/unit/test_semantic_routing_and_planning.py`
- 现有设计文档中的代表性 query

改写原则：

- 保留语义
- 改变问法
- 引入口语、短句、省略、行业俗称

#### 3. 小模型辅助预标

使用 `Qwen2.5-0.5B-Instruct` 做：

- 候选标签建议
- 边界样本生成
- 难例改写

但所有样本必须经过人工审校。

### 数据集格式

建议使用 JSONL，每行一个样本：

```json
{
  "sample_id": "rsc_000123",
  "query": "红海局势升级利好哪些A股航运股？",
  "intent": "event_impact_analysis",
  "event": "红海局势升级",
  "themes": ["航运", "油运"],
  "target": "A股航运股",
  "time_scope": "recent",
  "session_topic": "",
  "label": "dual_primary",
  "label_source": "human_reviewed",
  "notes": "同时需要事件背景和A股影响判断"
}
```

### 数据集版本

至少维护三份逻辑文件：

- `raw`：原始待标样本
- `labeled`：已人工确认标签的样本
- `splits`：训练/验证/测试切分清单

不建议把切分结果直接写死在单一文件里，以便后续重切分和复现实验。

## 标注规范

### 标注原则

标注员判断的是：

**“为了高效拿到足够事件上下文，应该先查哪类源”**

而不是：

- 哪个答案最终更好写
- 哪种分析路径更“聪明”
- 哪种检索量更大

### 主判定问题

标注时先问自己：

1. 这个 query 首先要不要先理解外部事件本身？
2. 这个 query 首先要不要先看公司/公告/披露？
3. 这两个是否都明显必需？

### 标注判定准则

#### 标 `event_primary`

当满足以下倾向时：

- 不先理解事件，就无法开展后续分析
- query 没有明显单公司公告中心
- 公司层只是后续可能扩展，不是第一步主问题

#### 标 `disclosure_primary`

当满足以下倾向时：

- query 本身就是公司内生事项
- 主语已明确落在公司披露
- 不需要先大量补充外部事件背景

#### 标 `dual_primary`

当满足以下倾向时：

- query 同时在问外部事件 + A 股/公司影响
- 任意单源都明显不够
- 若只看外部新闻或只看披露，都会丢失关键上下文

### 边界样本处理

对于模糊 query：

- 先按“首个必要检索动作”判断
- 若事件理解和公司披露同等必要，则标 `dual_primary`

不允许使用：

- `unknown`
- `other`

这两类标签。首版必须收敛为三分类。

### 双人复核

推荐标注流程：

1. 首标
2. 复标抽检
3. 分歧样本入冲突池
4. 最终裁决并沉淀到标注手册

对于以下样本，必须进入冲突池：

- 首标与复标不一致
- 事件/披露边界很模糊
- `dual_primary` 是否成立存在分歧

## 训练设计

### 模型结构

首版使用：

- `StructBERT encoder`
- `dropout`
- `linear classifier head`

输出维度为 3，对应三个标签。

### 训练目标

- 标准 cross entropy loss

不引入：

- focal loss
- contrastive objective
- 多任务 loss

除非首版评测表明明显类别失衡难以收敛。

### 切分策略

推荐：

- train：70%
- validation：15%
- test：15%

切分要求：

- 分层抽样，保持三类比例近似
- 同一语义簇的近重复改写不要跨集合泄漏
- 明显来源于同一原句的 paraphrase 应放在同一 split

### 训练轮次与早停

首版不把训练超参写死成唯一值，但建议：

- batch size：按机器资源自适应
- epoch：3 到 10
- 以 validation macro F1 做 early stopping

### 输出产物

训练完成后至少要有：

- 模型权重目录
- 标签映射文件
- 输入模板版本号
- 训练配置快照
- 评测报告

## 评测设计

### 首版核心指标

必须关注以下四项：

1. `macro F1`
2. 每类 precision / recall / F1
3. `dual_primary` 的 recall
4. 误判样本回放清单

### 推荐门槛

首版建议以如下门槛作为“可接入候选版”：

- macro F1 >= 0.80
- `dual_primary` recall >= 0.75
- 任一单类 F1 不低于 0.70

若未达门槛：

- 不阻塞主流程
- 分类器继续停留在线下实验状态

### 误判分析要求

每轮实验必须产出误判分析，至少覆盖：

- `dual_primary -> event_primary`
- `dual_primary -> disclosure_primary`
- `event_primary <-> disclosure_primary`

这些是对主流程影响最大的误路由类型。

## 与主流程的解耦设计

### 分类器接口

主流程只依赖一个稳定接口：

- `RetrievalStrategyClassifier`

而不是依赖具体训练脚本或具体模型框架。

### 接入前状态

在正式模型未准备好前，主流程使用：

- `StubRetrievalStrategyClassifier`
- 或极薄 fallback 实现

### 接入后状态

当线下评测达到门槛后，再新增：

- `StructBertRetrievalStrategyClassifier`

并通过配置切换启用。

### 失败回退

即使正式分类器启用，也必须支持：

- 模型文件缺失
- 推理异常
- 非法标签输出

这些情况下统一回退到保守默认值：

- `event_primary`

## 推荐目录边界

为了与现有仓库结构一致，建议按以下边界组织：

- `backend/src/finsight_agent/control_plane/orchestrator/`
  - 放分类器接口与线上推理适配
- `backend/src/finsight_agent/evaluation/datasets/`
  - 放标注数据 schema、加载器、切分元数据
- `backend/src/finsight_agent/evaluation/runners/`
  - 放线下评测 runner
- 新增训练相关目录
  - 放训练脚本、配置、导出逻辑

是否把训练脚本放进 `evaluation` 下，不在本设计中强制锁死；但要求：

- 线上推理代码
- 线下训练代码
- 数据与评测代码

三者边界必须清楚，不能互相缠绕。

## 里程碑建议

### 里程碑 1：数据与标注闭环

完成：

- 数据 schema
- 标注手册
- 300+ 条已校正样本
- 稳定切分文件

### 里程碑 2：首版训练与离线评测

完成：

- `StructBERT` 单头 3 分类训练
- 评测报告
- 误判回放

### 里程碑 3：可插拔线上接入

完成：

- `StructBertRetrievalStrategyClassifier`
- stub / real classifier 可切换
- 推理失败回退

## 风险与缓解

### 风险 1：真实 query 分布不足

缓解：

- 优先收集真实请求
- 让小模型只做预标和扩样，不做真值替代

### 风险 2：`dual_primary` 类过于稀疏

缓解：

- 人工定向补充“外部事件 + A 股影响”类 query
- 单独监控该类召回

### 风险 3：标注标准漂移

缓解：

- 固化标注手册
- 保留冲突池与裁决记录

### 风险 4：训练工作阻塞主流程

缓解：

- 主流程保留 stub/fallback
- 分类器未达标前不替换线上默认路径

## 结论

`RetrievalStrategyClassifier` 应被视为一个独立训练子项目，而不是主流程必须等待完成的前置任务。首版正式方案推荐：

- `StructBERT + 单头 3 分类`
- `Qwen2.5-0.5B-Instruct` 仅作冷启动辅助
- 先完成数据、标注、评测闭环
- 达标后再以可插拔方式接入 `collect_event_context`

这样既能保证设计方向正确，也能避免分类器训练工作卡住整个 FinSight 事件分析主线。
