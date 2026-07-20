from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from shared.contracts.final_response import FinalResponse
from shared.enums.response_type import ResponseType

from .compute_registry import compute
from .entities_validator import EntitiesValidator
from .models import (
    ComputePlan,
    ComputedResult,
    MetricLookupResult,
    MetricQuery,
    StructuredQueryResult,
)
from .providers import ExternalMetricProvider, NullExternalMetricProvider
from .repository import MetricRepository
from .sql_assembler import AssemblerError, assemble
from .constraint_resolver import resolve_constraints

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
        self._entities_validator: EntitiesValidator | None = None

    def _ensure_entities_validator(self) -> EntitiesValidator:
        """懒加载 entities 校验器：复用 normalizer 的受控词表。"""
        if self._entities_validator is not None:
            return self._entities_validator
        valid_keys: set[str] = set()
        if self._normalizer is not None:
            # 复用 normalizer 已加载的 aliases dict 的 values()
            aliases = getattr(self._normalizer, "_aliases", None)
            if isinstance(aliases, dict):
                valid_keys = {str(v) for v in aliases.values() if v}
        self._entities_validator = EntitiesValidator(valid_metric_keys=valid_keys)
        return self._entities_validator

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

    # ============================================================
    # Tier 1 确定性组装器主路径（Phase 1）
    # ============================================================

    def query_via_assembler(self, entities: dict) -> StructuredQueryResult:
        """列表型 entities → 校验 → Assembler → 执行 → 多行结果。

        流程：
        1. entities_validator 校验 + 剔除坏实体；列表空 → 直接 fallback。
        2. sql_assembler.assemble 拼参数化 SQL；Assembler 无法表达（即席长尾）→ fallback。
           (Phase 2 在此插入 T2S escape；当前直接 fallback，绝不退步)
        3. repository.execute_parameterized_sql 执行；失败/空 → fallback。
        4. 成功返回 via="assembler"。

        兜底走 find_best_match 单值路径（取 entities 第一个 company/metric）。
        衍生指标/external provider 由调用方（stage runner）在 via=fallback 时
        再调 query_metric_lookup 单值完整路径处理。
        """
        validator = self._ensure_entities_validator()
        # 多指标拆分后 standard_name 可能为空（schema.py 的 _try_split_multi_metric
        # 只填 raw 不填 standard_name）。这里用 normalizer 归一化 raw → standard_name，
        # 确保 validator 能识别。若 normalizer 不可用或归一化失败，原样透传（validator 会剔除）。
        entities = self._normalize_metric_standard_names(entities)
        cleaned = validator.validate(entities)

        if cleaned["need_fallback"]:
            return self._fallback_single(
                entities, reason="entities 校验后 companies/metrics 为空"
            )

        # 2.2 定案：约束校验闸门。Router 顶层 filters/ranking 已注入 entities，
        # 这里经 constraint_resolver 校验/透传（非法项丢弃 + 告警，降级而非失败）。
        raw_filters = entities.get("filters")
        raw_ranking = entities.get("ranking")
        resolved_filters, resolved_ranking, constraint_warnings = resolve_constraints(
            raw_filters, raw_ranking
        )

        try:
            sql, params = assemble(
                companies=cleaned["companies"],
                metrics=cleaned["metrics"],
                periods=cleaned["periods"],
                filters=resolved_filters or None,
                ranking=resolved_ranking,
            )
        except AssemblerError as e:
            # Phase 2: 此处应转 T2S escape；当前直接 fallback，绝不退步
            return self._fallback_single(entities, reason=f"Assembler 无法表达: {e}")

        try:
            records = self._repository.execute_parameterized_sql(sql, params)
        except Exception as e:  # noqa: BLE001 - 兜底任何执行异常
            return self._fallback_single(entities, reason=f"SQL 执行失败: {e}")

        if not records:
            return self._fallback_single(entities, reason="Assembler 结果为空")

        explanation = "确定性组装器主路径"
        if constraint_warnings:
            explanation += f"；约束校验告警: {'; '.join(constraint_warnings)}"
        return StructuredQueryResult(
            records=records,
            sql_used=sql,
            via="assembler",
            explanation=explanation,
        )

    # ============================================================
    # Tier 1b 路径② 取数 + Python 计算（Phase 2 覆盖率扩展）
    # ============================================================

    def query_via_compute(self, plan: ComputePlan) -> ComputedResult | None:
        """路径②：Assembler 取数 → compute_registry 计算 → ComputedResult。

        覆盖 Assembler 构造不出但可确定性计算的查询：聚合/增长/连续增长。
        返回 None 表示计算不适用或数据不足，调用方（stage runner）应回落到 Assembler
        主路径（Assembler 会返回原始行，synthesize 多行聚合展示，作为合理降级）。

        流程：
        1. metric key 校验（受控词表）；不命中 → None。
        2. assemble 取数（companies=None 表示全公司）；失败 → None。
        3. compute_registry 套计算函数；数据不足 → None。
        4. 成功返回 ComputedResult(via="compute")，underlying_records 保留原料行溯源。
        """
        validator = self._ensure_entities_validator()
        # 受控词表非空时必须命中（空表为测试场景，放行）
        if validator._valid_keys and plan.metric not in validator._valid_keys:
            return None

        # 若 router 未给 stock_code（plan.companies 为空）但给了 company_names，
        # 通过 company_name LIKE 反查 company_code 列表，避免 compute 路径误走全公司
        # 导致 yoy/cagr 算的是其他公司的数据。
        companies = plan.companies
        if not companies and plan.company_names:
            companies = self._resolve_company_codes_by_name(plan.company_names)

        try:
            sql, params = assemble(
                companies=companies if companies else None,
                metrics=[plan.metric],
                periods=plan.periods,
            )
        except AssemblerError:
            return None

        try:
            records = self._repository.execute_parameterized_sql(sql, params)
        except Exception:  # noqa: BLE001 - 计算路径失败即降级
            return None

        if not records:
            return None

        kind, rows = compute(plan.op, records, plan)
        if not rows:
            # 增长类（CAGR/连续增长）缺期时，明确返回"缺期无法计算"提示，
            # 而非降级到 Assembler 返回原始行（会让用户误以为已计算）。
            # yoy/qoq 缺期（仅 1 期）也走这里。
            if plan.op in ("cagr", "consecutive_growth", "yoy", "qoq"):
                have = len({r.period_end for r in records if r.company_code == (records[0].company_code if records else "")})
                if plan.op == "cagr":
                    need = (plan.years + 1) if plan.years > 0 else 3
                    op_label = "复合增长率"
                elif plan.op == "consecutive_growth":
                    need = (plan.years + 1) if plan.years > 0 else 2
                    op_label = "连续增长"
                else:
                    need = 2
                    op_label = "同比增长率" if plan.op == "yoy" else "环比增长率"
                return ComputedResult(
                    kind="growth" if plan.op != "consecutive_growth" else "consecutive",
                    rows=[{
                        "label": f"{plan.metric_raw}{op_label}",
                        "value": "缺期无法计算",
                        "unit": "",
                        "detail": f"需 {need} 期数据，仅有 {have} 期；建议补充缺失年份的数据或缩短时间范围",
                    }],
                    via="compute",
                    explanation=f"路径② 取数+计算: op={plan.op} (缺期降级)",
                    underlying_records=records,
                    is_degraded=False,  # compute 确实执行了，只是数据不足；用 rows 承载"缺期"提示
                    error="insufficient_periods",
                )
            # 数据不足（如 CAGR 期数不够）→ 降级，让 Assembler 返回原始行
            return None

        return ComputedResult(
            kind=kind,
            rows=rows,
            via="compute",
            explanation=f"路径② 取数+计算: op={plan.op}",
            underlying_records=records,
        )

    def _fallback_single(
        self, entities: dict, *, reason: str
    ) -> StructuredQueryResult:
        """Assembler 路径失败时，取 entities 第一个 company/metric 走 find_best_match 兜底。

        保证绝不退步：Assembler 失败时回到现状单值逻辑。
        """
        company = self._first_entity(entities.get("company"), "standard_name", "raw")
        company_code = self._first_entity(entities.get("company"), "stock_code")
        metric = self._first_entity(entities.get("metric"), "standard_name", "raw")
        metric_raw = self._first_entity(entities.get("metric"), "raw", "standard_name")
        period_end = self._first_entity(entities.get("time_scope"), "period_end")

        # metric 归一化（中文→英文 key）
        if self._normalizer:
            metric = self._normalizer.normalize(metric)

        query = MetricQuery(
            company_name=company,
            metric_name=metric,
            time_scope=period_end or "latest",
            metric_label_raw=metric_raw or metric,
            company_code=company_code,
            period_end=period_end if period_end not in ("", "latest") else "",
        )
        record = self._repository.find_best_match(query)
        result = StructuredQueryResult.fallback_from_record(
            record, error=reason
        )
        return result

    def _normalize_metric_standard_names(self, entities: dict) -> dict:
        """对 entities.metric 中 standard_name 为空的项，用 normalizer 归一化 raw。

        用于多指标拆分后（schema.py 的 _try_split_multi_metric）：拆分时只填 raw，
        standard_name 留空。这里用 normalizer 把中文 raw 归一化成英文 standard_name，
        让 entities_validator 能识别。

        若 normalizer 不可用，原样返回（validator 会剔除 standard_name 为空的项）。
        """
        if not self._normalizer:
            return entities
        metric = entities.get("metric")
        if not isinstance(metric, list):
            return entities
        new_metric = []
        changed = False
        for m in metric:
            if not isinstance(m, dict):
                new_metric.append(m)
                continue
            std = str(m.get("standard_name") or "").strip()
            raw = str(m.get("raw") or "").strip()
            if not std and raw:
                normalized = self._normalizer.normalize(raw)
                if normalized and normalized != raw:
                    new_m = dict(m)
                    new_m["standard_name"] = normalized
                    new_metric.append(new_m)
                    changed = True
                    continue
            new_metric.append(m)
        if not changed:
            return entities
        new_entities = dict(entities)
        new_entities["metric"] = new_metric
        return new_entities

    def _resolve_company_codes_by_name(
        self, company_names: list[str]
    ) -> list[str]:
        """通过公司名反查 company_code 列表（LIKE 匹配，去重）。

        用于 compute 路径：router 未给 stock_code 但给了 company_names 时，
        避免误走全公司路径导致 yoy/cagr 算错公司。
        """
        if not company_names:
            return []
        codes: list[str] = []
        seen: set[str] = set()
        for name in company_names:
            name = (name or "").strip()
            if not name:
                continue
            try:
                rows = self._repository.execute_parameterized_sql(
                    "SELECT DISTINCT company_code FROM metric_records "
                    "WHERE company_name LIKE ? AND company_code != '' "
                    "LIMIT 5",
                    (f"%{name}%",),
                )
            except Exception:  # noqa: BLE001
                continue
            for row in rows:
                # row 是 tuple，取第一列
                code = str(row[0]).strip() if row else ""
                if code and code not in seen:
                    seen.add(code)
                    codes.append(code)
        return codes

    @staticmethod
    def _first_entity(value, *keys: str, default: str = "") -> str:
        """从列表/单值 entity 里取第一个非空字段值。keys 按优先级尝试。"""
        if value is None:
            return default
        items = value if isinstance(value, list) else [value]
        for it in items:
            if not isinstance(it, dict):
                continue
            for k in keys:
                v = str(it.get(k, "") or "").strip()
                if v:
                    return v
        return default

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
