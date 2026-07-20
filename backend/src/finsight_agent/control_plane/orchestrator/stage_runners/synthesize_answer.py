from __future__ import annotations

"""统一的 synthesize_answer stage：按 response_mode 切换 context 组装逻辑。

替代原 synthesize_brief_answer / synthesize_event_answer / synthesize_report 三个 stage。
response_mode 由 stage_planner.resolve_stages 写入 stage_constraints，本 stage 读取后分发：
  - direct       → 泛财经 LLM 直答，只用 query + router entities
  - brief_answer → 指标类简短答复，读 query_structured_data 结果
  - event_answer → 事件类答复，读 collect_event_context 结果
  - report       → 证据型报告，读 retrieve_evidence + analyze_targets + collect_event_context
"""

from finsight_agent.capabilities.reporting.service import ReportingService
from finsight_agent.capabilities.retrieval.models import RetrievalResult
from finsight_agent.capabilities.structured_data.unit_normalizer import (
    format_display_value,
    normalize_to_base_unit,
)
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.report_block import EvidenceOverviewBlock, EvidenceOverviewItem
from shared.contracts.router_result import RouterResult
from shared.enums.response_mode import ResponseMode
from shared.enums.stage_name import StageName

from ..models import StageExecutionResult


def run_synthesize_answer_stage(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object] | None,
    execution_state: dict[str, StageExecutionResult],
    reporting_service: ReportingService,
) -> StageExecutionResult:
    constraints = dict(stage_constraints or {})
    response_mode = str(
        constraints.get("response_mode") or ResponseMode.BRIEF_ANSWER.value
    )

    if response_mode == ResponseMode.DIRECT.value:
        return _synthesize_direct(request, router_result, reporting_service)
    if response_mode == ResponseMode.BRIEF_ANSWER.value:
        return _synthesize_brief(request, router_result, execution_state, reporting_service)
    if response_mode == ResponseMode.EVENT_ANSWER.value:
        return _synthesize_event(request, router_result, execution_state, reporting_service)
    return _synthesize_report(request, router_result, execution_state, reporting_service)


def _synthesize_direct(
    request: AnalysisRequest,
    router_result: RouterResult,
    reporting_service: ReportingService,
) -> StageExecutionResult:
    """泛财经轻路径：LLM 直答，不读 execution_state。"""
    summary = request.query.strip() or "泛财经问题直接答复。"
    final_response = reporting_service.build_response(
        response_mode=ResponseMode.DIRECT.value,
        session_id=request.session_id or "",
        summary=summary,
        final_answer_context={
            "query": request.query,
            "intent": router_result.intent,
            "topics": router_result.entities.get("topics", []),
            "is_direct": True,
        },
    )
    return StageExecutionResult(
        stage_name=StageName.SYNTHESIZE_ANSWER.value,
        status="success",
        output_payload={"final_response": final_response},
        user_summary=summary,
    )


