from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MetricQuery:
    """结构化指标查询的内部标准对象。"""

    company_name: str
    metric_name: str
    time_scope: str
    allow_external_fallback: bool = True
    # 归一化前的原始中文 metric（如"净利润"），用于精确未命中时做 metric_label LIKE 兜底
    metric_label_raw: str = ""
    # 6 位 A 股代码（新格式 router 输出），DB 用 company_code 精确匹配；
    # 空字符串则 fallback 到 company_name LIKE 匹配
    company_code: str = ""
    # period_end 日期（YYYY-MM-DD），新格式 router 输出，DB 用 period_end 字段精确匹配；
    # 空字符串或 "latest" 走最新报告期排序
    period_end: str = ""


@dataclass(slots=True)
class MetricRecord:
    """本地指标库中的标准记录。"""

    company_name: str
    company_code: str
    metric_name: str
    metric_label: str
    time_scope: str
    period_end: str
    value: str
    unit: str
    currency: str
    source_type: str
    source_document_id: str
    source_table_id: str
    source_caption: str
    confidence: str
    # 报表口径：consolidated（合并）/ parent_only（母公司）/ unknown
    statement_type: str = "unknown"
    # 来源章节：balance_sheet/income_statement/cash_flow_statement/notes/equity_statement/unknown
    # 用于查询时区分三表 vs 注释表，避免同名 key 碰撞
    source_section: str = "unknown"


@dataclass(slots=True)
class MetricLookupResult:
    """统一结构化指标查询结果。"""

    company_name: str
    metric_name: str
    time_scope: str
    value: str
    unit: str
    source_type: str
    source_summary: str
    matched_by: str
    confidence: str
    is_degraded: bool = False
    notes: list[str] = field(default_factory=list)

    @classmethod
    def degraded(
        cls,
        *,
        company_name: str,
        metric_name: str,
        time_scope: str,
        notes: list[str],
    ) -> "MetricLookupResult":
        return cls(
            company_name=company_name,
            metric_name=metric_name,
            time_scope=time_scope,
            value="",
            unit="",
            source_type="unavailable",
            source_summary="",
            matched_by="none",
            confidence="low",
            is_degraded=True,
            notes=notes,
        )


@dataclass(slots=True)
class StructuredQueryResult:
    """结构化指标查询结果（支持多行，Assembler/T2S/兜底三路统一返回）。

    via 字段记录命中的路径，便于埋点统计覆盖率：
    - "assembler": Tier 1 确定性组装器主路径
    - "t2s_escape": Tier 2 Text-to-SQL 即席兜底（Phase 2 启用）
    - "fallback": find_best_match 终极兜底（现状逻辑，绝不退步）
    - "derived": Tier 3 衍生指标规则表
    """

    records: list[MetricRecord]
    sql_used: str
    via: str  # assembler | t2s_escape | fallback | derived
    is_degraded: bool = False
    via_t2s: bool = False
    explanation: str = ""
    error: str | None = None

    @property
    def is_multi(self) -> bool:
        return len(self.records) > 1

    @classmethod
    def fallback_from_record(
        cls, record: "MetricRecord | None", *, sql_used: str = "", error: str | None = None
    ) -> "StructuredQueryResult":
        """从 find_best_match 的单条结果构造兜底返回。"""
        return cls(
            records=[record] if record else [],
            sql_used=sql_used,
            via="fallback",
            is_degraded=record is None,
            explanation="find_best_match 终极兜底",
            error=error,
        )

    def to_stage_payload(self) -> dict[str, object]:
        """转成 stage payload，兼容现有 _synthesize_brief 单行逻辑 + 支持多行聚合。

        单行：暴露 company/metric/time_scope/value/unit 等扁平字段（取 records[0]）。
        多行：额外暴露 records 列表 + is_multi 标记，由 _aggregate_multi_records 聚合。
        """
        payload: dict[str, object] = {
            "via": self.via,
            "is_multi": self.is_multi,
            "is_degraded": self.is_degraded,
            "via_t2s": self.via_t2s,
            "records": [
                {
                    "company_name": r.company_name,
                    "company_code": r.company_code,
                    "metric_name": r.metric_name,
                    "metric_label": r.metric_label,
                    "time_scope": r.time_scope,
                    "period_end": r.period_end,
                    "value": r.value,
                    "unit": r.unit,
                    "currency": r.currency,
                    "statement_type": r.statement_type,
                    "source_section": r.source_section,
                    "source_document_id": r.source_document_id,
                    "source_caption": r.source_caption,
                }
                for r in self.records
            ],
        }
        if self.records:
            head = self.records[0]
            payload.update(
                {
                    "company": head.company_name,
                    "metric": head.metric_name,
                    "time_scope": head.time_scope,
                    "value": head.value,
                    "unit": head.unit,
                    "notes": [] if not self.is_degraded else ["当前未找到对应指标数据"],
                }
            )
        else:
            payload.update(
                {
                    "company": "",
                    "metric": "",
                    "time_scope": "",
                    "value": "",
                    "unit": "",
                    "notes": ["当前未找到对应指标数据"],
                }
            )
        return payload


@dataclass(slots=True)
class ComputePlan:
    """路径② 计算计划：取数（Assembler）+ Python 计算（compute_registry）。

    用于表达 Assembler 构造不出但可确定性计算的查询：
    聚合（avg/sum/max/min/count）、增长（yoy/qoq/cagr）、连续增长、跨公司比率排行。

    与 StructuredQueryResult 并存（待定决策2）：行形状走 StructuredQueryResult，
    计算形状（标量/排名表）走 ComputedResult。
    """

    op: str  # avg|sum|max|min|count|yoy|qoq|cagr|consecutive_growth|ratio_rank
    metric: str  # standard_name（英文 key），须命中受控词表
    metric_raw: str  # 中文展示名（如"净利润"），用于合成话术
    companies: list[str]  # company_code 列表；空表示全公司
    company_names: list[str]  # 配套公司名（展示用）
    periods: list[str]  # period_end 列表（多期用于 growth/cagr）
    years: int = 0  # cagr/consecutive_growth 的年数
    group_by: str = ""  # "" | "company"（按公司分组聚合）


@dataclass(slots=True)
class ComputedResult:
    """路径② 计算结果（非行形状：聚合值/增长率/排名表）。

    kind 决定 synthesize 格式化分支：
    - "aggregate": 标量聚合值（avg/sum/max/min/count）
    - "growth": 增长率（yoy/qoq/cagr）
    - "consecutive": 连续增长判定（是/否 + 明细）
    - "rank": 跨公司排行（多行）
    """

    kind: str
    rows: list[dict]  # [{"label","value","unit"}, ...]
    via: str  # compute | fallback
    explanation: str
    underlying_records: list[MetricRecord] = field(default_factory=list)
    is_degraded: bool = False
    error: str | None = None

    def to_stage_payload(self) -> dict[str, object]:
        """转 stage payload。带 "computed": True 标记，synthesize 据此走计算结果格式化。"""
        return {
            "computed": True,
            "kind": self.kind,
            "rows": self.rows,
            "via": self.via,
            "explanation": self.explanation,
            "is_degraded": self.is_degraded,
            "underlying_count": len(self.underlying_records),
            # 兼容 _synthesize_brief 的扁平字段读取（计算结果不用这些，但防止 KeyError）
            "company": "",
            "metric": "",
            "time_scope": "",
            "value": "",
            "unit": "",
            "notes": [] if not self.is_degraded else ["计算失败或数据不足"],
        }
