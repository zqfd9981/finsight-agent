from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.structured_data.models import MetricRecord
from finsight_agent.capabilities.structured_data.sql_assembler import assemble
from finsight_agent.capabilities.structured_data.sql_executor import (
    SqlValidationError,
    _enforce_limit,
    execute_sql,
    validate_sql,
)
from finsight_agent.capabilities.structured_data.unit_normalizer import (
    normalize_to_base_unit,
)


def _create_db_with_records(path: Path, records: list[MetricRecord]) -> sqlite3.Connection:
    """建表 + 插入记录，返回连接（含 value_numeric 列）。"""
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE metric_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT, company_code TEXT, metric_name TEXT, metric_label TEXT,
            time_scope TEXT, period_end TEXT, value TEXT, unit TEXT, currency TEXT,
            source_type TEXT, source_document_id TEXT, source_table_id TEXT,
            source_caption TEXT, confidence TEXT,
            statement_type TEXT DEFAULT 'unknown',
            source_section TEXT DEFAULT 'unknown',
            value_numeric REAL
        )
        """
    )
    for r in records:
        vnum = normalize_to_base_unit(r.value, r.unit, r.currency)
        conn.execute(
            """
            INSERT INTO metric_records (
                company_name, company_code, metric_name, metric_label,
                time_scope, period_end, value, unit, currency,
                source_type, source_document_id, source_table_id,
                source_caption, confidence, statement_type, source_section, value_numeric
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                r.company_name, r.company_code, r.metric_name, r.metric_label,
                r.time_scope, r.period_end, r.value, r.unit, r.currency,
                r.source_type, r.source_document_id, r.source_table_id,
                r.source_caption, r.confidence, r.statement_type, r.source_section, vnum,
            ),
        )
    conn.commit()
    return conn


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


class SqlExecutorValidateTest(unittest.TestCase):
    def test_select_passes(self) -> None:
        validate_sql("SELECT * FROM metric_records WHERE x = ?")

    def test_drop_blocked(self) -> None:
        with self.assertRaises(SqlValidationError):
            validate_sql("DROP TABLE metric_records")

    def test_semicolon_blocked(self) -> None:
        with self.assertRaises(SqlValidationError):
            validate_sql("SELECT * FROM metric_records; DROP TABLE x")

    def test_union_blocked(self) -> None:
        with self.assertRaises(SqlValidationError):
            validate_sql("SELECT * FROM metric_records UNION SELECT * FROM users")

    def test_non_select_blocked(self) -> None:
        with self.assertRaises(SqlValidationError):
            validate_sql("DELETE FROM metric_records")

    def test_illegal_table_blocked(self) -> None:
        with self.assertRaises(SqlValidationError):
            validate_sql("SELECT * FROM users")

    def test_block_comment_blocked(self) -> None:
        with self.assertRaises(SqlValidationError):
            validate_sql("SELECT * FROM metric_records /* hack */")

    def test_empty_sql_blocked(self) -> None:
        with self.assertRaises(SqlValidationError):
            validate_sql("")


class EnforceLimitTest(unittest.TestCase):
    def test_no_limit_appended(self) -> None:
        sql = _enforce_limit("SELECT * FROM metric_records")
        self.assertIn("LIMIT 100", sql)

    def test_over_limit_capped(self) -> None:
        sql = _enforce_limit("SELECT * FROM metric_records LIMIT 500")
        self.assertIn("LIMIT 100", sql)
        self.assertNotIn("LIMIT 500", sql)

    def test_under_limit_kept(self) -> None:
        sql = _enforce_limit("SELECT * FROM metric_records LIMIT 5")
        self.assertIn("LIMIT 5", sql)


class ExecuteSqlTest(unittest.TestCase):
    def test_execute_assembler_sql_returns_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn = _create_db_with_records(
                Path(tmp) / "t.db",
                [
                    _record(company_name="宁德时代", company_code="300750", value="507.45", unit="亿元"),
                    _record(company_name="格力电器", company_code="000651", value="321.0", unit="亿元"),
                ],
            )
            sql, params = assemble(
                companies=["300750", "000651"],
                metrics=["net_profit"],
                periods=["2024-12-31"],
                ranking={"limit": 5, "desc": True},
            )
            records = execute_sql(conn, sql, params)
            # 按 value_numeric DESC 排序，宁德（507亿）应在前
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0].company_code, "300750")
            self.assertEqual(records[1].company_code, "000651")
            conn.close()

    def test_execute_filters_by_value(self) -> None:
        # 单位归一：千元 vs 亿元混存，验证跨公司比较正确（头号 bug 修复验证）
        with tempfile.TemporaryDirectory() as tmp:
            conn = _create_db_with_records(
                Path(tmp) / "t.db",
                [
                    _record(company_name="A", company_code="000001", value="1000", unit="亿元"),
                    _record(company_name="B", company_code="000002", value="500", unit="亿元"),
                    _record(company_name="C", company_code="000003", value="80000000", unit="千元"),
                ],
            )
            # 营收超 800 亿：A(1000亿)、C(8000万千元=8000亿... 实际 80000000千元=8e7*1000=8e10元=800亿)
            # 重新算：80000000千元 = 80000000 * 1000 = 8e10 元 = 800 亿。阈值 800 亿 = 8e10 元
            sql, params = assemble(
                companies=["000001", "000002", "000003"],
                metrics=["net_profit"],
                periods=["2024-12-31"],
                filters=[{"op": ">", "value": 700, "unit": "亿元"}],
            )
            records = execute_sql(conn, sql, params)
            codes = {r.company_code for r in records}
            # A=1000亿>700亿 ✓, B=500亿✗, C=800亿>700亿 ✓（千元归一后正确比较）
            self.assertEqual(codes, {"000001", "000003"})
            conn.close()

    def test_statement_priority_window_dedup(self) -> None:
        # 同公司同期有 consolidated + parent_only 两条，窗口去重应只取 consolidated
        with tempfile.TemporaryDirectory() as tmp:
            conn = _create_db_with_records(
                Path(tmp) / "t.db",
                [
                    _record(
                        company_name="宁德", company_code="300750", value="507.45",
                        unit="亿元", statement_type="consolidated",
                    ),
                    _record(
                        company_name="宁德", company_code="300750", value="400.0",
                        unit="亿元", statement_type="parent_only",
                    ),
                ],
            )
            sql, params = assemble(
                companies=["300750"],
                metrics=["net_profit"],
                periods=["2024-12-31"],
            )
            records = execute_sql(conn, sql, params)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].statement_type, "consolidated")
            self.assertEqual(records[0].value, "507.45")
            conn.close()

    def test_source_section_notes_excluded(self) -> None:
        # notes 表的同名 key 应被白名单排除
        with tempfile.TemporaryDirectory() as tmp:
            conn = _create_db_with_records(
                Path(tmp) / "t.db",
                [
                    _record(
                        company_name="宁德", company_code="300750",
                        source_section="income_statement", value="100",
                    ),
                    _record(
                        company_name="宁德", company_code="300750",
                        source_section="notes", value="999",
                    ),
                ],
            )
            sql, params = assemble(
                companies=["300750"],
                metrics=["net_profit"],
                periods=["2024-12-31"],
            )
            records = execute_sql(conn, sql, params)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].value, "100")  # income_statement 的，非 notes 的 999
            conn.close()


if __name__ == "__main__":
    unittest.main()
