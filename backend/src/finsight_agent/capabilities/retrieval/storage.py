from __future__ import annotations

import json
from pathlib import Path

from .acquisition_models import FilingRecord


# 采集目录和 RAG 设计稿里的文档类型目录保持一致。
DOC_TYPE_DIRS = {
    "annual_report": "annual",
    "semiannual_report": "semiannual",
    "major_announcement": "announcements",
}


def build_output_path(
    root: Path,
    record: FilingRecord,
    normalized_doc_type: str,
    report_year: int | None,
) -> Path:
    """根据公司、文档类型和年份生成标准输出路径。"""

    company_dir = f"{record.company_code}_{record.company_name}"
    # 没有显式 report_year 时，退回到披露日期年份，避免路径缺层级。
    year_dir = str(report_year or record.publish_date[:4])
    filename = (
        f"{record.company_code}_{record.company_name}_"
        f"{normalized_doc_type}_{year_dir}_{record.publish_date.replace('-', '')}.pdf"
    )
    return root / company_dir / DOC_TYPE_DIRS[normalized_doc_type] / year_dir / filename


def write_status_snapshot(
    status_root: Path,
    snapshot_name: str,
    payload: dict[str, object],
) -> Path:
    """把当前批次采集结果写成状态快照，便于后面做覆盖率检查。"""

    status_root.mkdir(parents=True, exist_ok=True)
    output_path = status_root / f"{snapshot_name}.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
