"""导出 LangGraph 图可视化。

用法：
    python scripts/export_langgraph_graph.py

输出：
    var/langgraph_graph.png  （需要 pygraphviz 或 grandalf）
    var/langgraph_graph.mmd  （Mermaid 文本，无需额外依赖）
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_SRC_ROOT))

from unittest.mock import MagicMock  # noqa: E402

from finsight_agent.control_plane.orchestrator.graph import build_graph  # noqa: E402
from finsight_agent.control_plane.orchestrator.node_deps import NodeDependencies  # noqa: E402


def _build_mock_deps() -> NodeDependencies:
    """全 mock 依赖，只为构建图拓扑，不触发真实初始化。"""
    return NodeDependencies(
        router_service=MagicMock(),
        structured_data_service=MagicMock(),
        reporting_service=MagicMock(),
        retrieval_facade_factory=MagicMock(return_value=MagicMock()),
        external_context_retriever=MagicMock(),
        target_analysis_service=MagicMock(),
        session_service=MagicMock(),
        strategy_classifier=MagicMock(),
        llm_client=MagicMock(),
    )


def main() -> None:
    out_dir = REPO_ROOT / "var"
    out_dir.mkdir(exist_ok=True)

    deps = _build_mock_deps()
    graph = build_graph(deps)

    # ── 1. Mermaid 文本（始终可用）──
    mermaid_str = graph.get_graph().draw_mermaid()
    mmd_path = out_dir / "langgraph_graph.mmd"
    mmd_path.write_text(mermaid_str, encoding="utf-8")
    print(f"[OK] Mermaid 图已导出: {mmd_path}")

    # ── 2. PNG（需要 pygraphviz 或 grandalf）──
    png_path = out_dir / "langgraph_graph.png"
    try:
        graph.get_graph().draw_png(str(png_path))
        print(f"[OK] PNG 图已导出: {png_path}")
    except ImportError as exc:
        print(f"[SKIP] PNG 导出需要额外依赖: {exc}")
        print("       可选安装: pip install grandalf  (纯 Python, 无需 Graphviz)")
        print("       或安装: pip install pygraphviz  (需要 Graphviz 系统二进制)")
    except Exception as exc:
        print(f"[SKIP] PNG 导出失败: {exc}")

    # ── 3. 打印 ASCII 拓扑 ──
    print("\n图拓扑（ASCII）:")
    print("-" * 60)
    graph_obj = graph.get_graph()
    print(f"节点数: {len(graph_obj.nodes)}")
    for node_id, node in graph_obj.nodes.items():
        print(f"  - {node_id}")
    print(f"\n边数: {len(graph_obj.edges)}")
    for edge in graph_obj.edges:
        src = edge.source if hasattr(edge, "source") else str(edge)
        print(f"  - {src}")

    print("\nMermaid 内容预览:")
    print("-" * 60)
    print(mermaid_str)


if __name__ == "__main__":
    main()
