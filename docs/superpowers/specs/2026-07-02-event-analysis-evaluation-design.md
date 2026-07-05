# Event Analysis Evaluation Design

## 背景

截至 2026-07-02，FinSight 已经完成以下首版闭环：

- `semantic-routing-and-planning` 已能稳定产出 `event_impact_analysis` 的四阶段 `Plan`
- orchestrator 已打通：
  - `metric_lookup`
  - `evidence_lookup`
  - `event_impact_analysis`
- `event_impact_analysis` 已接入首版双层外部检索：
  - `GDELT` 事件搜索
  - `CNInfo + SSE` 官方披露搜索
- `collect_event_context` 已支持条件 RAG
- `analyze_targets` 已支持候选发现补检索与诚实降级

当前主缺口已经不再是“链路能不能跑”，而是：

- 不同事件类型下，双层外部检索的命中质量如何
- 哪些 query 会导致策略误判、候选为空或过度降级
- provider、planner、候选发现和后续分类器训练，是否有统一可复用的评测样本

现有仓库已经有：

- 单元测试
- 集成测试
- 少量端到端 happy path 验证

但这些更偏“功能不坏”，还不足以回答：

- 这条事件链在真实 query 上表现是否稳定
- 哪个 provider 组合更好
- `RetrievalStrategyClassifier` 训练后是否真的提升

因此，下一阶段需要一套轻量但正式的事件评测与回放框架。

## 目标

本设计的目标是为 `event_impact_analysis` 定义一个不阻塞主流程、可持续扩展的评测闭环，重点包括：

- 建立一批可版本化管理的事件样本 `fixtures`
- 建立一个离线 replay runner，批量回放现有事件主链
- 定义统一结果 schema，沉淀可比较的回放结果
- 定义首版最小评测检查项，用于：
  - provider 调优
  - `RetrievalStrategyClassifier` 训练前后对比
  - 事件主链回归验证

## 非目标

- 本轮不实现复杂评分平台或可视化评测面板
- 不引入 LLM judge 作为首版主评估方式
- 不要求首版自动评估结论“是否投资正确”
- 不把分类器训练与评测框架强耦合在一起
- 不替代现有 `unittest` / `integration test`
- 不修改任何已有主 spec，只新增本轮设计与计划文档

## 设计原则

### 1. 评测框架服务于主链，而不是另起一套平台

首版评测应该直接复用现有：

- `WorkbenchBackendApiService`
- `OrchestratorService`
- 事件主链四阶段

这样评测观察到的结果才真正反映当前系统行为，而不是测试专用旁路行为。

### 2. 功能回归与质量评测分层

现有测试继续负责：

- 代码是否可运行
- 主链是否断裂
- 固定 happy path 是否通过

新增评测框架负责：

- 不同事件类型的行为差异
- provider 命中质量
- 候选发现和降级行为
- 分类器与策略切换效果

### 3. 样本必须版本化、可追踪、可人工维护

首版样本不应藏在测试代码里，而应作为独立 `fixtures` 管理，满足：

- 可人工增删改
- 可逐步扩量
- 可被训练、回放、回归共同复用

### 4. 先做确定性检查，再谈复杂评分

首版先回答这些确定性问题：

- 是否命中预期 `intent`
- 是否走了预期检索策略
- 是否意外空候选
- 是否过度降级
- 是否产出了基本可读的最终响应

而不是一上来就做“整体质量分”或“LLM 主观打分”。

## 方案对比

### 方案 A：只扩充现有集成测试

做法：

- 在 `tests/integration/` 里继续增加更多事件用例
- 用断言覆盖更多场景

优点：

- 开发快
- 直接复用现有测试体系

缺点：

- 样本和断言强绑定，难以复用
- 不适合做批量回放、结果归档、provider 对比
- 后续分类器训练和误判分析复用价值低

### 方案 B：只做离线 replay 脚本

做法：

- 单独做一套脚本和 JSONL 样本
- 不接现有测试体系

优点：

- 灵活
- 适合快速批量跑样本

缺点：

- 容易变成平行世界
- 与现有测试和 CI 关系弱
- 长期维护上容易漂移

### 方案 C：`tests + fixtures + replay runner` 三件套

做法：

- 保留现有集成测试作为最小功能回归
- 新增独立事件样本 `fixtures`
- 新增 replay runner 与结果 schema
- 后续测试、provider 调优、分类器训练共用同一批样本

优点：

- 同时兼顾功能回归和质量评测
- 样本可复用、可版本化
- 后续扩 provider、分类器、缓存策略时都有统一尺子

缺点：

- 首版设计工作比单纯加测试略多
- 需要先定义样本 schema 和结果 schema

## 推荐方案

采用 **方案 C：`tests + fixtures + replay runner` 三件套**。

决策理由：

1. 现有主链已经足够复杂，单纯加测试用例无法承担长期质量观测任务
2. 事件评测样本后续不仅要服务测试，还要服务 provider 调优和分类器训练
3. replay runner 可以在不引入复杂平台的前提下，为系统提供批量回放和误判复盘能力

## 目标架构

```text
event_eval fixtures
        |
        v
  replay runner
        |
        v
WorkbenchBackendApiService / OrchestratorService
        |
        v
  replay results
        |
        v
evaluation checks / regression summary
```

## 组件设计

### 1. Event Eval Fixtures

新增一套专门的事件评测样本，例如：

- `event_primary`
- `disclosure_primary`
- `dual_primary`

每条样本建议至少包含以下字段：

