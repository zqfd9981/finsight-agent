"""单独重建检索索引（sparse + dense）。

用途：parse_filtered_pages 的索引重建步骤因网络问题失败时，单独重跑。
环境变量 HF_HUB_OFFLINE=1 避免 sentence-transformers 去 HuggingFace 检查更新。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# 必须在 import sentence_transformers 之前设置
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.service import build_retrieval_facade
from finsight_agent.config.settings import load_settings


def main() -> int:
    settings = load_settings()
    print("=" * 80)
    print("重建检索索引（sparse + dense）")
    print(f"  HF_HUB_OFFLINE={os.environ.get('HF_HUB_OFFLINE')}")
    print("=" * 80, flush=True)

    index_t0 = time.time()
    facade = build_retrieval_facade()

    print("  sparse (BM25) ...", end=" ", flush=True)
    sparse_t0 = time.time()
    sparse_count = facade.sparse_facade.rebuild_index()
    print(f"OK ({sparse_count} chunks, {time.time() - sparse_t0:.1f}s)")

    print("  dense (Qdrant + bge-m3) ...", end=" ", flush=True)
    dense_t0 = time.time()
    dense_count = facade.dense_facade.rebuild_index()
    print(f"OK ({dense_count} chunks, {time.time() - dense_t0:.1f}s)")

    facade.close()
    print(f"  索引重建完成: sparse={sparse_count}, dense={dense_count}, "
          f"总耗时 {time.time() - index_t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
