from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class PromptSettings:
    """控制面 prompt 文件路径配置。"""

    router_system_prompt_path: Path
    planner_system_prompt_path: Path


@dataclass(slots=True)
class ControlPlaneSettings:
    """控制面相关配置。"""

    root: Path
    prompts: PromptSettings


@dataclass(slots=True)
class RetrievalSettings:
    """本地 PDF 语料采集相关配置。"""

    manifest_path: Path
    raw_filings_root: Path
    status_root: Path
    default_pilot_company_count: int = 10


@dataclass(slots=True)
class AppSettings:
    """应用顶层配置对象。"""

    control_plane: ControlPlaneSettings
    retrieval: RetrievalSettings


def load_settings() -> AppSettings:
    """从仓库级 app.yaml 读取并解析当前应用配置。"""

    repo_root = Path(__file__).resolve().parents[4]
    config_path = repo_root / "config" / "app.yaml"
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    root_config = _require_mapping(raw_config, "root")
    app_config = _require_mapping(root_config.get("app"), "app")
    control_plane_config = _require_mapping(app_config.get("control_plane"), "app.control_plane")
    retrieval_config = _require_mapping(app_config.get("retrieval"), "app.retrieval")
    control_plane_root = _resolve_path(
        repo_root, _require_text(control_plane_config, "root")
    )
    prompts_config = _require_mapping(control_plane_config.get("prompts"), "app.control_plane.prompts")

    return AppSettings(
        control_plane=ControlPlaneSettings(
            root=control_plane_root,
            prompts=PromptSettings(
                router_system_prompt_path=_resolve_path(
                    control_plane_root,
                    _require_text(prompts_config, "router_system_prompt_path"),
                ),
                planner_system_prompt_path=_resolve_path(
                    control_plane_root,
                    _require_text(prompts_config, "planner_system_prompt_path"),
                ),
            ),
        ),
        retrieval=RetrievalSettings(
            manifest_path=_resolve_path(
                repo_root,
                _require_text(retrieval_config, "manifest_path"),
            ),
            raw_filings_root=_resolve_path(
                repo_root,
                _require_text(retrieval_config, "raw_filings_root"),
            ),
            status_root=_resolve_path(
                repo_root,
                _require_text(retrieval_config, "status_root"),
            ),
            default_pilot_company_count=_require_int(
                retrieval_config,
                "default_pilot_company_count",
            ),
        ),
    )


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    """确保指定配置节点是对象结构。"""

    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _require_text(mapping: dict[str, Any], key: str) -> str:
    """确保配置项是非空字符串。"""

    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _require_int(mapping: dict[str, Any], key: str) -> int:
    """确保配置项是整数。"""

    value = mapping.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _resolve_path(base_path: Path, relative_path: str) -> Path:
    """把配置中的相对路径统一解析成绝对路径。"""

    return (base_path / relative_path).resolve()
