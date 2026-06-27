# FinSight V1 并行交付治理文档

日期：2026-06-24
状态：生效中

## 1. 文档目的

这份文档定义 FinSight Agent V1 在并行开发阶段的模块分组、依赖关系、联调顺序和检查点规则。

它不替代 capability spec，也不替代项目状态看板。它负责回答：

- 这 7 个 spec 应该如何分组
- 哪些模块可以独立推进
- 哪些模块天然耦合更强
- 下游何时可以在上游未完成时先行开发

## 2. 模块分组

### 2.1 控制面

- `semantic-routing-and-planning`
- `conversation-session-state`
- `event-analysis-orchestration`

职责：

- 理解用户任务
- 继承多轮上下文
- 生成并执行主计划

特点：

- 三者之间耦合最强
- 更适合协同推进，而不是完全独立开发

### 2.2 数据与证据面

- `structured-market-data-support`
- `evidence-retrieval-pipeline`

职责：

- 提供主题/候选映射
- 提供本地证据检索与引用组装

特点：

- 相对独立
- 能较早通过 mock 输入开始开发

### 2.3 呈现与评测面

- `report-trace-and-evaluation`
- `analysis-workbench`

职责：

- 组织最终响应
- 暴露 trace
- 呈现 UI
- 支持人工评测

特点：

- 依赖共享 contract 明确
- 在 response mock 就绪后可以较快并行推进

## 3. 依赖关系图

```text
SessionContext
   -> RouterResult
   -> Plan
   -> Orchestrator
      -> Structured Market Data
      -> Evidence Bundle
   -> FinalResponse / TraceBlock / Guardrail
   -> Workbench / Evaluation
```

进一步展开为模块依赖：

```text
conversation-session-state
  -> semantic-routing-and-planning
  -> event-analysis-orchestration

semantic-routing-and-planning
  -> event-analysis-orchestration

structured-market-data-support
  -> event-analysis-orchestration

evidence-retrieval-pipeline
  -> event-analysis-orchestration
  -> report-trace-and-evaluation

event-analysis-orchestration
  -> report-trace-and-evaluation

report-trace-and-evaluation
  -> analysis-workbench
```

## 4. 并行开发原则

### 4.1 先冻结 contract，再放大并行度

真正能支撑并行开发的前提不是“大家都开始写”，而是：

- required fields 已冻结
- owner 已明确
- mock payload 已可用

### 4.2 控制面按小集群推进

控制面 3 个 spec 不建议完全分离推进。更适合的方式是：

- 先由一位 owner 主导 contract 对齐
- 再分工实现 router / session / orchestration
- 联调时按小集群验收

### 4.3 数据面和呈现面优先基于 mock 并行

一旦 `Plan`、`SessionContext`、`EvidenceBundle`、`FinalResponse` 的 mock payload 固定，下游就可以先开发：

- retrieval 组可以用固定 claim 输入调检索输出
- report / UI 组可以用固定 response mock 做渲染与 trace 展示

## 5. 联调顺序

建议采用下面的顺序，而不是七个 spec 同时随机联调：

### 阶段 1：Contract Ready

- 冻结共享对象 required fields
- 冻结 mock payload
- 明确 owner / producer / consumer

### 阶段 2：控制面骨架 Ready

- `SessionContext` 能产出稳定 mock
- `RouterResult` 和 `Plan` 能产出稳定 mock
- orchestrator 能按 mock plan 跑通主阶段占位执行

### 阶段 3：数据与证据面 Ready

- `structured-market-data-support` 能返回最小可用候选集
- `evidence-retrieval-pipeline` 能返回最小可用 `EvidenceBundle`

### 阶段 4：响应层 Ready

- `report-trace-and-evaluation` 能用 observation 和 evidence mock 组装 `FinalResponse`
- 能稳定输出 `TraceBlock`
- guardrail 响应结构固定

### 阶段 5：工作台联调 Ready

- `analysis-workbench` 能消费 success / degraded / guardrail 三类响应
- 首轮分析和一轮追问能跑通

## 6. 第一批联调检查点

### Checkpoint A：Contract Ready

通过条件：

