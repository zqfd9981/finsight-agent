"""节点依赖容器：图构建时注入的 service 依赖。

节点函数是纯函数，但需要访问 service（RouterService、StructuredDataService 等）。
通过模块级单例 + 闭包注入，避免节点函数签名透传依赖。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from finsight_agent.capabilities.reporting.service import ReportingService
from finsight_agent.capabilities.retrieval.service import RetrievalFacade
from finsight_agent.capabilities.structured_data.service import StructuredDataService
from finsight_agent.control_plane.router.service import RouterService
from finsight_agent.control_plane.session.service import SessionService
from finsight_agent.infra.llm.client import LlmClient

from .context_retriever import ExternalContextRetriever
from .target_analysis import TargetAnalysisService


@dataclass(slots=True)
class NodeDependencies:
    """图构建时注入的 service 依赖，节点函数通过模块级 ``_deps`` 访问。"""

    router_service: RouterService
    structured_data_service: StructuredDataService
    reporting_service: ReportingService
    retrieval_facade_factory: Callable[[], RetrievalFacade]
    external_context_retriever: ExternalContextRetriever
    target_analysis_service: TargetAnalysisService
    session_service: SessionService
    strategy_classifier: Any  # TrainedRetrievalStrategyClassifier | StubRetrievalStrategyClassifier
    llm_client: LlmClient
    # 可选的共享 retrieval_facade（避免每个 stage 重复创建）
    retrieval_facade: RetrievalFacade | None = None


_deps: NodeDependencies | None = None


def configure_dependencies(deps: NodeDependencies) -> None:
    """设置模块级依赖单例。graph 构建时调用一次。"""
    global _deps
    _deps = deps


def get_dependencies() -> NodeDependencies:
    """获取当前依赖单例。节点函数内部调用。"""
    if _deps is None:
        raise RuntimeError(
            "NodeDependencies 未配置：请先调用 configure_dependencies() "
            "（通常在 build_graph() 时完成）"
        )
    return _deps
