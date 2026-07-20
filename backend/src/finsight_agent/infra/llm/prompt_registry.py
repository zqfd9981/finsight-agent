"""集中式 Prompt 注册表（PromptRegistry）。

统一管理所有 LLM prompt 文本，替代分散在各模块的 ``read_text()`` 调用
和写死在代码里的 prompt 字符串。

设计目标：
- **单一入口**：所有 prompt 通过 ``get_prompt("router.system")`` 访问
- **文件驱动**：prompt 文本集中在 ``prompts/`` 目录，支持版本管理与 diff
- **缓存+热重载**：首次加载缓存，``reload()`` 清缓存（开发期热更新）
- **变量插值**：``render()`` 方法支持 ``{var}`` 模板替换
- **向后兼容**：旧路径配置仍可用，Registry 是可选增强

目录结构（``prompts/`` 根目录）::

    prompts/
    ├── router/
    │   └── system.txt              → get_prompt("router.system")
    ├── reporting/
    │   ├── system.txt              → get_prompt("reporting.system")
    │   ├── brief_answer.txt        → get_prompt("reporting.brief_answer")
    │   ├── direct_answer.txt       → get_prompt("reporting.direct_answer")
    │   ├── event_answer.txt        → get_prompt("reporting.event_answer")
    │   └── report_answer.txt       → get_prompt("reporting.report_answer")
    ├── retrieval/
    │   ├── query_rewrite.txt       → get_prompt("retrieval.query_rewrite")
    │   └── reflect.txt             → get_prompt("retrieval.reflect")
    ├── structured_data/
    │   ├── notes_section_decision.txt
    │   └── metric_normalizer.txt   → get_prompt("structured_data.metric_normalizer")
    └── session/
        └── summarizer.txt          → get_prompt("session.summarizer")

用法::

    from finsight_agent.infra.llm.prompt_registry import get_prompt

    system_prompt = get_prompt("router.system")
    rendered = get_prompt("session.summarizer").render(
        existing_summary="...",
        turns_text="...",
    )
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

# 默认 prompts 根目录（相对仓库根）
_DEFAULT_PROMPTS_ROOT = "prompts"


class PromptNotFoundError(FileNotFoundError):
    """请求的 prompt 文件不存在。"""


class PromptEntry:
    """单个 prompt 文本的包装，支持变量插值。"""

    __slots__ = ("name", "text", "path")

    def __init__(self, name: str, text: str, path: Path) -> None:
        self.name = name
        self.text = text
        self.path = path

    def render(self, **variables: Any) -> str:
        """用 ``str.format_map`` 做变量插值。

        未提供的变量会保留原 ``{var}`` 占位符（用 _SafeDict 兜底），
        避免抛 KeyError——某些 prompt 的 ``{{json}}`` 转义也能正常工作。
        """
        return self.text.format_map(_SafeDict(variables))

    def __str__(self) -> str:
        return self.text


class _SafeDict(dict):
    """format_map 兜底：缺失 key 返回 ``{key}`` 原文。"""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class PromptRegistry:
    """Prompt 注册表单例。

    线程安全，首次调用 ``get_prompt`` 时懒加载。
    """

    def __init__(self, root: Path | str | None = None) -> None:
        self._root = Path(root) if root else self._resolve_default_root()
        self._cache: dict[str, PromptEntry] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _resolve_default_root() -> Path:
        """从仓库根找 prompts/ 目录。

        优先用环境变量 ``FINSIGHT_PROMPTS_ROOT``，否则从本文件向上找仓库根。
        """
        import os

        env_root = os.getenv("FINSIGHT_PROMPTS_ROOT")
        if env_root:
            return Path(env_root).resolve()

        # 本文件在 backend/src/finsight_agent/infra/llm/prompt_registry.py
        # 仓库根是 parents[5]
        repo_root = Path(__file__).resolve().parents[5]
        return (repo_root / _DEFAULT_PROMPTS_ROOT).resolve()

    def get(self, name: str) -> PromptEntry:
        """按 dotted name 获取 prompt（如 ``router.system``）。

        Args:
            name: ``namespace.filename``，如 ``router.system`` →
                  ``prompts/router/system.txt``

        Raises:
            PromptNotFoundError: 文件不存在
        """
        if name in self._cache:
            return self._cache[name]

        with self._lock:
            # double-check
            if name in self._cache:
                return self._cache[name]

            entry = self._load(name)
            self._cache[name] = entry
            return entry

    def render(self, name: str, **variables: Any) -> str:
        """便捷方法：获取 prompt 并立即插值。"""
        return self.get(name).render(**variables)

    def reload(self) -> None:
        """清空缓存，下次 ``get`` 重新读盘（开发期热重载）。"""
        with self._lock:
            self._cache.clear()
            _logger.info("PromptRegistry 缓存已清空，下次 get 将重新读盘")

    def list_prompts(self) -> list[str]:
        """列出所有可用 prompt 的 dotted name（扫描目录）。"""
        names: list[str] = []
        if not self._root.exists():
            return names
        for txt_path in sorted(self._root.rglob("*.txt")):
            rel = txt_path.relative_to(self._root)
            # windows 路径分隔符 → dot
            dotted = str(rel.with_suffix("")).replace("\\", ".").replace("/", ".")
            names.append(dotted)
        return names

    def _load(self, name: str) -> PromptEntry:
        """从磁盘加载 prompt 文件。"""
        # dotted name → 相对路径
        rel_parts = name.split(".")
        path = self._root.joinpath(*rel_parts).with_suffix(".txt")

        if not path.exists():
            available = self.list_prompts()
            raise PromptNotFoundError(
                f"prompt '{name}' not found at {path}. "
                f"Available: {available}"
            )

        text = path.read_text(encoding="utf-8")
        return PromptEntry(name=name, text=text, path=path)


# ── 模块级单例 ──

_registry: PromptRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> PromptRegistry:
    """获取全局 PromptRegistry 单例。"""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = PromptRegistry()
    return _registry


def get_prompt(name: str) -> PromptEntry:
    """便捷函数：从全局 Registry 获取 prompt。"""
    return get_registry().get(name)


def render_prompt(name: str, **variables: Any) -> str:
    """便捷函数：获取 prompt 并插值。"""
    return get_registry().render(name, **variables)


def reload_prompts() -> None:
    """便捷函数：清空全局 Registry 缓存。"""
    get_registry().reload()
