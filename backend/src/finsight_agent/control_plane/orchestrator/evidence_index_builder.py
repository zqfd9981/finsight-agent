from __future__ import annotations

from typing import Any

from shared.contracts.evidence_detail import (
    SOURCE_TYPE_ANNUAL_REPORT,
    SOURCE_TYPE_NEWS,
    SOURCE_TYPE_STRUCTURED_METRIC,
)

# stage_name 取值（与 StageName 枚举 value 及前端 STAGE_LABELS 对齐）
_STAGE_RETRIEVE_EVIDENCE = "retrieve_evidence"
_STAGE_COLLECT_EVENT_CONTEXT = "collect_event_context"
_STAGE_QUERY_STRUCTURED_DATA = "query_structured_data"


def _get(obj: Any, key: str) -> Any:
    """兼容 dataclass 与 dict 的字段读取。"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _empty_detail(evidence_id: str, source_type: str) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "source_type": source_type,
        "company_name": "",
        "company_code": "",
        "doc_type": "",
        "report_year": "",
        "section_path": [],
        "pages": "",
        "excerpt": "",
        "support_strength": "",
        "url": "",
        "title": "",
        "publish_date": "",
        "source": "",
        "metric": "",
        "value": "",
        "unit": "",
        "period": "",
        "matched_by": "",
    }


def _pages_from_citation(citation: Any) -> str:
    if citation is None:
        return ""
    ps = _get(citation, "page_start")
    pe = _get(citation, "page_end")
    if ps is None and pe is None:
        return ""
    ps_s = _as_str(ps)
    pe_s = _as_str(pe)
    if ps_s and pe_s and pe_s != ps_s:
        return f"{ps_s}-{pe_s}"
    return ps_s or pe_s


def _from_rag_item(item: Any) -> dict[str, Any] | None:
    """年报 / 公告 RAG 检索命中（EvidenceItem）。"""
    evidence_id = _get(item, "evidence_id")
    if not evidence_id:
        return None
    detail = _empty_detail(_as_str(evidence_id), SOURCE_TYPE_ANNUAL_REPORT)
    detail.update(
        {
            "company_name": _as_str(_get(item, "company_name")),
            "company_code": _as_str(_get(item, "company_code")),
            "doc_type": _as_str(_get(item, "doc_type")),
            "report_year": _as_str(_get(item, "report_year")),
            "section_path": _as_list(_get(item, "section_path")),
            "pages": _pages_from_citation(_get(item, "citation")),
            "excerpt": _as_str(_get(item, "excerpt")),
            "support_strength": _as_str(_get(item, "support_strength")),
            "source": "retrieval",
        }
    )
    return detail


def _from_event_item(item: Any) -> dict[str, Any] | None:
    """事件新闻（Bocha ExternalContextItem）。"""
    evidence_id = _get(item, "evidence_ref")
    if not evidence_id:
        return None
    detail = _empty_detail(_as_str(evidence_id), SOURCE_TYPE_NEWS)
    detail.update(
        {
            "doc_type": "事件新闻",
            "excerpt": _as_str(_get(item, "snippet")),
            "url": _as_str(_get(item, "url")),
            "title": _as_str(_get(item, "title")),
            "publish_date": _as_str(_get(item, "publish_date")),
            "source": _as_str(_get(item, "source")) or "bocha",
        }
    )
    return detail


def _from_structured(sr: dict[str, Any]) -> dict[str, Any] | None:
    """年报结构化指标结果（structured_result）。"""
    company = _as_str(_get(sr, "company") or _get(sr, "company_name"))
    metric = _as_str(_get(sr, "metric") or _get(sr, "metric_name"))
    if not company and not metric:
        return None
    value = _as_str(_get(sr, "value"))
    unit = _as_str(_get(sr, "unit"))
    period = _as_str(
        _get(sr, "time_scope") or _get(sr, "period") or _get(sr, "period_end")
    )
    evidence_id = f"structured::{company}::{metric}::{period}"
    detail = _empty_detail(evidence_id, SOURCE_TYPE_STRUCTURED_METRIC)
    detail.update(
        {
            "company_name": company,
            "company_code": _as_str(_get(sr, "company_code")),
            "doc_type": "年报结构化数据",
            "report_year": period[:4] if period else "",
            "excerpt": f"{metric}: {value} {unit}".strip(),
            "metric": metric,
            "value": value,
            "unit": unit,
            "period": period,
            "matched_by": _as_str(_get(sr, "matched_by")),
            "source": "structured_data",
        }
    )
    return detail


def build_evidence_index(orchestration_result: Any) -> dict[str, dict[str, Any]]:
    """从编排结果聚合统一证据注册表（evidence_id -> EvidenceDetail）。

    同时覆盖 LangGraph 路径与旧 execute 路径：两条路径的 stage_observations
    均由 build_stage_observation 生成（key_outputs = stage_result.output_payload），
    因此 retrieve_evidence 的 retrieval_result、collect_event_context 的 event_context.items、
    query_structured_data 的 structured_result 都能在此取到。
    """
    index: dict[str, dict[str, Any]] = {}
    if orchestration_result is None:
        return index
    observations = _get(orchestration_result, "stage_observations") or []
    for obs in observations:
        stage_name = _as_str(_get(obs, "stage_name"))
        key_outputs = _get(obs, "key_outputs") or {}

        if stage_name == _STAGE_RETRIEVE_EVIDENCE:
            retrieval_result = key_outputs.get("retrieval_result")
            if retrieval_result is None:
                continue
            items = _get(retrieval_result, "evidence_items") or []
            for it in items:
                detail = _from_rag_item(it)
                if detail:
                    index[detail["evidence_id"]] = detail

        elif stage_name == _STAGE_COLLECT_EVENT_CONTEXT:
            event_context = key_outputs.get("event_context") or {}
            items = event_context.get("items") or []
            for it in items:
                detail = _from_event_item(it)
                if detail:
                    index[detail["evidence_id"]] = detail

        elif stage_name == _STAGE_QUERY_STRUCTURED_DATA:
            structured_result = key_outputs.get("structured_result") or {}
            if not isinstance(structured_result, dict):
                structured_result = {}
            detail = _from_structured(structured_result)
            if detail:
                index[detail["evidence_id"]] = detail

    return index