def _synthesize_brief(
    request: AnalysisRequest,
    router_result: RouterResult,
    execution_state: dict[str, StageExecutionResult],
    reporting_service: ReportingService,
) -> StageExecutionResult:
    """指标类简短答复，读 query_structured_data 结果。"""
    stage_result = execution_state[StageName.QUERY_STRUCTURED_DATA.value]
    structured_result = dict(stage_result.output_payload.get("structured_result", {}))

    company = str(structured_result.get("company", "")).strip()
    metric = str(structured_result.get("metric", "")).strip()
    time_scope = _clean_time_scope(str(structured_result.get("time_scope", "")).strip())
    value = str(structured_result.get("value", "")).strip()
    unit = str(structured_result.get("unit", "")).strip()
    is_degraded = bool(structured_result.get("is_degraded", False))
    notes = [
        str(item).strip()
        for item in structured_result.get("notes", [])
        if str(item).strip()
    ]

    # 指标名优先用用户原文（中文，如"归母净利润"），而非 DB 的英文 key（如
    # net_profit_attributable_to_parent），避免 summary 暴露内部字段。
    # router entities 新格式：metric 可能是 dict（单指标）或 list（多指标拆分后）
    metric_entity = router_result.entities.get("metric", "")
    if isinstance(metric_entity, dict):
        metric_display = str(metric_entity.get("raw") or "").strip()
    elif isinstance(metric_entity, list):
        # 多指标：拼接所有 raw，用顿号分隔（如"净利润、营业收入"）
        raws = [str(m.get("raw") or "").strip() for m in metric_entity if isinstance(m, dict)]
        metric_display = "、".join(r for r in raws if r)
    else:
        metric_display = str(metric_entity or "").strip()
    # fallback：router 没给 raw 时用 structured_result 的 metric（可能是英文 key）
    if not metric_display:
        metric_display = metric

    # 反思补查结果（reflect_and_requery 节点产出）：降级时若补查到原料指标，
    # 交给 brief prompt 基于原料计算（如 毛利率 = (营收-营业成本)/营收）。
    ingredient_results = _read_reflect_ingredients(execution_state)
    # 仅统计真正取到数值、未二次降级的原料，用于判定 summary 是否应标注"已推导恢复"。
    # 若原料本身也降级或无数值，则不视为成功恢复，summary 仍如实标注"未命中"。
    usable_ingredients = [
        item
        for item in ingredient_results
        if str(item.get("value", "")).strip() and not item.get("is_degraded", False)
    ]

    if is_degraded:
        if usable_ingredients:
            # 降级但反思补查到了可用的原料指标：诚实标注"已基于原料推导恢复"，
            # 避免 summary（聊天气泡 / session response_summary 记忆）误写"未命中"
            # 而污染下一轮路由与多轮对话记忆。具体推导数值由 brief writer 在
            # answer_markdown 中给出，此处只给结论性摘要，不重复/编造数字。
            summary = (
                f"{company}{time_scope}{metric_display}暂无直接数据，"
                f"已基于 {len(usable_ingredients)} 个原料指标推导得出（详见回答）。"
            )
        else:
            note_text = "；".join(notes) if notes else "当前未找到对应指标数据。"
            summary = f"{company}{time_scope}{metric_display}暂未命中结构化数据。{note_text}"
    elif structured_result.get("computed"):
        # 路径② 计算结果（聚合/增长/连续增长/排名），非行形状
        summary = _format_computed_result(structured_result)
    else:
        records = structured_result.get("records", [])
        if structured_result.get("is_multi") and isinstance(records, list) and len(records) > 1:
            # 多行结果（多指标/多公司/多年/TopN）走聚合展示
            summary = _aggregate_multi_records(records)
        elif unit == "%" and value.endswith("%"):
            # value 已含 % 号（比率类衍生指标）时不再拼接 unit，避免 "91.63%%"
            summary = f"{company}{time_scope}{metric_display}为 {value}。"
        else:
            # 展示层单位换算：千元/万元 → 亿元（更友好）；每股类指标强制"元/股"
            display_value, display_unit = format_display_value(value, unit, metric_name=metric)
            summary = f"{company}{time_scope}{metric_display}为 {display_value}{display_unit}。"

    # 构造传给 LLM 的 structured_result：把 records 列表中的 value/unit 换算成展示值，
    # 让 LLM 生成的 answer_markdown 与 summary 单位一致（都展示亿元/万元）。
    # 原始 value/unit 保留在 raw_value/raw_unit 字段供溯源。
    llm_structured_result = _build_llm_structured_result(structured_result)

    final_response = reporting_service.build_response(
        response_mode=ResponseMode.BRIEF_ANSWER.value,
        session_id=request.session_id or "",
        summary=summary,
        final_answer_context={
            "query": request.query,
            "intent": router_result.intent,
            "strategy": "structured_data",
            "structured_result": llm_structured_result,
            "is_degraded": is_degraded,
            "notes": notes,
            "ingredient_results": ingredient_results,
        },
    )
    return StageExecutionResult(
        stage_name=StageName.SYNTHESIZE_ANSWER.value,
        status="success",
        output_payload={"final_response": final_response},
        user_summary=summary,
    )


