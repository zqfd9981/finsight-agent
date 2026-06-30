from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .acquisition_models import SampleCompany


@dataclass(slots=True)
class SampleUniverse:
    """半导体样本股池的内存表示。"""

    theme: str
    segment_targets: dict[str, int]
    companies: list[SampleCompany] = field(default_factory=list)

    def select_companies(
        self,
        limit: int,
        company_codes: list[str] | None = None,
    ) -> list[SampleCompany]:
        """按试点策略返回公司列表。"""

        # 显式传入代码列表时，优先返回指定公司，便于做小范围试点。
        if company_codes:
            code_set = set(company_codes)
            return [
                company for company in self.companies if company.company_code in code_set
            ][:limit]

        # 默认按优先级筛选，但同一优先级内保留 manifest 原顺序，
        # 这样样本池文件里的排列就能直接表达“试点先后顺序”。
        priority_rank = {"high": 0, "medium": 1, "low": 2}
        indexed_companies = list(enumerate(self.companies))
        ranked_companies = sorted(
            indexed_companies,
            key=lambda item: (
                priority_rank.get(item[1].priority, 9),
                item[0],
            ),
        )
        return [company for _, company in ranked_companies[:limit]]


def load_sample_universe(manifest_path: Path) -> SampleUniverse:
    """从 YAML manifest 读取样本股池。"""

    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    companies = [
        SampleCompany(
            company_code=str(item["company_code"]),
            company_name=str(item["company_name"]),
            segment=str(item["segment"]),
            subsegment=str(item.get("subsegment", "")),
            priority=str(item.get("priority", "medium")),
            theme_tags=list(item.get("theme_tags", [])),
            notes=item.get("notes"),
        )
        for item in payload["companies"]
    ]
    return SampleUniverse(
        theme=str(payload["theme"]),
        segment_targets={
            str(key): int(value) for key, value in payload["segment_targets"].items()
        },
        companies=companies,
    )
