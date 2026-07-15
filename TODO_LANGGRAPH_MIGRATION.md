# 改造文档：Orchestrator 全流程 LangGraph 化

> **状态**：设计完成，待实施
> **目标**：把 router → strategy_classifier → stage_planner → stage 执行 → trace 组装 → session 快照的全流程建模为 LangGraph StateGraph，为 ReAct 反思（方案 C）铺路
> **原则**：重写编排层，保留执行单元（stage_runners 内部逻辑不改）

---

## 一、为什么要做

### 当前架构的根本缺陷

当前 [workbench_backend_api/service.py](backend/src/finsight_agent/workbench_backend_api/service.py) 的 `_execute_request` 是**过程式编排**：

```
session = load_context()
router_result = router_service.route()           # 图外预执行
strategy = classifier.classify()                  # 图外预执行
stages = stage_planner.resolve_stages()           # 图外预执行（查表）
for stage in stages:                              # 线性 for 循环
    result = STAGE_RUNNERS[stage](execution_state)  # mutable dict 传状态
trace = build_trace_blocks()
session.save_snapshot()
```

三个架构缺陷：

1. **状态是 mutable dict，无 schema**：`execution_state: dict[str, object]`，任何 key 任何 value，缺了运行时才崩
2. **stage 间依赖隐式**：`retrieve_evidence` 硬编码读 `execution_state["collect_event_context"]`，谁先跑谁后跑只有 stage_planner 的查表隐式保证
3. **无法表达运行时分支**：stages 列表执行前一次性确定，执行中改不了。ReAct 的"查不到→反思→补查"做不到

### LangGraph 化后的架构

全流程建模为 StateGraph：**每个处理步骤都是节点**（含 router），State 在节点间显式流转，条件边表达动态分支。

---

## 二、State Schema 设计

替代当前的 `execution_state: dict[str, object]` + 散落在各处的局部变量。

```python
# backend/src/finsight_agent/control_plane/orchestrator/state.py（新增）

from __future__ import annotations
from typing import Any, TypedDict
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext
from shared.contracts.final_response import FinalResponse
from shared.contracts.trace_block import TraceBlock
from .models import StageExecutionResult, StageObservation


class OrchestratorState(TypedDict, total=False):
    """LangGraph 全流程状态对象，在所有节点间传递。

    设计原则：
    - 每个字段对应一个节点的输出（或输入）
    - 显式声明依赖关系，替代旧的 execution_state 隐式 dict
    - total=False：所有字段可选，节点只读自己需要的字段、只写自己产出的字段
    """

    # ── 输入（invoke 时注入）──
    request: AnalysisRequest
    session_context: SessionContext
    run_id: str

    # ── load_session 节点输出 ──
    # session_context 已在输入字段，load_session 节点可能 enrich 它

    # ── route 节点输出 ──
    router_result: RouterResult

    # ── classify_strategy 节点输出（仅 event_impact_analysis）──
    strategy_payload: dict[str, str] | None

    # ── plan_stages 节点输出 ──
    stages: list[str]
    stage_constraints: dict[str, dict[str, object]]
    response_mode: str

    # ── stage 执行节点输出（每个 stage 一个字段，替代 execution_state[stage_name]）──
    collect_event_context: StageExecutionResult | None
    analyze_targets: StageExecutionResult | None
    query_structured_data: StageExecutionResult | None
    retrieve_evidence: StageExecutionResult | None
    synthesize_answer: StageExecutionResult | None

    # ── 累积观察（所有 stage 执行后汇总）──
    stage_observations: list[StageObservation]

    # ── 最终输出 ──
    final_response: FinalResponse | None
    guardrail_response: Any | None

    # ── trace 组装节点输出 ──
    trace_blocks: list[TraceBlock]

    # ── 错误处理 ──
    error: dict[str, Any] | None  # {"stage": "...", "message": "...", "exception": ...}
```

### 与旧 execution_state 的对应关系

| 旧（execution_state dict） | 新（OrchestratorState 字段） |
|---|---|
| `execution_state["collect_event_context"]` | `state["collect_event_context"]` |
| `execution_state["query_structured_data"]` | `state["query_structured_data"]` |
| 散落局部变量 `router_result` | `state["router_result"]` |
| 散落局部变量 `stages` | `state["stages"]` |
| 散落局部变量 `strategy_payload` | `state["strategy_payload"]` |
| `result.stage_observations` | `state["stage_observations"]` |
| `result.final_response` | `state["final_response"]` |
| `result.guardrail_response` | `state["guardrail_response"]` |

---