def _synthesize_event(
    request: AnalysisRequest,
    router_result: RouterResult,
    execution_state: dict[str, StageExecutionResult],
    reporting_service: ReportingService,
) -> StageExecutionResult:
    """事件类答复，读 collect_event_context 结果。"""
    collect_result = execution_state[StageName.COLLECT_EVENT_CONTEXT.value]
    collect_payload = dict(collect_result.output_payload)
    event_context = dict(collect_payload.get("event_context", {}) or {})
    source_status = dict(collect_payload.get("source_status", {}) or {})
    strategy = str(
        collect_payload.get("strategy") or source_status.get("mode") or ""
    ).strip()

    event = str(event_context.get("event") or "").strip()
    summary_text = str(event_context.get("context_summary") or "").strip()
    supporting_points = [
        str(item).strip()
        for item in event_context.get("supporting_points", [])
        if str(item).strip()
    ]
    evidence_refs = [
        str(item).strip()
        for item in event_context.get("evidence_refs", [])
        if str(item).strip()
    ]

    summary = _build_event_summary(
        event=event,
        summary_text=summary_text,
        supporting_points=supporting_points,
    )
    uncertainty_notes: list[str] = []
    if not evidence_refs:
        uncertainty_notes.append("Event context is still missing strong traceable evidence.")
    next_actions = [
        "Ask about specific sectors, companies, or disclosures for a deeper follow-up.",
    ]

    final_response = reporting_service.build_response(
        response_mode=ResponseMode.EVENT_ANSWER.value,
        session_id=request.session_id or "",
        summary=summary,
        uncertainty_notes=uncertainty_notes,
        next_actions=next_actions,
        final_answer_context={
            "query": request.query,
            "intent": router_result.intent,
            "strategy": strategy,
            "event": event,
            "event_summary": summary_text,
            "supporting_points": supporting_points,
            "event_evidence_refs": evidence_refs,
            "uncertainty_notes": uncertainty_notes,
            "next_actions": next_actions,
        },
    )
    return StageExecutionResult(
        stage_name=StageName.SYNTHESIZE_ANSWER.value,
        status="success",
        output_payload={"final_response": final_response},
        evidence_refs=evidence_refs,
        user_summary=summary,
    )


def _synthesize_report(
    request: AnalysisRequest,
    router_result: RouterResult,
    execution_state: dict[str, StageExecutionResult],
    reporting_service: ReportingService,
) -> StageExecutionResult:
    """证据型报告，读 retrieve_evidence + analyze_targets + collect_event_context。"""
    retrieve_result = execution_state[StageName.RETRIEVE_EVIDENCE.value]
    analyze_targets_result = execution_state.get(StageName.ANALYZE_TARGETS.value)
    collect_context_result = execution_state.get(StageName.COLLECT_EVENT_CONTEXT.value)

    retrieval_result = retrieve_result.output_payload.get("retrieval_result")
    if not isinstance(retrieval_result, RetrievalResult):
        raise TypeError("retrieve_evidence stage missing retrieval_result")

    analyze_targets_payload = _read_stage_output(analyze_targets_result)
    collect_context_payload = _read_stage_output(collect_context_result)
    event_context = dict(collect_context_payload.get("event_context", {}) or {})
    source_status = dict(collect_context_payload.get("source_status", {}) or {})
    strategy = str(
        collect_context_payload.get("strategy") or source_status.get("mode") or ""
    ).strip()

    target_scope = _normalize_parts(analyze_targets_payload.get("target_scope"))
    open_questions = _normalize_parts(analyze_targets_payload.get("open_questions"))
    evidence_count = len(retrieval_result.evidence_items)
    event_evidence_count = len(_normalize_parts(event_context.get("evidence_refs")))
    summary = _build_report_summary(
        evidence_count=evidence_count,
        target_scope=target_scope,
    )

    report_blocks = [
        EvidenceOverviewBlock(
            block_type="evidence_overview",
            title="Evidence Overview",
            items=[
                EvidenceOverviewItem(
                    evidence_id=item.evidence_id,
                    excerpt=item.excerpt,
                    company_name=item.company_name,
                    doc_type=item.doc_type,
                )
                for item in retrieval_result.evidence_items
            ],
        )
    ]
    uncertainty_notes: list[str] = []
    if not evidence_count and strategy != "event_primary":
        uncertainty_notes.append("No strong direct evidence was retrieved yet.")
    uncertainty_notes.extend(open_questions)

    next_actions = ["Ask for a narrower company, time window, or disclosure angle."]
    if target_scope:
        next_actions.insert(
            0, f"Prioritize direct evidence review for {', '.join(target_scope[:2])}."
        )

    final_response = reporting_service.build_response(
        response_mode=ResponseMode.REPORT.value,
        session_id=request.session_id or "",
        summary=summary,
        report_blocks=report_blocks,
        uncertainty_notes=uncertainty_notes,
        next_actions=next_actions,
        final_answer_context={
            "query": request.query,
            "intent": router_result.intent,
            "strategy": strategy,
            "event_summary": str(event_context.get("context_summary") or "").strip(),
            "supporting_points": list(event_context.get("supporting_points") or []),
            "target_scope": target_scope,
            "event_evidence_refs": list(event_context.get("evidence_refs") or []),
            "event_evidence_count": event_evidence_count,
            "company_evidence_count": evidence_count,
            "evidence_items": [
                {
                    "evidence_id": item.evidence_id,
                    "excerpt": item.excerpt,
                    "company_name": item.company_name,
                    "doc_type": item.doc_type,
                }
                for item in retrieval_result.evidence_items
            ],
            "uncertainty_notes": uncertainty_notes,
            "next_actions": next_actions,
        },
    )
    return StageExecutionResult(
        stage_name=StageName.SYNTHESIZE_ANSWER.value,
        status="success",
        output_payload={"final_response": final_response},
        evidence_refs=list(retrieve_result.evidence_refs),
        user_summary=summary,
    )


