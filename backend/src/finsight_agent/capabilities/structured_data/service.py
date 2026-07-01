from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from shared.contracts.final_response import FinalResponse
from shared.enums.response_type import ResponseType

from .models import MetricLookupResult, MetricQuery
from .providers import ExternalMetricProvider, NullExternalMetricProvider
from .repository import MetricRepository


class StructuredDataService:
    """metric_lookup 使用的结构化指标查询能力。"""

    def __init__(
        self,
        *,
        metric_repository: MetricRepository | None = None,
        external_provider: ExternalMetricProvider | None = None,
        storage_dir: str | Path = "runtime/structured_data",
    ) -> None:
        self._repository = metric_repository or MetricRepository(storage_dir=storage_dir)
        self._external_provider = external_provider or NullExternalMetricProvider()

    def query_metric_lookup(
        self,
        company: str,
        metric: str,
        time_scope: str,
    ) -> dict[str, object]:
        """优先查询本地指标库，未命中时先返回显式降级结果。"""

        query = MetricQuery(
            company_name=company,
            metric_name=metric,
            time_scope=time_scope,
        )
        record = self._repository.find_best_match(query)
        if record is not None:
            result = MetricLookupResult(
                company_name=record.company_name,
                metric_name=record.metric_name,
                time_scope=record.time_scope,
                value=record.value,
                unit=record.unit,
                source_type=record.source_type,
                source_summary=f"{record.source_document_id} / {record.source_caption}",
                matched_by="local_repository",
                confidence=record.confidence,
                is_degraded=False,
                notes=[],
            )
            return self._to_stage_payload(result)

        if query.allow_external_fallback:
            external_result = self._external_provider.lookup_metric(
                company_name=company,
                metric_name=metric,
                time_scope=time_scope,
            )
            if external_result is not None:
                external_result = dict(external_result)
                external_result["company"] = str(
                    external_result.get("company_name", company)
                )
                external_result["metric"] = str(
                    external_result.get("metric_name", metric)
                )
                external_result["time_scope"] = str(
                    external_result.get("time_scope", time_scope)
                )
                external_notes = [
                    str(item) for item in external_result.get("notes", [])
                ]
                external_result["notes"] = external_notes + [
                    "结果来自外部指标接口，非本地财报抽取"
                ]
                return external_result

        degraded = MetricLookupResult.degraded(
            company_name=company,
            metric_name=metric,
            time_scope=time_scope,
            notes=["当前未找到对应指标数据"],
        )
        return self._to_stage_payload(degraded)

    def to_brief_response(self, session_id: str, summary: str) -> FinalResponse:
        """将简答摘要包装成统一最终响应。"""

        return FinalResponse(
            response_type=ResponseType.SUCCESS.value,
            session_id=session_id,
            summary=summary,
        )

    def _to_stage_payload(self, result: MetricLookupResult) -> dict[str, object]:
        payload = asdict(result)
        payload["company"] = result.company_name
        payload["metric"] = result.metric_name
        payload["time_scope"] = result.time_scope
        return payload
