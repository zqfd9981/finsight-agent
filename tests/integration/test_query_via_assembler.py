from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.structured_data.metric_normalizer import MetricNormalizer
from finsight_agent.capabilities.structured_data.models import MetricRecord
from finsight_agent.capabilities.structured_data.repository import MetricRepository
from finsight_agent.capabilities.structured_data.service import StructuredDataService

_ALIASES_PATH = REPO_ROOT / "var" / "data" / "structured_data" / "metric_aliases.json"


def _record(**overrides) -> MetricRecord:
    defaults = dict(
        company_name="宁德时代", company_code="300750", metric_name="net_profit",
        metric_label="净利润", time_scope="期末余额", period_end="2024-12-31",
        value="507.45", unit="亿元", currency="CNY",
        source_type="annual_report", source_document_id="doc_001",
        source_table_id="table_001", source_caption="主要会计数据",
        confidence="high", statement_type="consolidated", source_section="income_statement",
    )
    defaults.update(overrides)
    return MetricRecord(**defaults)


def _entities(*, companies, metrics, periods, filters=None, ranking=None) -> dict:
    """构造列表型 entities（router 新格式）。"""
    e: dict = {
        "company": [
            {"raw": c[0], "standard_name": c[0], "stock_code": c[1]} for c in companies
        ],
        "metric": [
            {"raw": m[0], "standard_name": m[1], "metric_type": "direct"} for m in metrics
        ],
        "time_scope": [
            {"raw": p, "period_end": p, "fiscal_year": int(p[:4])} for p in periods
        ],
    }
    if filters is not None:
        e["filters"] = filters
    if ranking is not None:
        e["ranking"] = ranking
    return e