- 共享 contract 文档存在
- 8 个共享对象的 required fields 已写明
- 每个对象至少有 1 个 mock payload

下游可启动：

- 所有 consumer 模块都可以开始本地开发

### Checkpoint B：Control Plane Mock Ready

通过条件：

- `SessionContext` mock 可用
- `RouterResult` mock 可用
- `Plan` mock 可用
- orchestrator 输入输出占位结构可跑通

下游可启动：

- response 层可开始接 observation mock
- workbench 可开始接 response mock

### Checkpoint C：Evidence Ready

通过条件：

- retrieval pipeline 能产出 `EvidenceBundle`
- support strength 语义固定

下游可启动：

- report 层开始拼接真实证据
- evaluation 开始构造黄金题样例

### Checkpoint D：Response Ready

通过条件：

- `FinalResponse` 稳定
- `TraceBlock` 稳定
- `GuardrailOrErrorResponse` 稳定

下游可启动：

- workbench 真正对接后端输出

## 7. 哪些模块可以在 Mock Ready 后先行开发

| 模块 | 先行条件 | 可先做的内容 |
| --- | --- | --- |
| `structured-market-data-support` | `event_entities` 输入 mock 就绪 | 主题映射、候选收敛、排序字段输出 |
| `evidence-retrieval-pipeline` | claim / target mock 就绪 | 检索、rerank、citation 输出 |
| `report-trace-and-evaluation` | observation 和 evidence mock 就绪 | 响应组装、trace 输出、guardrail 结构 |
| `analysis-workbench` | `FinalResponse` / `TraceBlock` mock 就绪 | 报告展示、trace 面板、错误态 |

## 8. Owner 协作要求

- 每个共享对象只有一个语义 owner
- 每个模块群至少有一个当前负责人
- 跨组字段争议优先回到 contract owner 决策
- 联调 blocker 必须更新到项目状态文档

## 9. 并行开发要用到的文件

### 9.1 全局文档

- `docs/finsight/shared-contracts-v1.md`
- `docs/finsight/parallel-delivery-governance.md`
- `docs/finsight/project-status.md`

这三份文档负责统一口径：

- 共享接口长什么样
- 并行开发规则是什么
- 全局现在推进到哪一步

### 9.2 模块进度文件

- `docs/finsight/modules/control-plane-status.md`
- `docs/finsight/modules/data-evidence-status.md`
- `docs/finsight/modules/presentation-eval-status.md`

这三份文档负责回答：

- 这个模块这轮要做什么
- 依赖什么输入
- 产出什么输出
- 当前卡在哪
- 下一次阶段检查要看什么

### 9.3 窗口协作模板

- `docs/finsight/templates/task-card.md`
- `docs/finsight/templates/sync-card.md`
- `docs/finsight/templates/handoff-card.md`

这三份模板分别负责：

- 任务卡：主控窗口派发短期任务
- 同步卡：阶段检查时汇报进展
- 交接卡：窗口暂停或关闭时交接

## 10. 文件怎么配合使用

### 10.1 主控窗口开工前看什么

主控窗口开工前至少看这几份：

- `shared-contracts-v1.md`
- `project-status.md`
- 对应模块的状态文件

主控窗口要先决定：

- 今天打哪个阶段目标
- 哪些输入可以视为冻结
- 哪几个短期任务可以并行开

### 10.2 工作窗口启动时看什么

工作窗口不要重新通读全部 spec，优先只看：

- 共享接口文档
- 自己模块的状态文件
- 主控窗口发下来的任务卡

这样做的目的，是把新窗口的启动成本压低。

### 10.3 阶段检查时怎么收口

到了阶段检查：

- 各工作窗口用同步卡汇报局部进展
- 主控窗口统一更新 `project-status.md`
- 主控窗口同步更新相关模块状态文件

如果某个窗口要暂停或关闭，再额外写交接卡。

## 11. 文档维护规则

- contract 变更先改 `shared-contracts-v1.md`
- 交付规则变更先改本文件
- 全局进展与 blocker 先改 `project-status.md`
- 模块内的本轮目标、活跃任务和卡点改对应模块状态文件
- 任务卡、同步卡、交接卡只记录当前窗口直接相关的信息
