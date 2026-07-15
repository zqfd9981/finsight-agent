from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from shared.contracts.final_response import FinalResponse
from shared.enums.response_type import ResponseType

from .models import MetricLookupResult, MetricQuery
from .providers import ExternalMetricProvider, NullExternalMetricProvider
from .repository import MetricRepository

if TYPE_CHECKING:
    from .metric_normalizer import MetricNormalizer


# ============================================================
# 衍生指标定义：年报三表里没有，需从原料指标计算
# ============================================================

# 衍生指标公式：key 是衍生指标名（normalizer 归一化后的 key 或中文原文），
# value 是 (原料指标名列表, 计算函数, 单位, 说明)
# 计算函数接收原料指标的 value（字符串），返回衍生指标的 value（字符串）
def _safe_float(s: str) -> float | None:
    """把带千分位逗号和括号负值的字符串转成 float。"""
    if not s or not isinstance(s, str):
        return None
    s = s.strip().replace(",", "")
    if not s or s in ("-", "—", "N/A", "n/a"):
        return None
    # 括号负值：(123.45) → -123.45
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def _calc_gross_margin(revenue: str, cost: str) -> str | None:
    """毛利率 = (营业收入 - 营业成本) / 营业收入"""
    r = _safe_float(revenue)
    c = _safe_float(cost)
    if r is None or c is None or r == 0:
        return None
    return f"{(r - c) / r * 100:.2f}%"


def _calc_net_margin(revenue: str, net_profit: str) -> str | None:
    """净利率 = 净利润 / 营业收入"""
    r = _safe_float(revenue)
    n = _safe_float(net_profit)
    if r is None or n is None or r == 0:
        return None
    return f"{n / r * 100:.2f}%"


def _calc_roe(net_profit: str, total_equity: str) -> str | None:
    """净资产收益率(ROE) = 净利润 / 所有者权益合计"""
    n = _safe_float(net_profit)
    e = _safe_float(total_equity)
    if n is None or e is None or e == 0:
        return None
    return f"{n / e * 100:.2f}%"


def _calc_debt_ratio(total_liabilities: str, total_assets: str) -> str | None:
    """资产负债率 = 负债合计 / 资产总计"""
    l = _safe_float(total_liabilities)
    a = _safe_float(total_assets)
    if l is None or a is None or a == 0:
        return None
    return f"{l / a * 100:.2f}%"


# 衍生指标表：
# key: 衍生指标名（中文原文或 standard_name）
# value: (原料 metric_name 列表, 计算函数, 单位, 说明)
_DERIVED_METRICS: dict[str, tuple[list[str], object, str, str]] = {
    "毛利率": (["revenue", "operating_cost"], _calc_gross_margin, "%", "(营业收入-营业成本)/营业收入"),
    "销售毛利率": (["revenue", "operating_cost"], _calc_gross_margin, "%", "(营业收入-营业成本)/营业收入"),
    "gross_margin": (["revenue", "operating_cost"], _calc_gross_margin, "%", "(营业收入-营业成本)/营业收入"),
    "净利率": (["revenue", "net_profit"], _calc_net_margin, "%", "净利润/营业收入"),
    "销售净利率": (["revenue", "net_profit"], _calc_net_margin, "%", "净利润/营业收入"),
    "net_margin": (["revenue", "net_profit"], _calc_net_margin, "%", "净利润/营业收入"),
    "净资产收益率": (["net_profit", "total_owners_equity"], _calc_roe, "%", "净利润/所有者权益合计"),
    "ROE": (["net_profit", "total_owners_equity"], _calc_roe, "%", "净利润/所有者权益合计"),
    "roe": (["net_profit", "total_owners_equity"], _calc_roe, "%", "净利润/所有者权益合计"),
    "资产负债率": (["total_liabilities", "total_assets"], _calc_debt_ratio, "%", "负债合计/资产总计"),
    "debt_ratio": (["total_liabilities", "total_assets"], _calc_debt_ratio, "%", "负债合计/资产总计"),
}