class QueryViaAssemblerIntegrationTest(unittest.TestCase):
    """Phase 1 脏数据集成测试：Assembler 主路径 + 三大正确性场景 + 兜底。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._db_path = Path(self._tmp.name) / "metrics.db"
        self._repo = MetricRepository(sqlite_path=self._db_path)
        # 用真实 aliases 加载 normalizer，让 validator 受控词表生效
        self._normalizer = MetricNormalizer(aliases_path=_ALIASES_PATH)
        self._service = StructuredDataService(
            metric_repository=self._repo,
            normalizer=self._normalizer,
        )

    def _save(self, records: list[MetricRecord]) -> None:
        self._repo.save_records(records)

    # ---- 三大正确性场景 ----

    def test_unit_mixed_cross_company_comparison(self) -> None:
        """头号 bug：千元/亿元混存，跨公司比较必须按 value_numeric 归一。"""
        self._save([
            _record(company_name="A", company_code="000001", value="1000", unit="亿元"),
            _record(company_name="B", company_code="000002", value="500", unit="亿元"),
            _record(company_name="C", company_code="000003", value="80000000", unit="千元"),
        ])
        # 80000000 千元 = 8e7 * 1000 = 8e10 元 = 800 亿
        result = self._service.query_via_assembler(_entities(
            companies=[("A", "000001"), ("B", "000002"), ("C", "000003")],
            metrics=[("净利润", "net_profit")],
            periods=["2024-12-31"],
            ranking={"limit": 5, "by_metric": "net_profit", "desc": True},
        ))
        self.assertEqual(result.via, "assembler")
        self.assertEqual(len(result.records), 3)
        # 按 value_numeric DESC：A(1000亿) > C(800亿) > B(500亿)
        self.assertEqual([r.company_code for r in result.records], ["000001", "000003", "000002"])

    def test_statement_priority_dedup_multi_company(self) -> None:
        """口径去重：同公司同期 consolidated + parent_only，窗口取 consolidated 唯一行。"""
        self._save([
            _record(company_name="宁德", company_code="300750", value="507", unit="亿元",
                    statement_type="consolidated"),
            _record(company_name="宁德", company_code="300750", value="400", unit="亿元",
                    statement_type="parent_only"),
            _record(company_name="格力", company_code="000651", value="321", unit="亿元",
                    statement_type="consolidated"),
            _record(company_name="格力", company_code="000651", value="280", unit="亿元",
                    statement_type="parent_only"),
        ])
        result = self._service.query_via_assembler(_entities(
            companies=[("宁德", "300750"), ("格力", "000651")],
            metrics=[("净利润", "net_profit")],
            periods=["2024-12-31"],
        ))
        self.assertEqual(result.via, "assembler")
        # 每公司只取 consolidated 一行，共 2 行（不会混入 parent_only）
        self.assertEqual(len(result.records), 2)
        for r in result.records:
            self.assertEqual(r.statement_type, "consolidated")

    def test_source_section_notes_excluded(self) -> None:
        """source_section 白名单：notes 表同名 key 必须被排除。"""
        self._save([
            _record(company_name="宁德", company_code="300750", value="100", unit="亿元",
                    source_section="income_statement"),
            _record(company_name="宁德", company_code="300750", value="999", unit="亿元",
                    source_section="notes"),
        ])
        result = self._service.query_via_assembler(_entities(
            companies=[("宁德", "300750")],
            metrics=[("净利润", "net_profit")],
            periods=["2024-12-31"],
        ))
        self.assertEqual(result.via, "assembler")
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].value, "100")  # income_statement 的，非 notes 的 999

    # ---- 查询模式覆盖 ----

    def test_multi_metrics_returns_multiple_rows(self) -> None:
        self._save([
            _record(company_name="宁德", company_code="300750", metric_name="net_profit",
                    metric_label="净利润", value="507", unit="亿元"),
            _record(company_name="宁德", company_code="300750", metric_name="revenue",
                    metric_label="营收", value="4009", unit="亿元"),
        ])
        result = self._service.query_via_assembler(_entities(
            companies=[("宁德", "300750")],
            metrics=[("净利润", "net_profit"), ("营收", "revenue")],
            periods=["2024-12-31"],
        ))
        self.assertEqual(result.via, "assembler")
        names = {r.metric_name for r in result.records}
        self.assertEqual(names, {"net_profit", "revenue"})

    def test_multi_periods_returns_multiple_rows(self) -> None:
        self._save([
            _record(company_name="宁德", company_code="300750", value="507", unit="亿元",
                    period_end="2024-12-31"),
            _record(company_name="宁德", company_code="300750", value="441", unit="亿元",
                    period_end="2023-12-31"),
        ])
        result = self._service.query_via_assembler(_entities(
            companies=[("宁德", "300750")],
            metrics=[("净利润", "net_profit")],
            periods=["2024-12-31", "2023-12-31"],
        ))
        self.assertEqual(result.via, "assembler")
        self.assertEqual(len(result.records), 2)

    def test_value_filter_threshold(self) -> None:
        self._save([
            _record(company_name="A", company_code="000001", value="1000", unit="亿元"),
            _record(company_name="B", company_code="000002", value="500", unit="亿元"),
            _record(company_name="C", company_code="000003", value="80000000", unit="千元"),
        ])
        # 营收超 700 亿：A(1000) ✓, B(500) ✗, C(800) ✓
        result = self._service.query_via_assembler(_entities(
            companies=[("A", "000001"), ("B", "000002"), ("C", "000003")],
            metrics=[("净利润", "net_profit")],
            periods=["2024-12-31"],
            filters=[{"op": ">", "value": 700, "unit": "亿元"}],
        ))
        self.assertEqual(result.via, "assembler")
        codes = {r.company_code for r in result.records}
        self.assertEqual(codes, {"000001", "000003"})

    # ---- 兜底路径 ----

    def test_bad_metric_key_triggers_fallback(self) -> None:
        """坏 metric key 校验剔除后列表空 → need_fallback → find_best_match 兜底。"""
        self._save([_record()])
        result = self._service.query_via_assembler(_entities(
            companies=[("宁德时代", "300750")],
            metrics=[("瞎编", "nonexistent_key_xyz")],
            periods=["2024-12-31"],
        ))
        self.assertEqual(result.via, "fallback")
        self.assertTrue(result.is_degraded)

    def test_empty_result_triggers_fallback(self) -> None:
        """Assembler 执行成功但结果空 → fallback find_best_match。"""
        self._save([_record(period_end="2023-12-31")])  # 数据是 2023，查 2024
        result = self._service.query_via_assembler(_entities(
            companies=[("宁德时代", "300750")],
            metrics=[("净利润", "net_profit")],
            periods=["2024-12-31"],
        ))
        # Assembler 查 2024 空 → fallback find_best_match 查 2024 也空 → degraded
        self.assertEqual(result.via, "fallback")
        self.assertTrue(result.is_degraded)

    def test_single_value_dict_entities_supported(self) -> None:
        """旧格式单值（dict）entities 也能走 assembler 路径。"""
        self._save([_record()])
        entities = {
            "company": {"raw": "宁德时代", "standard_name": "宁德时代", "stock_code": "300750"},
            "metric": {"raw": "净利润", "standard_name": "net_profit", "metric_type": "direct"},
            "time_scope": {"raw": "2024年", "period_end": "2024-12-31", "fiscal_year": 2024},
        }
        result = self._service.query_via_assembler(entities)
        self.assertEqual(result.via, "assembler")
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].value, "507.45")

    def test_via_field_for_telemetry(self) -> None:
        """via 字段记录命中路径，便于埋点统计覆盖率。"""
        self._save([_record()])
        result = self._service.query_via_assembler(_entities(
            companies=[("宁德时代", "300750")],
            metrics=[("净利润", "net_profit")],
            periods=["2024-12-31"],
        ))
        self.assertEqual(result.via, "assembler")
        payload = result.to_stage_payload()
        self.assertEqual(payload["via"], "assembler")
        self.assertFalse(payload["is_multi"])

    def test_to_stage_payload_multi_records(self) -> None:
        """多行结果 to_stage_payload 暴露 records 列表 + is_multi 标记。"""
        self._save([
            _record(company_name="A", company_code="000001", value="1000", unit="亿元"),
            _record(company_name="B", company_code="000002", value="500", unit="亿元"),
        ])
        result = self._service.query_via_assembler(_entities(
            companies=[("A", "000001"), ("B", "000002")],
            metrics=[("净利润", "net_profit")],
            periods=["2024-12-31"],
        ))
        payload = result.to_stage_payload()
        self.assertTrue(payload["is_multi"])
        self.assertEqual(len(payload["records"]), 2)


    def test_invalid_filter_value_degrades_gracefully(self) -> None:
        """约束闸门：非数值 value（如相对值比较把公司名当 value）被丢弃，查询降级为整组返回。

        验证 2.2 定案链路 RouterResult 顶层约束 → entities 注入 → resolve_constraints → assemble：
        非法项不抛异常、不拼错 SQL，而是优雅降级（告警写进 explanation）。
        """
        self._save([
            _record(company_name="A", company_code="000001", value="1000", unit="亿元"),
            _record(company_name="B", company_code="000002", value="500", unit="亿元"),
            _record(company_name="C", company_code="000003", value="800", unit="亿元"),
        ])
        # 模拟 stage runner 把 RouterResult 顶层约束注入 entities 后的形态
        entities = _entities(
            companies=[("A", "000001"), ("B", "000002"), ("C", "000003")],
            metrics=[("净利润", "net_profit")],
            periods=["2024-12-31"],
        )
        entities["filters"] = [{"op": ">", "value": "茅台", "unit": "元"}]  # 非数值 → 应被丢弃
        result = self._service.query_via_assembler(entities)
        self.assertEqual(result.via, "assembler")
        # 非法 filter 被丢弃 → 无筛选 → 三家全返回
        codes = {r.company_code for r in result.records}
        self.assertEqual(codes, {"000001", "000002", "000003"})
        self.assertIn("约束校验告警", result.explanation)

    def test_ranking_limit_one_returns_top(self) -> None:
        """某几家公司中最高：ranking limit=1 只返回 value_numeric 最大的一家。"""
        self._save([
            _record(company_name="A", company_code="000001", value="1000", unit="亿元"),
            _record(company_name="B", company_code="000002", value="500", unit="亿元"),
            _record(company_name="C", company_code="000003", value="800", unit="亿元"),
        ])
        entities = _entities(
            companies=[("A", "000001"), ("B", "000002"), ("C", "000003")],
            metrics=[("净利润", "net_profit")],
            periods=["2024-12-31"],
            ranking={"limit": 1, "desc": True},
        )
        result = self._service.query_via_assembler(entities)
        self.assertEqual(result.via, "assembler")
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].company_code, "000001")  # 1000 亿最大


if __name__ == "__main__":
    unittest.main()