def _build_event_summary(
    *,
    event: str,
    summary_text: str,
    supporting_points: list[str],
) -> str:
    if summary_text:
        return summary_text
    if supporting_points:
        prefix = event if event else "Current event"
        return f"{prefix} key context: {'; '.join(supporting_points[:3])}"
    if event:
        return f"Completed event-context synthesis for {event}."
    return "Completed event-context synthesis."


def _build_report_summary(
    *,
    evidence_count: int,
    target_scope: list[str],
) -> str:
    if target_scope and evidence_count:
        return (
            f"Retrieved {evidence_count} evidence items for {', '.join(target_scope[:2])}; "
            "ready for report synthesis."
        )
    if target_scope:
        return f"Completed target scoping with focus on {', '.join(target_scope[:3])}."
    if evidence_count:
        return f"Retrieved {evidence_count} evidence items for report synthesis."
    return "No relevant evidence was retrieved."


def _read_stage_output(stage_value: object) -> dict[str, object]:
    if isinstance(stage_value, StageExecutionResult):
        return stage_value.output_payload
    if isinstance(stage_value, dict):
        return stage_value
    return {}


def _read_reflect_ingredients(execution_state: dict[str, object]) -> list[dict]:
    """读取 reflect_and_requery 节点补查到的原料指标结果。

    仅在结构化查询降级且反思成功补查到原料时返回非空列表，供 brief prompt 计算。
    """
    reflect_value = execution_state.get(StageName.REFLECT_AND_REQUERY.value)
    if not isinstance(reflect_value, StageExecutionResult):
        return []
    payload = reflect_value.output_payload
    ingredients = payload.get("ingredient_results")
    if not isinstance(ingredients, list):
        return []
    return [item for item in ingredients if isinstance(item, dict)]


def _normalize_parts(value: object) -> list[str]:
    if isinstance(value, str):
        candidate = value.strip()
        return [candidate] if candidate else []
    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            candidate = str(item).strip()
            if candidate:
                normalized.append(candidate)
        return normalized
    return []


