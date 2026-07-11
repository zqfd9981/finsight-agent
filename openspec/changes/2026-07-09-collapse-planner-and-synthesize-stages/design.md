## Context

FinSight Agent V1 在重构前的控制面是三层结构 `router → planner → orchestrator`：

- router 负责意图识别，输出 `RouterResult`
- planner（[backend/src/finsight_agent/control_plane/planner/](backend/src/finsight_agent/control_plane/planner/)）用 LLM 生成 plan 骨架，并把 time hint、retrieval budget、preferred output 等约束编码进 plan
- orchestrator 按 plan 逐 stage 执行，收集 observation

这一结构在实践中暴露出三个问题：

1. **planner 的 LLM 分支实际不生效**。planner 内部确实会调 LLM 产出 plan，但只要产出的 stages 与受支持集合不一致就退回 rule-based 兜底；线上观测下来 LLM plan 几乎总被兜底覆盖，等于这一层 LLM 调用只带来延迟和 prompt 维护成本，却没有真实决策权。
2. **3 个 synthesize stage 代码高度重复**。`synthesize_brief_answer` / `synthesize_event_answer` / `synthesize_report` 三个 stage runner 的执行骨架几乎一致，差别只在 prompt 模板与个别字段，维护三套 runner + 三套契约枚举带来大量冗余 diff。
3. **泛财经问题被 `out_of_scope` 误杀**。router 对"降息对债市意味着什么"这类泛财经常识问题一律返回 `out_of_scope` 触发 guardrail 拒答，既损害体验也浪费了 LLM 直答能力。

`openspec/changes/archive/2026-07-06-make-workbench-runnable/` 的 design 已经验证 workbench 可启动，本 change 在可启动基础上把控制面收敛为目标态 `router → classifier（仅 event 触发）→ orchestrator（查表 + 执行）`。

## Goals / Non-Goals

**Goals:**

- 删除 planner 层，把 stage 编编职责收敛为 orchestrator 内的纯查表函数 `resolve_stages`，去掉无效 LLM 调用
- 合并 3 个 synthesize stage 为单个 `synthesize_answer`，按 `response_mode` 分发 prompt 模板
- 新增 `general_finance_qa` 轻路径，承接泛财经常识问题，LLM 直答不走检索
- 收紧 `out_of_scope`，仅对投资建议/荐股/股价预测与非金融问题触发
- 删除 `Plan` 契约与相关 feature_flag，控制面不再跨模块暴露 plan 骨架

**Non-Goals:**

- 不把 classifier 合并进 router（classifier 是训练好的子策略分类器，保留独立）
- 不做 `retrieve_evidence` re-plan loop（V1 步骤级回退保持有限有界）
- 不做回答质量 rubic / 评测自动打分（属于 report-trace-and-evaluation 后续 change）
- 不引入新的外部检索源或缓存层

## Decisions

### D1. 删 planner 而非保留

**Decision**：删除整个 planner 目录与 `Plan` 契约，把 stage 编排职责交给 orchestrator 层的纯查表函数。

**Rationale**：planner 的 LLM 分支影响力为零——产出 stages 不一致就退回 rule，等于 LLM 调用从未生效，却要承担一轮额外延迟与 prompt 维护成本。既然实际决策是规则化的，直接把规则固化成查表函数 `resolve_stages` 即可，既消除无效 LLM 调用，又减少一层抽象。删 `Plan` 契约是因为它原本就是跨模块暴露 planner 产物的载体，planner 消失后该契约没有消费者。

**Alternatives considered**：
- *保留 planner 但改成纯查表（reject）*：多保留一层无意义的薄包装，与 orchestrator 职责重叠
- *保留 planner LLM 但放宽兜底（reject）*：会引入不受控的 stage 序列，破坏 V1 受支持集合约束

### D2. 合并为单 synthesize_answer 按 response_mode 分发

**Decision**：把 `synthesize_brief_answer` / `synthesize_event_answer` / `synthesize_report` 合并为单个 `synthesize_answer` stage，内部按 `response_mode`（`direct` / `brief_answer` / `event_answer` / `report`）切换 prompt 模板。

**Rationale**：3 个 stage 的执行代码高度重复，差别仅在 prompt 模板与个别字段，维护三套 runner + 三套契约枚举的 diff 成本远高于在一个 runner 里做模板分发。`response_mode` 已经是 stage_constraints 的显式字段，把它作为唯一分发键既清晰又可被 trace 直接消费。

**Alternatives considered**：
- *保留 3 个 stage 但共用一个 runner 基类（reject）*：仍要维护三套枚举与三处注册，没有真正减少表面积
- *按 intent 而非 response_mode 分发（reject）*：intent 与 response_mode 不是 1:1（如 event_impact_analysis 会落到 event_answer 或 report），用 response_mode 更精确

