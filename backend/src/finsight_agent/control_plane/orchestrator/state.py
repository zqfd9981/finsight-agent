"""LangGraph 全流程状态对象定义。

替代旧的 ``execution_state: dict[str, object]`` + 散落在 workbench_backend_api/service.py
的局部变量。每个节点只读自己需要的字段、只写自己产出的字段。
"""

from __future__ import annotations

from typing import Any, TypedDict

from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.final_response import FinalResponse
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext
from shared.contracts.stage_observation import StageObservation
from shared.contracts.trace_block import TraceBlock

from .models import StageExecutionResult


class OrchestratorState(TypedDict, total=False):
    """LangGraph 状态对象，在所有节点间传递。

    设计原则：
    - 每个字段对应一个节点的输出（或输入）
    - 显式声明依赖关系，替代旧的 execution_state 隐式 dict
    - total=False：所有字段可选，节点只读自己需要的字段、只写自己产出的字段
    """

    # ── 输入（invoke 时注入）──
    request: AnalysisRequest
    session_context: SessionContext | None
    run_id: str

    # ── route 节点输出 ──
    router_result: RouterResult

    # ── classify_strategy 节点输出（仅 event_impact_analysis）──
    strategy_payload: dict[str, str] | None

    # ── plan_stages 节点输出 ──
    stages: list[str]
    stage_constraints: dict[str, dict[str, object]]
    response_mode: str

    # ── stage 执行节点输出（每个 stage 一个字段，替代 execution_state[stage_name]）──
    # 字段名与 StageName 枚举值保持一致，兼容 stage_runners 内部对 execution_state 的硬编码读取
    collect_event_context: StageExecutionResult | None
    analyze_targets: StageExecutionResult | None
    query_structured_data: StageExecutionResult | None
    reflect_and_requery: StageExecutionResult | None
    retrieve_evidence: StageExecutionResult | None
    synthesize_answer: StageExecutionResult | None
    verify_answer: StageExecutionResult | None

    # ── 累积观察（所有 stage 执行后汇总）──
    stage_observations: list[StageObservation]

    # ── 最终输出 ──
    final_response: FinalResponse | None
    guardrail_response: Any | None

    # ── trace 组装节点输出 ──
    trace_blocks: list[TraceBlock]

    # ── 错误处理 ──
    error: dict[str, Any] | None  # {"stage": "...", "message": "...", "exception": ...}
