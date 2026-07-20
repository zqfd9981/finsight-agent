from __future__ import annotations

import os


def llm_router_enabled() -> bool:
    """控制 router 是否优先走 LLM 结构化判别。"""
    return os.getenv("FINSIGHT_LLM_ROUTER_ENABLED", "1") == "1"


def llm_strategy_enabled() -> bool:
    """控制检索策略分类是否优先走 LLM 判断（默认开启）。

    关闭时回退到 Trained 分类器（再回退 Stub），方便在离线 / LLM 不可用时降级。
    """
    return os.getenv("FINSIGHT_LLM_STRATEGY_ENABLED", "1") == "1"

# ── LangSmith 追踪配置 ──

def langsmith_tracing_enabled() -> bool:
    """是否启用 LangSmith tracing。

    需同时满足：LANGCHAIN_TRACING_V2=true 且 LANGCHAIN_API_KEY 已设置。
    """
    return (
        os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
        and bool(os.getenv("LANGCHAIN_API_KEY", "").strip())
    )


def langsmith_api_key() -> str:
    """LangSmith API key（ls_ 开头）。"""
    return os.getenv("LANGCHAIN_API_KEY", "").strip()


def langsmith_project() -> str:
    """LangSmith 项目名，用于在 UI 中组织追踪记录。"""
    return os.getenv("LANGCHAIN_PROJECT", "finsight-agent").strip()


def langsmith_endpoint() -> str:
    """LangSmith API endpoint。"""
    return os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com").strip()


def setup_langsmith_tracing() -> bool:
    """配置 LangSmith 环境变量，返回是否成功启用。

    LangGraph/LangChain 的 tracing 由环境变量驱动：
    - LANGCHAIN_TRACING_V2=true 开启 tracing
    - LANGCHAIN_API_KEY 认证
    - LANGCHAIN_PROJECT 指定项目名
    - LANGCHAIN_ENDPOINT 指定 API 端点

    设置好环境变量后，LangGraph 的 graph.invoke() / graph.stream() 会自动
    上报每个节点的输入输出、执行时间、异常到 LangSmith UI。
    """
    if not langsmith_tracing_enabled():
        return False
    # 确保所有 LangSmith 环境变量都设置好（从 feature_flags 统一入口）
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_ENDPOINT", langsmith_endpoint())
    os.environ.setdefault("LANGCHAIN_PROJECT", langsmith_project())
    # LANGCHAIN_API_KEY 必须由用户在 .env 里设置，这里不覆盖
    return True
