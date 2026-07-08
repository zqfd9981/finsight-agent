from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class PromptSettings:
    """Control-plane prompt file path configuration."""

    router_system_prompt_path: Path
    planner_system_prompt_path: Path


@dataclass(slots=True)
class ReportingPromptSettings:
    """Reporting prompt file path configuration."""

    final_answer_writer_system_prompt_path: Path


@dataclass(slots=True)
class ControlPlaneSettings:
    """Control-plane related settings."""

    root: Path
    prompts: PromptSettings


@dataclass(slots=True)
class ReportingSettings:
    """Reporting related settings."""

    root: Path
    prompts: ReportingPromptSettings


@dataclass(slots=True)
class DenseSettings:
    """Dense retrieval local vector-search settings."""

    qdrant_collection_name: str
    embedding_model_name: str
    embedding_model_version: str
    qdrant_path: Path


@dataclass(slots=True)
class RetrievalSettings:
    """Local PDF corpus and retrieval settings."""

    manifest_path: Path
    raw_filings_root: Path
    parsed_filings_root: Path
    chunked_filings_root: Path
    retrieval_index_root: Path
    status_root: Path
    dense: DenseSettings
    default_pilot_company_count: int = 10
    primary_parser_name: str = "mineru"
    parent_target_chars: int = 2000
    child_target_chars: int = 500


@dataclass(slots=True)
class AppSettings:
    """Top-level application settings object."""

    control_plane: ControlPlaneSettings
    reporting: ReportingSettings
    retrieval: RetrievalSettings


def load_settings() -> AppSettings:
    """Read application settings from the repository-level app.yaml."""

    repo_root = Path(__file__).resolve().parents[4]
    config_path = repo_root / "config" / "app.yaml"
    raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    root_config = _require_mapping(raw_config, "root")
    app_config = _require_mapping(root_config.get("app"), "app")
    control_plane_config = _require_mapping(app_config.get("control_plane"), "app.control_plane")
    reporting_config = _require_mapping(app_config.get("reporting"), "app.reporting")
    retrieval_config = _require_mapping(app_config.get("retrieval"), "app.retrieval")
    dense_config = _require_mapping(retrieval_config.get("dense"), "app.retrieval.dense")

    control_plane_root = _resolve_path(repo_root, _require_text(control_plane_config, "root"))
    control_plane_prompts = _require_mapping(
        control_plane_config.get("prompts"),
        "app.control_plane.prompts",
    )
    reporting_root = _resolve_path(repo_root, _require_text(reporting_config, "root"))
    reporting_prompts = _require_mapping(
        reporting_config.get("prompts"),
        "app.reporting.prompts",
    )

    return AppSettings(
        control_plane=ControlPlaneSettings(
            root=control_plane_root,
            prompts=PromptSettings(
                router_system_prompt_path=_resolve_path(
                    control_plane_root,
                    _require_text(control_plane_prompts, "router_system_prompt_path"),
                ),
                planner_system_prompt_path=_resolve_path(
                    control_plane_root,
                    _require_text(control_plane_prompts, "planner_system_prompt_path"),
                ),
            ),
        ),
        reporting=ReportingSettings(
            root=reporting_root,
            prompts=ReportingPromptSettings(
                final_answer_writer_system_prompt_path=_resolve_path(
                    reporting_root,
                    _require_text(
                        reporting_prompts,
                        "final_answer_writer_system_prompt_path",
                    ),
                ),
            ),
        ),
        retrieval=RetrievalSettings(
            manifest_path=_resolve_path(repo_root, _require_text(retrieval_config, "manifest_path")),
            raw_filings_root=_resolve_path(repo_root, _require_text(retrieval_config, "raw_filings_root")),
            parsed_filings_root=_resolve_path(repo_root, _require_text(retrieval_config, "parsed_filings_root")),
            chunked_filings_root=_resolve_path(repo_root, _require_text(retrieval_config, "chunked_filings_root")),
            retrieval_index_root=_resolve_path(
                repo_root,
                _require_text(retrieval_config, "retrieval_index_root"),
            ),
            status_root=_resolve_path(repo_root, _require_text(retrieval_config, "status_root")),
            dense=DenseSettings(
                qdrant_collection_name=_require_text(dense_config, "qdrant_collection_name"),
                embedding_model_name=_require_text(dense_config, "embedding_model_name"),
                embedding_model_version=_require_text(dense_config, "embedding_model_version"),
                qdrant_path=_resolve_path(repo_root, _require_text(dense_config, "qdrant_path")),
            ),
            default_pilot_company_count=_require_int(
                retrieval_config,
                "default_pilot_company_count",
            ),
            primary_parser_name=_require_text(retrieval_config, "primary_parser_name"),
            parent_target_chars=_require_int(retrieval_config, "parent_target_chars"),
            child_target_chars=_require_int(retrieval_config, "child_target_chars"),
        ),
    )


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    """Ensure a config node is an object."""

    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _require_text(mapping: dict[str, Any], key: str) -> str:
    """Ensure a config value is a non-empty string."""

    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _require_int(mapping: dict[str, Any], key: str) -> int:
    """Ensure a config value is an integer."""

    value = mapping.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _resolve_path(base_path: Path, relative_path: str) -> Path:
    """Resolve a relative path from config into an absolute path."""

    return (base_path / relative_path).resolve()