### D3. 新增 general_finance_qa 而非放宽 out_of_scope

**Decision**：新增 `general_finance_qa` intent 与 `response_mode=direct` 轻路径，泛财经问题走单 stage LLM 直答；`out_of_scope` 维持原语义只对非金融/投资建议/股价预测触发。

**Rationale**：泛财经问题与真正超范围问题需要不同处理路径——前者应被回答，后者应被拒答。如果把泛财经问题塞进 `out_of_scope` 再放宽 guardrail 语义，会让 `out_of_scope` 同时承载"拒答"和"直答"两种相反语义，破坏该 intent 的可读性与 trace 可解释性。新增独立 intent + 独立 response_mode 让两条路径各自清晰。

**Alternatives considered**：
- *放宽 out_of_scope 让 guardrail 直答（reject）*：让 out_of_scope 语义自相矛盾
- *把泛财经问题硬塞进 metric_lookup（reject）*：会触发结构化数据查询 stage，与问题性质不符

### D4. 保留 classifier 不合并进 router

**Decision**：保留 `event_impact_analysis` 的 strategy 三分类器（classifier）作为独立组件，仅在 event 触发时调用，不合并进 router。

**Rationale**：classifier 是训练好的子策略分类器（event_primary / disclosure_primary / dual_primary），准确率约 93.18%，属于专门的子模型；router 只做意图识别，把两类模型职责混在一起会让 router 既要懂意图又要懂 event 子策略，破坏单一职责。保留独立也便于单独评测与替换。

**Alternatives considered**：
- *把 classifier 合并进 router（reject）*：router 职责膨胀，且 classifier 训练/评测与 router 解耦
- *对所有 intent 都跑 classifier（reject）*：只有 event_impact_analysis 需要 strategy，多余调用浪费资源

### D5. stage_planner 放 orchestrator 层而非 router 层

**Decision**：`stage_planner.py` 与 `resolve_stages` 放在 `orchestrator/` 目录下，而非 `router/`。

**Rationale**：职责单一原则——router 只做意图识别，不应知道下游有哪些 stage；orchestrator 才是按 stage 执行的组件，stage 列表解析天然属于它的内部决策。把查表函数放 orchestrator 层也让"router 输出 → orchestrator 查表执行"的数据流单向清晰，避免 router 反向依赖 stage 集合。

**Alternatives considered**：
- *放 router 层（reject）*：让 router 反向依赖 stage 集合，破坏意图识别与执行的解耦
- *独立成 control_plane/stage_planner/ 顶层模块（reject）*：为一个纯查表函数新增顶层包，过度抽象

## Risks / Trade-offs

- **[R1] router 误判 general_finance_qa** → router 对 `general_finance_qa` 与 `metric_lookup` / `event_impact_analysis` 的边界可能误判（如"降息对某公司利润影响"既像泛财经又像 event）。需补 router 评测样本与边界 case；短期靠 router rules 兜底。
- **[R2] synthesize_answer 分支臃肿** → 单 runner 内按 `response_mode` 分 4 个模板，若未来 response_mode 继续扩张会让该 runner 趋于臃肿。当前 4 个模板可接受，后续若超过 6 个需考虑按 mode 拆 sub-runner。
- **[R3] Plan 契约删除影响面** → `Plan` 删除后需排查所有跨模块 import 与 trace 序列化引用，避免遗留引用导致 ImportError 或 trace 渲染空字段。
- **[R4] classifier 准确率依赖** → stage 列表分叉依赖 classifier 的 strategy 判断，classifier 误判会选错 stage 序列（如把 dual_primary 误判为 event_primary 会跳过 analyze_targets）。V1 接受该风险，靠 observation 降级兜底。
- **[R5] out_of_scope 收紧后边界** → 收紧后部分原被打成 out_of_scope 的问题会改走 general_finance_qa，需确认 guardrail 规则同步更新，避免双重判定。

## Migration Plan

- 本 change 是控制面内"三层 → 两层 + 查表"重构，不涉及线上数据迁移
- 仓库现有 smoke 测试与 skeleton 测试（`tests/unit/test_project_skeleton.py` 等）必须继续通过
- 8 个受影响测试文件需同步调整：planner 单测移除、stage_planner 单测新增、synthesize_answer 单测合并、workbench 装配测试更新、router 规则测试更新 general_finance_qa / out_of_scope 边界
- 无需 transitional shim / feature_flag 回退路径——planner 已无外部消费者，直接删除即可