class StructuredDataService:
    """metric_lookup 使用的结构化指标查询能力。"""

    def __init__(
        self,
        *,
        metric_repository: MetricRepository | None = None,
        external_provider: ExternalMetricProvider | None = None,
        sqlite_path: str | Path | None = None,
        normalizer: "MetricNormalizer | None" = None,
    ) -> None:
        if metric_repository is not None:
            self._repository = metric_repository
        else:
            # 从 settings 读取 sqlite_path
            if sqlite_path is None:
                from finsight_agent.config.settings import load_settings

                sqlite_path = load_settings().structured_data.sqlite_path
            self._repository = MetricRepository(sqlite_path=sqlite_path)
        self._external_provider = external_provider or NullExternalMetricProvider()
        self._normalizer = normalizer

    def query_metric_lookup(
        self,
        company: str,
        metric: str,
        time_scope: str,
        *,
        company_code: str = "",
        metric_raw: str = "",
        metric_type: str = "direct",
    ) -> dict[str, object]:
        """优先查询本地指标库，未命中时先返回显式降级结果。

        新格式参数（router LLM 直接输出标准格式）：
        - company: 公司 standard_name（如"宁德时代"）
        - metric: 指标 standard_name（已是英文 key，如"net_profit_attributable_to_parent"）
        - time_scope: period_end 日期（YYYY-MM-DD）或 "latest"
        - company_code: 6 位 A 股代码（如"300750"），DB 用 company_code 精确匹配
        - metric_raw: 用户原文中的指标表述（如"归母净利润"），用于 metric_label LIKE 兜底
        - metric_type: direct/derived，derived 时直接走衍生计算

        旧格式兼容：
        - 若 metric 是中文（如"货币资金"），用 normalizer 归一化到英文 key
        - 若 time_scope 是描述格式（如"2024年"），repository 内部 fallback 到 time_scope 字符串匹配
        """
        # 归一化 metric：若 metric 还是中文原文，用 normalizer 归一化（旧格式 fallback）
        # 新格式下 metric 已是 standard_name（英文 key），normalizer 会原样返回
        normalized_metric = (
            self._normalizer.normalize(metric) if self._normalizer else metric
        )

        # metric_type=derived 时直接走衍生计算（router LLM 已识别为衍生指标）
        if metric_type == "derived":
            derived_result = self._try_derived_metric(
                company=company,
                metric=metric,
                normalized_metric=normalized_metric,
                metric_raw=metric_raw or metric,
                time_scope=time_scope,
                company_code=company_code,
            )
            if derived_result is not None:
                return derived_result
            # 衍生指标计算失败（原料缺失等），降级返回
            degraded = MetricLookupResult.degraded(
                company_name=company,
                metric_name=metric,
                time_scope=time_scope,
                notes=["衍生指标计算失败：原料指标缺失或无法计算"],
            )
            return self._to_stage_payload(degraded)

        query = MetricQuery(
            company_name=company,
            metric_name=normalized_metric,
            time_scope=time_scope,
            metric_label_raw=metric_raw or metric,  # 归一化前的中文原文，用于 metric_label LIKE 兜底
            company_code=company_code,
            period_end=time_scope if time_scope not in ("", "latest") else "",
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

        # 衍生指标兜底：direct 未命中时，检查是否是衍生指标（旧格式兼容）
        # 新格式下 router 已识别 metric_type，不会走到这里
        derived_result = self._try_derived_metric(
            company=company,
            metric=metric,
            normalized_metric=normalized_metric,
            metric_raw=metric_raw or metric,
            time_scope=time_scope,
            company_code=company_code,
        )
        if derived_result is not None:
            return derived_result

        degraded = MetricLookupResult.degraded(
            company_name=company,
            metric_name=metric,
            time_scope=time_scope,
            notes=["当前未找到对应指标数据"],
        )
        return self._to_stage_payload(degraded)

    def _try_derived_metric(
        self,
        *,
        company: str,
        metric: str,
        normalized_metric: str,
        metric_raw: str,
        time_scope: str,
        company_code: str = "",
    ) -> dict[str, object] | None:
        """尝试衍生指标计算：毛利率/净利率/ROE/资产负债率等。

        衍生指标不在年报三表里，需从原料指标（营业收入+营业成本等）计算。
        匹配逻辑：先匹配中文原文（metric_raw/metric），再匹配归一化后的 key。
        """
        # 衍生指标匹配：中文原文优先，归一化key兜底
        derived_def = (
            _DERIVED_METRICS.get(metric_raw)
            or _DERIVED_METRICS.get(metric)
            or _DERIVED_METRICS.get(normalized_metric)
        )
        if derived_def is None:
            return None

        ingredient_names, calc_fn, unit, formula_note = derived_def

        # 查原料指标：每个原料指标都查一次本地库
        ingredients: dict[str, str] = {}  # metric_name -> value
        ingredient_sources: list[str] = []
        for ingredient_name in ingredient_names:
            ingredient_query = MetricQuery(
                company_name=company,
                metric_name=ingredient_name,
                time_scope=time_scope,
                metric_label_raw=ingredient_name,
                company_code=company_code,
                period_end=time_scope if time_scope not in ("", "latest") else "",
            )
            ingredient_record = self._repository.find_best_match(ingredient_query)
            if ingredient_record is None:
                # 原料指标缺失，无法计算
                return None
            ingredients[ingredient_name] = ingredient_record.value
            ingredient_sources.append(
                f"{ingredient_name}={ingredient_record.value}"
                f"({ingredient_record.source_document_id})"
            )

        # 按公式计算
        try:
            value = calc_fn(*[ingredients[name] for name in ingredient_names])
        except Exception:
            return None
        if value is None:
            return None

        result = MetricLookupResult(
            company_name=company,
            metric_name=metric,
            time_scope=time_scope,
            value=value,
            unit=unit,
            source_type="derived",
            source_summary=f"衍生计算: {formula_note}; 原料: {'; '.join(ingredient_sources)}",
            matched_by="derived_calculation",
            confidence="medium",  # 衍生指标置信度 medium（计算值，非原始数据）
            is_degraded=False,
            notes=[f"基于年报原料指标计算: {formula_note}"],
        )
        return self._to_stage_payload(result)

    def to_brief_response(self, session_id: str, summary: str) -> FinalResponse:
        """将简答摘要包装成统一最终响应。"""

        return FinalResponse(
            response_type=ResponseType.SUCCESS.value,
            session_id=session_id,
            summary=summary,
            answer_markdown=summary,
        )

    def _to_stage_payload(self, result: MetricLookupResult) -> dict[str, object]:
        payload = asdict(result)
        payload["company"] = result.company_name
        payload["metric"] = result.metric_name
        payload["time_scope"] = result.time_scope
        return payload