## 三、节点设计

每个节点是一个纯函数：`(state) -> partial_state`（只返回要更新的字段）。

### 节点清单

| 节点名 | 职责 | 读 State | 写 State | 对应旧代码 |
|---|---|---|---|---|
| `load_session` | 加载会话上下文 | request | session_context | SessionService.load_context |
| `route` | LLM 路由 | request, session_context | router_result | RouterService.route |
| `classify_strategy` | event 策略分类（仅 event） | router_result, session_context | strategy_payload | _classify_event_strategy |
| `plan_stages` | 查表规划 stage 列表 | router_result, strategy_payload | stages, stage_constraints, response_mode | stage_planner.resolve_stages |
| `guardrail` | out_of_scope 短路 | router_result | guardrail_response | should_short_circuit + build_guardrail |
| `query_structured_data` | 结构化数据查询 | request, router_result, stage_constraints | query_structured_data, stage_observations | STAGE_RUNNERS["query_structured_data"] |
| `collect_event_context` | 事件上下文收集 | request, router_result, stage_constraints | collect_event_context, stage_observations | STAGE_RUNNERS["collect_event_context"] |
| `analyze_targets` | 目标分析 | request, router_result, session_context, stage_constraints, collect_event_context | analyze_targets, stage_observations | STAGE_RUNNERS["analyze_targets"] |
| `retrieve_evidence` | 证据检索（内含 RetrievalAgent LangGraph） | request, router_result, stage_constraints, collect_event_context, analyze_targets | retrieve_evidence, stage_observations | STAGE_RUNNERS["retrieve_evidence"] |
| `synthesize_answer` | 答案合成 | router_result, stage_constraints, 所有上游 stage 输出 | synthesize_answer, final_response, stage_observations | STAGE_RUNNERS["synthesize_answer"] |
| `build_trace` | 组装 trace_blocks | router_result, stages, response_mode, stage_observations, strategy_payload, final_response, guardrail_response | trace_blocks | _build_trace_blocks + trace_builder |
| `save_snapshot` | 保存会话快照 | request, router_result, stages, 所有 stage 输出 | (无返回，副作用) | SessionService.build_snapshot + save_snapshot |

### 节点函数示例

```python
# backend/src/finsight_agent/control_plane/orchestrator/graph.py（新增）

def route_node(state: OrchestratorState) -> dict:
    """路由节点：调用 RouterService，输出 router_result。"""
    router_result = _deps.router_service.route(
        query=state["request"].query,
        session_context=state.get("session_context"),
    )
    return {"router_result": router_result}


def query_structured_data_node(state: OrchestratorState) -> dict:
    """结构化数据查询节点：包装 stage_runner。"""
    stage_result = run_query_structured_data_stage(
        request=state["request"],
        router_result=state["router_result"],
        stage_constraints=state["stage_constraints"].get("query_structured_data"),
        execution_state=state,  # 兼容旧接口（stage_runner 内部读上游）
        structured_data_service=_deps.structured_data_service,
    )
    observation = build_stage_observation(
        observation_id=f"obs_{uuid.uuid4().hex[:8]}",
        input_summary={"query": state["request"].query, "intent": state["router_result"].intent},
        stage_result=stage_result,
    )
    new_observations = state.get("stage_observations", []) + [observation]
    return {"query_structured_data": stage_result, "stage_observations": new_observations}
```

### 依赖注入：用 dataclass 持有 service 依赖

节点函数是纯函数，但需要访问 service（RouterService、StructuredDataService 等）。用闭包注入：

```python
@dataclass
class NodeDependencies:
    """图构建时注入的 service 依赖，节点函数通过闭包访问。"""
    router_service: RouterService
    structured_data_service: StructuredDataService
    reporting_service: ReportingService
    retrieval_facade_factory: Callable[[], RetrievalFacade]
    external_context_retriever: ExternalContextRetriever
    target_analysis_service: TargetAnalysisService
    session_service: SessionService
    strategy_classifier: Any
    llm_client: LlmClient


_deps: NodeDependencies | None = None  # 模块级单例，graph 构建时设置


def configure_dependencies(deps: NodeDependencies) -> None:
    global _deps
    _deps = deps
```

---

## 四、图拓扑设计

### 完整图结构

