"""跨平台工作台后端启动器。

用法：
    python scripts/run_workbench_backend.py
    python scripts/run_workbench_backend.py --reload

读 ``config/app.yaml`` 的 ``app.workbench.backend_host`` / ``backend_port``，
并把 ``backend.apps.api.main:app`` 喂给 ``uvicorn.run``。

环境变量从仓库根目录的 ``.env`` 文件自动加载（LangSmith tracing、LLM API key 等）。
"""

from __future__ import annotations

import os

# 必须在任何可能 import torch / sentence_transformers 的库之前设置，
# 否则 OpenMP 运行时冲突（libiomp5md.dll 与 vcomp140.dll 同进程初始化）
# 会在首次 bge-m3 encode 时随机 SIGSEGV，导致后端进程崩溃。
# bge_m3.py 内也设了同样的变量，但入口处更早、更稳妥。
# 用强制赋值（非 setdefault）：若环境已存在 falsy 值，setdefault 不会覆盖，
# 会导致 OpenMP 冲突未被消除、bge-m3 加载时偶发 SIGSEGV——这正是此前
# "探测脚本正常、实况服务崩溃" 的根因（探测环境该变量为空，setdefault 生效；
# 实况环境可能继承了某个 falsy 值，setdefault 静默失效）。
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import argparse
import sys
from pathlib import Path

# 崩溃时打印 Python 栈，便于定位原生段错误（如 torch/OpenMP）。
import faulthandler

faulthandler.enable()


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

# 让 ``frontend.streamlit_app.config_resolver`` 与 ``backend.apps.api.*`` 都能 import。
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_SRC_ROOT))


def _load_dotenv() -> None:
    """从 .env 文件加载环境变量（LangSmith、AGICTO API key 等）。

    优先尝试 python-dotenv（若已安装），否则用简易解析器兜底。
    不覆盖已存在的环境变量。
    """
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
        return
    except ImportError:
        pass
    # 简易解析器兜底
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in __import__("os").environ:
            __import__("os").environ[key] = value


_load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(description="FinSight V1 workbench backend launcher.")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="开发期热重载（修改服务端代码自动重启）",
    )
    args = parser.parse_args()

    # 必须在 ``import uvicorn`` 之前把 repo + backend/src 加进 sys.path；
    # config_resolver 依赖 ``import yaml`` 与 ``config/app.yaml`` 路径。
    import uvicorn  # noqa: E402
    from frontend.streamlit_app.config_resolver import (  # noqa: E402
        resolve_workbench_config,
    )

    cfg = resolve_workbench_config()

    # 启动期预热检索 facade（含 bge-m3 / torch 模型加载）。
    # 必须在 uvicorn.run 之前、单线程主线程上下文中完成：torch 的 OpenMP 运行时
    # 初始化若发生在 uvicorn 事件循环/工作线程已启动之后，会间歇性触发原生
    # SIGSEGV（access violation @ torch._C import）。提前在干净的单线程环境完成
    # 加载，后续 lifespan 内的 get_shared_retrieval_facade() 直接命中进程级缓存，
    # 不再触碰 torch 导入，从根本上消除初始化竞态。
    # （仅当启用真实 dense 模型时预热；否则走 384 维哈希回退，无重模型加载。）
    if os.environ.get("DENSE_USE_REAL_MODEL", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        try:
            from finsight_agent.capabilities.retrieval.service import (
                get_shared_retrieval_facade,
            )

            get_shared_retrieval_facade()
            print("[startup] 检索 facade 预热完成（bge-m3 模型已加载）")
        except Exception as exc:  # noqa: BLE001
            # Python 层异常（如模型文件缺失）可在此捕获记录；原生 SIGSEGV 无法被
            # Python 捕获，会直接终止进程——此时配合 faulthandler 可定位到崩溃点。
            print(f"[startup] 警告：检索 facade 预热失败：{exc}")

    uvicorn.run(
        "backend.apps.api.main:app",
        host=cfg["backend_host"],
        port=int(cfg["backend_port"]),
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