def _safe_float_val(value: str) -> float:
    """把 value 字符串转 float 用于排序，失败返回 0。"""
    try:
        s = str(value).strip().replace(",", "")
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def _build_llm_structured_result(structured_result: dict) -> dict:
    """构造传给 LLM 的 structured_result 副本：records 中 value/unit 换算成展示值。

    让 LLM 生成的 answer_markdown 与 summary 单位一致（亿元/万元），
    避免 LLM 用原始值（如"50744682千元"）生成回答。

    - records 列表：每条加 display_value/display_unit（换算后），保留 value/unit（原始）
    - 扁平 value/unit：也换成展示值
    - is_multi/is_degraded/notes 等其他字段原样保留
    """
    result = dict(structured_result)
    # 换算扁平 value/unit
    raw_value = str(result.get("value", "")).strip()
    raw_unit = str(result.get("unit", "")).strip()
    flat_metric_name = str(result.get("metric") or result.get("metric_name") or "").strip()
    if raw_value or raw_unit:
        dv, du = format_display_value(raw_value, raw_unit, metric_name=flat_metric_name)
        result["value"] = dv
        result["unit"] = du
        result["raw_value"] = raw_value
        result["raw_unit"] = raw_unit
    # 换算 records 列表
    records = result.get("records")
    if isinstance(records, list):
        new_records = []
        for r in records:
            if not isinstance(r, dict):
                new_records.append(r)
                continue
            nr = dict(r)
            rv = str(nr.get("value", "")).strip()
            ru = str(nr.get("unit", "")).strip()
            rec_metric_name = str(nr.get("metric_name") or nr.get("metric") or "").strip()
            if rv or ru:
                dv, du = format_display_value(rv, ru, metric_name=rec_metric_name)
                nr["value"] = dv
                nr["unit"] = du
                nr["raw_value"] = rv
                nr["raw_unit"] = ru
            # 清洗 metric_label 序号前缀
            label = str(nr.get("metric_label", "")).strip()
            if label:
                nr["metric_label"] = _clean_metric_label(label)
            new_records.append(nr)
        result["records"] = new_records
    return result


def _clean_time_scope(time_scope: str) -> str:
    """清洗 time_scope：把 period_end 格式（如 "2024-12-31"）转为友好的"2024年"。

    衍生指标（毛利率/ROE）走 query_metric_lookup 返回的 time_scope 是 period_end
    格式，summary 直接拼接会显示"宁德时代2024-12-31毛利率为..."，需清洗为"2024年"。
    """
    if not time_scope:
        return time_scope
    import re
    # "2024-12-31" → "2024年"
    m = re.match(r"^(20\d{2})-\d{2}-\d{2}$", time_scope)
    if m:
        return f"{m.group(1)}年"
    return time_scope


def _clean_metric_label(label: str) -> str:
    """清洗 metric_label：去掉注释区表常见的序号/章节前缀和尾部括号注释。

    前缀类：
    - 阿拉伯数字序号："1.归属于母公司股东的净利润"、"2.3 应收账款"
    - 中文章节编号："五、净利润"、"七、每股收益"
    - 中文括号编号："(一)基本每股收益"、"（二）稀释每股收益"
    尾部类：
    - 括号注释："净利润(净亏损以'-'号填列)"、"营业收入(含税)"
    保留语义性前缀（如"其中:"、"减:"），这些是合法的财务术语。
    """
    if not label:
        return label
    import re
    s = label.strip()
    # 反复清洗前缀（防止 "（一）1.基本每股收益" 这种复合前缀）
    for _ in range(3):
        prev = s
        # 阿拉伯数字序号前缀："1."、"2.3."、"10 "
        s = re.sub(r"^\d+(\.\d+)*\s*\.?\s*", "", s)
        # 中文括号编号："(一)"、"（二）"等
        s = re.sub(r"^[（(][一二三四五六七八九十百千]+[）)]\s*", "", s)
        # 中文章节编号："五、"、"十二、"等
        s = re.sub(r"^[一二三四五六七八九十百千]+\、\s*", "", s)
        if s == prev:
            break
    # 去尾部括号注释："净利润(净亏损以'-'号填列)" → "净利润"
    # 匹配末尾的中文/英文括号注释（含各种引号）
    s = re.sub(r"[（(][^）)]*[）)]\s*$", "", s).strip()
    return s