```
                                    START
                                      │
                                      ▼
                                load_session
                                      │
                                      ▼
                                    route
                                      │
                          ┌───────────┴───────────┐
                          │                       │
                    out_of_scope            其他 intent
                          │                       │
                          ▼                       ▼
                    guardrail              classify_strategy
                          │                       │
                          │                       ▼
                          │                 plan_stages
                          │                       │
                          │           ┌───────────┴───────────┐
                          │           │                       │
                          │     metric_lookup         event_impact_analysis
                          │           │               evidence_lookup
                          │           │               general_finance_qa
                          │           ▼                       │
                          │   query_structured_data            │
                          │           │              ┌─────────┴─────────┐
                          │           │              │                   │
                          │           │     event_primary        disclosure/dual
                          │           │              │                   │
                          │           │              ▼                   ▼
                          │           │    synthesize_answer   collect_event_context
                          │           │              │                   │
                          │           │              │           ┌───────┴───────┐
                          │           │              │           │               │
                          │           │              │     dual_primary    disclosure_primary
                          │           │              │           │               │
                          │           │              │           ▼               │
                          │           │              │    analyze_targets       │
                          │           │              │           │               │
                          │           │              │           ▼               ▼
                          │           │              │    retrieve_evidence ◄────┘
                          │           │              │           │
                          │           │              │           ▼
                          │           └──────────────┴──► synthesize_answer
                          │                                  │
                          ▼                                  ▼
                    build_trace ◄───────────────────────────┘
                                      │
                                      ▼
                                save_snapshot
                                      │
                                      ▼
                                     END
```

### 条件边函数

```python
def _after_route(state: OrchestratorState) -> str:
    """route 节点后的条件边：按 intent 分流。"""
    intent = state["router_result"].intent
    if intent == Intent.OUT_OF_SCOPE.value:
        return "guardrail"
    return "classify_strategy"


def _after_plan(state: OrchestratorState) -> str:
    """plan_stages 节点后的条件边：按 stages 列表路由到不同的 stage 链。

    这里用 stages[0] 作为入口节点，后续节点用线性边连接。
    """
    stages = state.get("stages", [])
    if not stages:
        return "build_trace"  # 空列表直接走 trace（guardrail 场景）
    return stages[0]  # 第一个 stage 节点名


def _after_stage(state: OrchestratorState, current_stage: str) -> str:
    """每个 stage 执行后的条件边：找 stages 列表里的下一个 stage。

    如果当前 stage 是最后一个，走 build_trace。
    """
    stages = state.get("stages", [])
    try:
        idx = stages.index(current_stage)
    except ValueError:
        return "build_trace"
    if idx + 1 >= len(stages):
        return "build_trace"
    return stages[idx + 1]
```

### 图构建代码

```python
def build_graph(deps: NodeDependencies) -> Any:
    """构建并编译 LangGraph StateGraph。"""
    configure_dependencies(deps)

    graph = StateGraph(OrchestratorState)

    # ── 添加所有节点 ──
    graph.add_node("load_session", load_session_node)
    graph.add_node("route", route_node)
    graph.add_node("classify_strategy", classify_strategy_node)
    graph.add_node("plan_stages", plan_stages_node)
    graph.add_node("guardrail", guardrail_node)
    graph.add_node("query_structured_data", query_structured_data_node)
    graph.add_node("collect_event_context", collect_event_context_node)
    graph.add_node("analyze_targets", analyze_targets_node)
    graph.add_node("retrieve_evidence", retrieve_evidence_node)
    graph.add_node("synthesize_answer", synthesize_answer_node)
    graph.add_node("build_trace", build_trace_node)
    graph.add_node("save_snapshot", save_snapshot_node)

    # ── 入口 ──
    graph.set_entry_point("load_session")

    # ── 线性边 ──
    graph.add_edge("load_session", "route")
    graph.add_edge("classify_strategy", "plan_stages")
    graph.add_edge("guardrail", "build_trace")
    graph.add_edge("build_trace", "save_snapshot")
    graph.add_edge("save_snapshot", END)

    # ── 条件边 ──
    graph.add_conditional_edges(
        "route",
        _after_route,
        {"guardrail": "guardrail", "classify_strategy": "classify_strategy"},
    )
    graph.add_conditional_edges(
        "plan_stages",
        _after_plan,
        # 动态返回值：第一个 stage 节点名 或 "build_trace"
    )
    # 每个 stage 节点执行后，条件边找下一个 stage
    for stage_name in ["query_structured_data", "collect_event_context",
                       "analyze_targets", "retrieve_evidence", "synthesize_answer"]:
        graph.add_conditional_edges(
            stage_name,
            functools.partial(_after_stage, current_stage=stage_name),
        )

    return graph.compile()
```

### 关键设计决策：为什么用"stages 列表驱动条件边"而不是硬编码多条路径

