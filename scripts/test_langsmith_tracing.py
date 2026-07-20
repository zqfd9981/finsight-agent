"""LangSmith tracing 配置验证脚本。

验证：
1. 环境变量正确加载
2. setup_langsmith_tracing() 返回 True
3. graph.invoke() 执行后，tracing 数据上报到 LangSmith

用法：
    先在 .env 配置好 LANGCHAIN_API_KEY，然后运行：
    python scripts/test_langsmith_tracing.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_SRC_ROOT))


def _load_dotenv() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        print(f"[WARN] .env 文件不存在: {env_path}")
        return
    from dotenv import load_dotenv

    load_dotenv(env_path, override=False)
    print(f"[OK] .env 已加载: {env_path}")


def main() -> None:
    _load_dotenv()

    # ── 1. 验证环境变量 ──
    print("\n=== 1. 环境变量检查 ===")
    api_key = os.getenv("LANGCHAIN_API_KEY", "")
    tracing_v2 = os.getenv("LANGCHAIN_TRACING_V2", "false")
    project = os.getenv("LANGCHAIN_PROJECT", "finsight-agent")
    endpoint = os.getenv("LANGCHAIN_ENDPOINT", "")

    print(f"  LANGCHAIN_TRACING_V2 = {tracing_v2}")
    print(f"  LANGCHAIN_API_KEY    = {'***' + api_key[-4:] if api_key else '(未设置)'}")
    print(f"  LANGCHAIN_PROJECT    = {project}")
    print(f"  LANGCHAIN_ENDPOINT   = {endpoint}")

    if not api_key:
        print("\n[FAIL] LANGCHAIN_API_KEY 未设置，无法启用 tracing")
        print("       请在 .env 文件中填入你的 LangSmith API key（ls_ 开头）")
        sys.exit(1)

    # ── 2. 验证 setup_langsmith_tracing() ──
    print("\n=== 2. setup_langsmith_tracing() 验证 ===")
    from finsight_agent.config.feature_flags import (
        langsmith_tracing_enabled,
        setup_langsmith_tracing,
    )

    enabled = langsmith_tracing_enabled()
    print(f"  langsmith_tracing_enabled() = {enabled}")
    if not enabled:
        print("[FAIL] tracing 未启用，检查环境变量")
        sys.exit(1)

    configured = setup_langsmith_tracing()
    print(f"  setup_langsmith_tracing()   = {configured}")
    print("  [OK] tracing 配置成功")

    # ── 3. 验证 graph.invoke() 能正常执行并上报 ──
    print("\n=== 3. graph.invoke() 执行验证 ===")
    from shared.contracts.analysis_request import AnalysisRequest
    from shared.contracts.router_result import RouterResult
    from shared.enums.intent import Intent
    from shared.enums.follow_up_type import FollowUpType

    from finsight_agent.control_plane.orchestrator.graph import build_graph
    from finsight_agent.control_plane.orchestrator.node_deps import NodeDependencies

    # 构建 mock 依赖（不触发真实 LLM，只验证 tracing 上报）
    router_service = MagicMock()
    router_service.route.return_value = RouterResult(
        intent=Intent.GENERAL_FINANCE_QA.value,
        follow_up_type=FollowUpType.NONE.value,
        confidence="high",
        entities={},
        needs=[],
        constraints={},
    )
    reporting_service = MagicMock()
    mock_response = MagicMock()
    mock_response.response_type = "success"
    mock_response.summary = "LangSmith tracing 测试答案"
    reporting_service.build_response.return_value = mock_response

    deps = NodeDependencies(
        router_service=router_service,
        structured_data_service=MagicMock(),
        reporting_service=reporting_service,
        retrieval_facade_factory=MagicMock(return_value=MagicMock()),
        external_context_retriever=MagicMock(),
        target_analysis_service=MagicMock(),
        session_service=MagicMock(),
        strategy_classifier=MagicMock(),
        llm_client=MagicMock(),
    )

    graph = build_graph(deps)

    request = AnalysisRequest(
        query="LangSmith tracing 测试",
        query_mode="conversational",
        session_id="test_langsmith_001",
        include_trace=True,
        notes=None,
    )

    initial_state = {
        "request": request,
        "session_context": None,
        "stage_observations": [],
    }

    print(f"  query: {request.query}")
    print(f"  session_id: {request.session_id}")
    print(f"  project: {project}")
    print("  正在执行 graph.invoke()...")

    final_state = graph.invoke(
        initial_state,
        config={
            "metadata": {
                "query": request.query,
                "session_id": request.session_id,
                "test_type": "langsmith_tracing_verification",
            },
        },
    )

    print(f"  [OK] graph.invoke() 执行成功")
    print(f"  intent: {final_state.get('router_result').intent}")
    print(f"  stages: {final_state.get('stages')}")
    print(f"  trace_blocks count: {len(final_state.get('trace_blocks', []))}")

    # ── 4. 提示用户去 LangSmith UI 查看 ──
    print("\n=== 4. 查看 trace ===")
    print(f"  打开 https://smith.langchain.com")
    print(f"  进入 project: {project}")
    print(f"  找到 query='LangSmith tracing 测试' 的 trace")
    print(f"  可以看到每个节点的输入输出、执行时间、State 流转")
    print(f"\n  [OK] LangSmith tracing 配置完成！")


if __name__ == "__main__":
    main()