def _format_computed_result(structured_result: dict) -> str:
    """格式化路径② 计算结果（ComputedResult）为展示 summary。

    按 kind 分支：
    - aggregate: 标量聚合值 → "{label}为 {value}{unit}。"
    - growth: 增长率 → "{label}为 {value}{unit}。"
    - consecutive: 连续增长判定 → "{label}：{value}。{detail}。"
    - rank: 跨公司排行 → "排名：A X，B Y。"
    """
    kind = str(structured_result.get("kind", ""))
    rows = structured_result.get("rows", [])
    if not isinstance(rows, list) or not rows:
        return "计算失败或数据不足。"

    if kind == "rank":
        parts = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            label = str(r.get("label", ""))
            raw_value = str(r.get("value", ""))
            raw_unit = str(r.get("unit", ""))
            row_metric = str(r.get("metric_name") or r.get("metric") or "")
            # rank 多为金额对比，应用展示换算
            dv, du = format_display_value(raw_value, raw_unit, metric_name=row_metric)
            parts.append(f"{label} {dv}{du}")
        return f"排名：{'，'.join(parts)}。"

    if kind == "consecutive":
        r = rows[0] if isinstance(rows[0], dict) else {}
        label = str(r.get("label", ""))
        value = str(r.get("value", ""))
        detail = str(r.get("detail", "")).strip()
        base = f"{label}：{value}。"
        return f"{base}{detail}。" if detail else base

    # aggregate / growth：单行标量
    r = rows[0] if isinstance(rows[0], dict) else {}
    label = str(r.get("label", ""))
    value = str(r.get("value", ""))
    unit = str(r.get("unit", ""))
    row_metric = str(r.get("metric_name") or r.get("metric") or "")
    # growth 类 unit 是 %，format_display_value 会原样返回；aggregate 类金额会换算到亿元
    display_value, display_unit = format_display_value(value, unit, metric_name=row_metric)
    return f"{label}为 {display_value}{display_unit}。"


def _aggregate_multi_records(records: list[dict]) -> str:
    """聚合多行 MetricRecord 成展示 summary。

    按记录多样性推断展示模式：
    - 多公司单指标 → 排名格式（按 value 降序）
    - 多指标单公司 → 多指标列举格式
    - 多年 → 按年份降序列举
    - 其他 → 逐行兜底列举
    """
    if not records:
        return "未找到对应指标数据。"

    def _get(r: dict, key: str, default: str = "") -> str:
        return str(r.get(key) or default)

    companies = {_get(r, "company_name") for r in records}
    metrics = {_get(r, "metric_name") for r in records}
    periods = {_get(r, "period_end") for r in records}

    if len(companies) > 1 and len(metrics) == 1:
        # 多公司对比：按归一化到元的 value 降序排名（避免千元/元混存导致排序错误）
        metric_label = _clean_metric_label(_get(records[0], "metric_label", _get(records[0], "metric_name")))
        period = _get(records[0], "period_end")
        period_text = f"{period[:4]}年" if len(period) >= 4 else period
        sorted_recs = sorted(
            records,
            key=lambda r: normalize_to_base_unit(_get(r, "value"), _get(r, "unit")) or 0.0,
            reverse=True,
        )
        parts = []
        for r in sorted_recs:
            dv, du = format_display_value(_get(r, "value"), _get(r, "unit"), metric_name=_get(r, "metric_name"))
            parts.append(f"{_get(r, 'company_name')} {dv}{du}")
        return f"{period_text}{metric_label}排名：{'，'.join(parts)}。"

    if len(metrics) > 1 and len(companies) == 1:
        # 多指标
        company = _get(records[0], "company_name")
        period = _get(records[0], "period_end")
        period_text = f"{period[:4]}年" if len(period) >= 4 else period
        parts = []
        for r in records:
            dv, du = format_display_value(_get(r, "value"), _get(r, "unit"), metric_name=_get(r, "metric_name"))
            label = _clean_metric_label(_get(r, "metric_label", _get(r, "metric_name")))
            parts.append(f"{label} {dv}{du}")
        return f"{company}{period_text}：{'，'.join(parts)}。"

    if len(periods) > 1:
        # 多年对比：按 period_end 降序
        company = _get(records[0], "company_name")
        metric_label = _clean_metric_label(_get(records[0], "metric_label", _get(records[0], "metric_name")))
        sorted_recs = sorted(records, key=lambda r: _get(r, "period_end"), reverse=True)
        parts = []
        for r in sorted_recs:
            dv, du = format_display_value(_get(r, "value"), _get(r, "unit"), metric_name=_get(r, "metric_name"))
            parts.append(f"{_get(r, 'period_end')[:4]}年 {dv}{du}")
        return f"{company}{metric_label}：{'，'.join(parts)}。"

    # 兜底：逐行列出
    parts = []
    for r in records:
        dv, du = format_display_value(_get(r, "value"), _get(r, "unit"), metric_name=_get(r, "metric_name"))
        label = _clean_metric_label(_get(r, "metric_label", _get(r, "metric_name")))
        parts.append(f"{_get(r, 'company_name')} {label} {dv}{du}")
    return "；".join(parts) + "。"