stage_planner 的查表逻辑 `(intent, strategy) → stages` 本质就是动态拓扑。与其在图里硬编码 6 条路径（metric/event_primary/event_disclosure/event_dual/evidence/general_qa），不如让 `plan_stages` 节点输出 `stages` 列表，条件边按列表顺序串联。

**好处**：
1. 图拓扑简洁（只有一套通用 stage 链逻辑）
2. 新增 intent 只需改 stage_planner，图结构不变
3. 为 Step B ReAct 铺路——ReAct 只需在某个 stage 后加条件边，不影响其他路径

---

## 五、SSE 事件映射

当前 [workbench_backend_api/service.py](backend/src/finsight_agent/workbench_backend_api/service.py) 手动 emit `stage_started` / `stage_finished` 事件。LangGraph 化后用 `graph.stream()` 的回调机制。

### 方案：LangGraph stream + 自定义 callback

```python
def execute_with_streaming(request, event_callback):
    """流式执行，把 LangGraph 节点事件映射到 SSE。"""
    emitter = RunEventEmitter(run_id=..., event_callback=event_callback)

    # LangGraph stream 逐节点 yield 状态更新
    for chunk in graph.stream(initial_state, stream_mode="updates"):
        # chunk 格式：{node_name: {updated_fields}}
        for node_name, updates in chunk.items():
            _emit_node_event(emitter, node_name, updates)

def _emit_node_event(emitter, node_name, updates):
    """把 LangGraph 节点事件映射到现有 SSE 事件格式。"""
    # 节点名 → stage 名映射
    STAGE_NAME_MAP = {
        "load_session": "session_loading",
        "route": "routing",
        "classify_strategy": "strategy_classification",
        "plan_stages": "stage_planning",
        "query_structured_data": "query_structured_data",
        "collect_event_context": "collect_event_context",
        "analyze_targets": "analyze_targets",
        "retrieve_evidence": "retrieve_evidence",
        "synthesize_answer": "synthesize_answer",
        "build_trace": "trace_building",
        "save_snapshot": "snapshot_saving",
    }
    stage_name = STAGE_NAME_MAP.get(node_name, node_name)
    # emit started + finished（LangGraph stream 在节点完成后才 yield）
    emitter.emit_stage_started(stage_name=stage_name, message=f"{stage_name} started")
    emitter.emit_stage_finished(stage_name=stage_name, status="success", message=f"{stage_name} finished")
```

### 注意：LangGraph stream 的时序限制

LangGraph 的 `stream(stream_mode="updates")` 在**节点完成后**才 yield，无法在节点开始时 emit。如果需要"开始时 emit started"的实时反馈，有两个方案：

**方案 A（推荐）**：用 LangGraph 的 `callback` 机制（`BaseCallbackHandler`），支持 `on_chain_start` / `on_chain_end` 事件，能拿到节点开始/结束的实时回调。

**方案 B**：保持当前的 `bind_active_run_event_emitter` 机制，在节点函数内部手动 emit started/finished（节点函数开头 emit started，结尾 emit finished）。改动最小，但没充分利用 LangGraph 的能力。

建议方案 B 作为过渡（改动最小），后续再升级到方案 A。

---

## 六、改动文件清单

### 新增文件

| 文件 | 职责 |
|---|---|
| `orchestrator/state.py` | OrchestratorState TypedDict 定义 |
| `orchestrator/graph.py` | StateGraph 构建 + 节点函数 + 条件边 + 依赖注入 |
| `orchestrator/node_deps.py` | NodeDependencies dataclass（service 依赖容器） |

### 重写文件

| 文件 | 改动说明 |
|---|---|
| `workbench_backend_api/service.py` | `_execute_request` 从过程式编排改为 `graph.invoke/stream`；删除手动 emit 逻辑（移到节点内部） |
| `orchestrator/service.py` | `OrchestratorService.execute` 重写为图执行入口；删除 for 循环 + 硬编码依赖注入 if/elif 链 |

### 改接口文件

| 文件 | 改动说明 |
|---|---|
| `orchestrator/stage_planner.py` | `resolve_stages` 函数改为 `plan_stages_node` 节点函数；查表逻辑不变，输出写入 State |
| `control_plane/router/service.py` | `RouterService.route` 保持不变，但被 `route_node` 包装调用 |
| `orchestrator/trace_builder.py` | `build_execution_trace_block` 改为 `build_trace_node` 节点函数；从 State 读取所有数据 |
| `control_plane/session/service.py` | `load_context` / `build_snapshot` / `save_snapshot` 被 `load_session_node` / `save_snapshot_node` 包装 |

