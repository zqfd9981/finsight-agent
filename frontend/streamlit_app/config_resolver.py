"""读取 ``config/app.yaml`` 中工作台启动相关的配置。

设计要点：
- 解析是**懒**的：仅在调用方主动 ``resolve_workbench_config()`` 时读文件；
  模块 import 期不读，避免破坏"无需配置即可 smoke import"的测试模式。
- 缺值回落到本机开发默认值，让启动操作不被配置细节阻塞。
- 上下游合同：所有读出的 host/port 都是 ``str`` / ``int``，调用方无须做类型转换。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_BACKEND_HOST: str = "127.0.0.1"
DEFAULT_BACKEND_PORT: int = 8000
DEFAULT_BACKEND_BASE_URL: str = f"http://{DEFAULT_BACKEND_HOST}:{DEFAULT_BACKEND_PORT}"
DEFAULT_FRONTEND_HOST: str = "127.0.0.1"
DEFAULT_FRONTEND_PORT: int = 8501

DEFAULT_CONFIG_PATH: Path = Path("config") / "app.yaml"


def load_app_config(config_path: Path | None = None) -> dict[str, Any]:
    """加载 ``config/app.yaml`` 并返回 dict。文件不存在 / 解析失败时回落到空 dict。"""

    candidate = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    if not candidate.is_file():
        return {}
    try:
        payload = yaml.safe_load(candidate.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    return payload or {}


def resolve_workbench_config(config_path: Path | None = None) -> dict[str, Any]:
    """从 app config 中提取 ``app.workbench`` 段，并补齐本地默认回退。

    Returns
    -------
    dict
        包含 ``backend_host`` / ``backend_port`` / ``backend_base_url`` /
        ``frontend_host`` / ``frontend_port`` 五项键。
    """

    cfg = load_app_config(config_path)
    section = (cfg.get("app") or {}).get("workbench") or {}

    backend_host = str(section.get("backend_host", DEFAULT_BACKEND_HOST))
    backend_port = int(section.get("backend_port", DEFAULT_BACKEND_PORT))
    backend_base_url = str(
        section.get("backend_base_url") or f"http://{backend_host}:{backend_port}"
    )
    frontend_host = str(section.get("frontend_host", DEFAULT_FRONTEND_HOST))
    frontend_port = int(section.get("frontend_port", DEFAULT_FRONTEND_PORT))

    return {
        "backend_host": backend_host,
        "backend_port": backend_port,
        "backend_base_url": backend_base_url,
        "frontend_host": frontend_host,
        "frontend_port": frontend_port,
    }
