from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class PromptSettings:
    router_system_prompt_path: Path
    planner_system_prompt_path: Path


@dataclass(slots=True)
class ControlPlaneSettings:
    root: Path
    prompts: PromptSettings


@dataclass(slots=True)
class AppSettings:
    control_plane: ControlPlaneSettings


def load_settings() -> AppSettings:
    repo_root = Path(__file__).resolve().parents[4]
    config_path = repo_root / "config" / "app.yaml"
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    root_config = _require_mapping(raw_config, "root")
    app_config = _require_mapping(root_config.get("app"), "app")
    control_plane_config = _require_mapping(app_config.get("control_plane"), "app.control_plane")
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
        )
    )


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _require_text(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _resolve_path(base_path: Path, relative_path: str) -> Path:
    return (base_path / relative_path).resolve()