### 不改文件（核心价值）

| 文件 | 为什么不改 |
|---|---|
| `orchestrator/stage_runners/query_structured_data.py` | 纯函数，节点函数内部调用它 |
| `orchestrator/stage_runners/collect_event_context.py` | 同上 |
| `orchestrator/stage_runners/analyze_targets.py` | 同上 |
| `orchestrator/stage_runners/retrieve_evidence.py` | 同上（内部已含 RetrievalAgent LangGraph） |
| `orchestrator/stage_runners/synthesize_answer.py` | 同上 |
| `capabilities/retrieval/retrieval_agent.py` | 已经是 LangGraph，保持原样 |
| `capabilities/structured_data/*` | 业务逻辑层，与编排无关 |

---

## 七、向后兼容策略

### 阶段 1：双轨运行（1-2 天）

- 保留旧的 `OrchestratorService.execute`（for 循环版）
- 新增 `OrchestratorService.execute_graph`（LangGraph 版）
- 通过 feature flag `FINSIGHT_USE_LANGGRAPH_ORCHESTRATOR` 切换
- 两种实现共享同一套 stage_runners，确保行为一致

### 阶段 2：验证 + 切换（1 天）

- 用现有的 19 组测试用例（8 大行业 4 种 response_mode）验证两种实现结果一致
- 验证 SSE 流式事件时序正确
- 验证 trace_blocks 结构一致
- 切换默认到 LangGraph 版

### 阶段 3：清理（半天）

- 删除旧的 for 循环代码
- 删除 feature flag
- 删除 `execution_state: dict` 相关的辅助函数

---

## 八、Step B ReAct 反思铺路

Step A 完成后，ReAct 只需在图里加条件边和两个节点：

```
query_structured_data ──is_degraded & metric_type=derived──→ reflect_node
                    ──else──→ synthesize_answer

reflect_node ──需要补查原料──→ query_ingredients_node
           ──无需补查──→ synthesize_answer

query_ingredients_node ──→ calculate_derived_node ──→ synthesize_answer
```

这在 for 循环架构里无法表达（stages 列表执行前固定），在 StateGraph 里是加两个节点 + 两个条件边的事。

### ReAct 需要的新 State 字段

```python
class OrchestratorState(TypedDict, total=False):
    # ... Step A 字段 ...

    # ── ReAct 反思字段（Step B 新增）──
    reflect_decision: dict | None  # {"need_ingredients": bool, "missing": [...], "reason": "..."}
    ingredient_results: dict[str, StageExecutionResult]  # 原料指标查询结果
    derived_calculation: dict | None  # 衍生指标计算结果
```

---

## 九、风险与对策

| 风险 | 对策 |
|---|---|
| LangGraph stream 的 SSE 时序与旧实现不一致 | 阶段 1 双轨运行 + 19 组测试验证 |
| stage_runners 内部读 `execution_state` 的硬编码 key 不兼容 | 节点函数传入的 state 兼容旧 key（state 字段名与 stage_name 一致） |
| RetrievalAgent 内部的 LangGraph 与外层 LangGraph 嵌套 | 无冲突——内层是独立 compile 的子图，外层只看节点的输入输出 |
| 条件边返回值与节点名不匹配导致图构建失败 | 图构建时校验所有条件边返回值都是已注册节点名 |
| `total=False` 导致节点读到 None | 节点函数用 `state.get("field", default)` 防御性读取 |

---

## 十、验证标准

- 19 组测试用例（8 大行业 4 种 response_mode）全部通过
- SSE 流式事件时序与旧实现一致（stage_started → stage_finished）
- trace_blocks 结构与旧实现一致（routing + stage_planning + execution 三个 block）
- out_of_scope guardrail 短路正常
- event_impact_analysis 的 3 个 strategy（event_primary/disclosure/dual）路径正确
- `execution_state` 完全移除，无残留引用

---

## 十一、实施顺序

1. **新增 state.py**：定义 OrchestratorState TypedDict
2. **新增 node_deps.py**：定义 NodeDependencies dataclass
3. **新增 graph.py**：实现所有节点函数 + 条件边 + 图构建
4. **改 stage_planner.py**：`resolve_stages` 适配为节点函数（逻辑不变，输出写 State）
5. **改 orchestrator/service.py**：新增 `execute_graph` 方法，feature flag 切换
6. **改 workbench_backend_api/service.py**：`_execute_request` 支持 feature flag 切换
7. **双轨验证**：19 组测试用例对比
8. **清理旧代码**：删除 for 循环 + execution_state