```json
{
  "case_id": "event_dual_001",
  "query": "红海局势升级利好哪些A股航运股？",
  "expected_intent": "event_impact_analysis",
  "expected_strategy": "dual_primary",
  "allow_degraded": true,
  "min_target_count": 1,
  "expected_target_keywords": ["航运", "中远海能"],
  "notes": "外部世界事件 + A股标的影响问题"
}
```

字段语义：

- `case_id`
  - 样本稳定标识
- `query`
  - 用户问题原文
- `expected_intent`
  - 预期路由意图
- `expected_strategy`
  - 预期检索策略：
    - `event_primary`
    - `disclosure_primary`
    - `dual_primary`
- `allow_degraded`
  - 是否允许降级
- `min_target_count`
  - 最少候选数门槛
- `expected_target_keywords`
  - 可选目标关键词，不要求严格等值
- `notes`
  - 人工说明，用于后续维护

首版不要求样本特别大，但建议先覆盖：

- 每类至少 5 到 10 条
- 合计 15 到 30 条事件样本

### 2. Replay Runner

新增一个离线 replay 入口，用于：

- 逐条读取样本
- 调用当前真实事件主链
- 收集执行结果
- 落成标准化结果记录

首版 runner 建议直接消费：

- `WorkbenchBackendApiService`

而不是手工拼一半链路。这样能够覆盖：

- routing
- planning
- orchestration
- response
- trace

### 3. Replay Result Schema

每条回放结果建议统一记录：

```json
{
  "case_id": "event_dual_001",
  "query": "红海局势升级利好哪些A股航运股？",
  "actual_intent": "event_impact_analysis",
  "actual_strategy": "dual_primary",
  "response_type": "success",
  "degraded": false,
  "target_count": 2,
  "evidence_ref_count": 3,
  "summary": "……",
  "failure_reason": null,
  "target_keywords": ["中远海能", "招商轮船"]
}
```

其中：

- `actual_strategy`
  - 优先从 trace 或 `collect_event_context` 相关结果里抽取
- `degraded`
  - 根据 `StageObservation` 或最终 response 中的降级语义判断
- `target_count`
  - 从 `analyze_targets` / 最终 report 中抽取
- `evidence_ref_count`
  - 从 stage observations 汇总

首版不要求把所有内部细节都序列化，只保留后续误判分析最需要的核心字段。

### 4. Evaluation Checks

首版只做确定性或半确定性检查：

1. `intent` 检查
- `actual_intent` 是否等于 `expected_intent`

2. 检索策略检查
- `actual_strategy` 是否等于 `expected_strategy`

3. 降级检查
- 当 `allow_degraded=false` 时，若实际降级则记为失败

4. 候选空洞检查
- `target_count` 是否低于 `min_target_count`

5. 关键词检查
- `expected_target_keywords` 中至少命中一部分，避免完全偏题

6. 响应成形检查
- 最终 response 是否存在 summary 或 report blocks

这些检查先输出：

- `pass`
- `fail`
- `warn`

不强制首版合成单个总分。

## 文件边界建议

首版建议新增一个轻量目录，例如：

```text
backend/src/finsight_agent/evaluation/
    event_eval/
        fixtures/
        replay.py
        models.py
        checks.py
```

职责边界：

- `fixtures/`
  - 保存事件样本 JSONL / JSON
- `models.py`
  - 保存样本与结果 schema
- `replay.py`
  - 批量回放入口
- `checks.py`
  - 评测检查逻辑

同时保留：

- `tests/integration/`
  - 继续放少量代表性端到端集成测试

## 数据流

### 回放流程

1. 读取事件样本 fixture
2. 构造 `AnalysisRequest`
3. 调用 `WorkbenchBackendApiService.build_response(...)`
4. 从 envelope / trace / stage observations 中抽取结果
5. 生成标准化 `ReplayResult`
6. 跑 evaluation checks
7. 输出汇总结果

### 后续复用方向

这套样本和回放结果后续可以同时服务：

- provider 调优
- `RetrievalStrategyClassifier` 训练前后的对比
- 误判回放
- 事件链回归测试

## 降级与失败语义

首版需要明确区分三种结果：

### 1. 正常通过

- 命中预期 intent
- 检索策略合理
- 目标和响应成形

### 2. 合法降级

- 事件背景建立成功
- 但目标不足或证据不足
- 且样本允许降级

### 3. 失败

- 路由偏离
- 检索策略明显错位
- 响应空洞
- 或样本不允许降级但实际发生降级

首版评测结果应该能明确区分这三类，而不是一律当失败处理。

## 测试策略

首版测试建议分两层：

### 1. 结构层测试

验证：

- fixture 解析是否稳定
- replay result 提取是否稳定
- evaluation checks 是否按预期工作

### 2. 主链层测试

保留少量代表性样本作为集成测试，继续验证：

- 事件主链可真实执行
- 外部 provider / 条件 RAG 接线未退化

## 实施顺序建议

建议按以下顺序推进：

1. 先定义 fixture schema 与 replay result schema
2. 再补第一批事件样本
3. 再做 replay runner
4. 再做 evaluation checks
5. 最后把代表性样本回收到 `tests/integration`

## 成功标准

本设计落地后，项目应具备以下能力：

- 能批量回放一批事件 query
- 能稳定记录每条样本的 intent、strategy、降级与候选结果
- 能快速发现：
  - provider 命中变差
  - 分类策略切错
  - 候选发现退化
  - 最终响应空洞
- 能为后续分类器训练和 provider 优化提供统一评测基线
