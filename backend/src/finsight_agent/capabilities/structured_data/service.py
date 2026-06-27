from __future__ import annotations

from shared.contracts.final_response import FinalResponse
from shared.enums.response_type import ResponseType


class StructuredDataService:
    """metric_lookup 快路径使用的结构化数据能力骨架。"""

    def query_metric_lookup(self, company: str, metric: str, time_scope: str) -> dict[str, str]:
        """返回结构化查询的占位结果，暂不接真实数据源。"""
        return {
            "company": company,
            "metric": metric,
            "time_scope": time_scope,
            "value": "TODO",
        }

    def to_brief_response(self, session_id: str, summary: str) -> FinalResponse:
        """将查询结果包装成简短响应占位对象。"""
        return FinalResponse(
            response_type=ResponseType.SUCCESS.value,
            session_id=session_id,
            summary=summary,
        )
