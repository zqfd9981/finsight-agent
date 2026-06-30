from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.corpus_manifest import load_sample_universe
from finsight_agent.capabilities.retrieval.service import (
    build_pdf_corpus_acquisition_service,
)
from finsight_agent.config.settings import load_settings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析试点下载脚本参数。"""

    parser = argparse.ArgumentParser(description="下载本地 PDF 语料试点样本")
    parser.add_argument(
        "--pilot-company-count",
        type=int,
        default=None,
        help="试点公司数量，默认使用 app.yaml 中的配置值",
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="披露起始日期，格式为 YYYY-MM-DD",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="披露结束日期，格式为 YYYY-MM-DD",
    )
    parser.add_argument(
        "--company-code",
        action="append",
        dest="company_codes",
        default=None,
        help="可重复传入，用于只下载指定公司",
    )
    return parser.parse_args(argv)


def run_pilot_download(argv: list[str] | None = None) -> int:
    """执行试点下载，并把结果以 JSON 打到标准输出。"""

    args = parse_args(argv)
    settings = load_settings()
    sample_universe = load_sample_universe(settings.retrieval.manifest_path)
    service = build_pdf_corpus_acquisition_service()

    result = service.download_pilot_filings(
        sample_universe=sample_universe,
        pilot_company_count=(
            args.pilot_company_count
            or settings.retrieval.default_pilot_company_count
        ),
        start_date=args.start_date,
        end_date=args.end_date,
        company_codes=args.company_codes,
    )
    print(
        json.dumps(
            {
                "downloaded_count": result.downloaded_count,
                "failed_count": result.failed_count,
                "status_snapshot_path": str(result.status_snapshot_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run_pilot_download())
