from __future__ import annotations

import re
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
import sqlite3

from .models import MetricQuery, MetricRecord

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 用户语义 time_scope 归一化：把 router 提取的用户语义映射到 DB 归一化值
# DB 归一化值：'2024年' / '期末余额' / '期初余额' / '本期' / '上期'
# 用户语义：'2024 年末' / '2024年末' / '2024年报' / '2024年度' / '2024 年' 等
_YEAR_NORMALIZE_RE = re.compile(r"(\d{4})\s*年?(?:末|初|报|度)?\s*$")


def _normalize_time_scope_for_query(time_scope: str) -> str:
    """把用户语义 time_scope 归一化到 DB 归一化值（旧格式 fallback）。

    新格式下 router 直接输出 period_end 日期，不走此函数。
    旧格式下 time_scope 是描述字符串（如"2024年末"），需归一化到 DB 中的"2024年"。

    - 'latest' → 'latest'（保持）
    - 'YYYY-MM-DD' → 原样（日期格式，走 period_end 匹配）
    - '2024 年末' / '2024年末' / '2024年报' / '2024年度' → '2024年'
    - '2024 年初' / '2024年初' → '2024年'（期初余额也在同一年记录里）
    - '2024' → '2024年'
    - '期末余额'/'期初余额' → 原样（已经是 DB 归一化值）
    """
    if not time_scope or time_scope == "latest":
        return time_scope
    if _DATE_PATTERN.match(time_scope):
        return time_scope
    # 已经是 DB 归一化值
    if time_scope in ("期末余额", "期初余额", "本期", "上期"):
        return time_scope
    # 提取年份，归一化到 'YYYY年'
    m = _YEAR_NORMALIZE_RE.search(time_scope)
    if m:
        return f"{m.group(1)}年"
    return time_scope


class MetricRepository:
    """基于 SQLite 的指标仓储。

    表结构：metric_records，14 个业务字段 + 自增主键。
    联合索引：(company_name, metric_name, time_scope) 支持快速查找。
    """

    def __init__(self, *, sqlite_path: str | Path) -> None:
        self._sqlite_path = Path(sqlite_path)
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """建表 + 索引 + 旧表迁移（幂等）。"""
        with closing(sqlite3.connect(self._sqlite_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metric_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_name TEXT NOT NULL,
                    company_code TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_label TEXT NOT NULL,
                    time_scope TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    value TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_document_id TEXT NOT NULL,
                    source_table_id TEXT NOT NULL,
                    source_caption TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    statement_type TEXT NOT NULL DEFAULT 'unknown',
                    source_section TEXT NOT NULL DEFAULT 'unknown'
                )
                """
            )
            # 旧表迁移：若缺 statement_type / source_section 列则补上
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(metric_records)").fetchall()
            }
            if "statement_type" not in cols:
                conn.execute(
                    "ALTER TABLE metric_records ADD COLUMN statement_type "
                    "TEXT NOT NULL DEFAULT 'unknown'"
                )
            if "source_section" not in cols:
                conn.execute(
                    "ALTER TABLE metric_records ADD COLUMN source_section "
                    "TEXT NOT NULL DEFAULT 'unknown'"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_metric_lookup "
                "ON metric_records(company_name, metric_name, time_scope)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_company "
                "ON metric_records(company_name)"
            )
            # 合并口径优先查询索引
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_statement_priority "
                "ON metric_records(company_name, metric_name, statement_type)"
            )
            # source_section 过滤索引（避免注释表 key 碰撞）
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_source_section "
                "ON metric_records(company_name, metric_name, source_section)"
            )
            # 新增 company_code + period_end 索引（新格式 router 输出）
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_code_period "
                "ON metric_records(company_code, metric_name, period_end)"
            )
            conn.commit()

    def save_records(self, records: list[MetricRecord]) -> None:
        """全量覆盖写入：先清表再批量插入。

        注意：这会清空所有公司数据。如需按公司粒度写入，
        使用 save_records_for_company。
        """
        with closing(sqlite3.connect(self._sqlite_path)) as conn:
            conn.execute("DELETE FROM metric_records")
            self._insert_batch(conn, records)
            conn.commit()

    def save_records_for_company(
        self, company_name: str, records: list[MetricRecord]
    ) -> None:
        """按公司粒度 upsert：先删除该公司旧记录，再插入新记录。

        支持重跑：同一家公司多次解析不会产生重复数据。
        """
        with closing(sqlite3.connect(self._sqlite_path)) as conn:
            conn.execute(
                "DELETE FROM metric_records WHERE company_name = ?",
                (company_name,),
            )
            self._insert_batch(conn, records)
            conn.commit()

    def _insert_batch(
        self, conn: sqlite3.Connection, records: list[MetricRecord]
    ) -> None:
        """批量插入记录。

        asdict(r) 按 MetricRecord 字段声明顺序返回，与下面的列顺序一致
        （statement_type、source_section 是最后两个字段，默认 'unknown'）。
        """
        if not records:
            return
        rows = [tuple(asdict(r).values()) for r in records]
        conn.executemany(
            """
            INSERT INTO metric_records (
                company_name, company_code, metric_name, metric_label,
                time_scope, period_end, value, unit, currency,
                source_type, source_document_id, source_table_id,
                source_caption, confidence, statement_type, source_section
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    def load_records(self) -> list[MetricRecord]:
        """全量加载（调试用，生产查询用 find_best_match）。"""
        with closing(sqlite3.connect(self._sqlite_path)) as conn:
            rows = conn.execute(
                """
                SELECT company_name, company_code, metric_name, metric_label,
                       time_scope, period_end, value, unit, currency,
                       source_type, source_document_id, source_table_id,
                       source_caption, confidence, statement_type, source_section
                FROM metric_records
                """
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    # 合并口径优先：consolidated(0) > unknown(1) > parent_only(2)
    _STMT_PRIORITY = (
        "CASE statement_type "
        "WHEN 'consolidated' THEN 0 "
        "WHEN 'unknown' THEN 1 "
        "WHEN 'parent_only' THEN 2 "
        "ELSE 1 END"
    )

    def find_best_match(
        self, query: MetricQuery, *, include_notes: bool = False
    ) -> MetricRecord | None:
        """按 company + metric 查找，period_end 精确匹配或取最新。

        新格式（router LLM 直接输出 standard_name + period_end + stock_code）：
        - 优先用 company_code 精确匹配（6 位 A 股代码）
        - 用 period_end 日期精确匹配（YYYY-MM-DD）
        - metric_name 已是英文 key（如 cash_and_equivalents），直接精确匹配

        旧格式 fallback（company_code 为空 / period_end 为空 / time_scope 是描述字符串）：
        - company_name LIKE 匹配
        - time_scope 归一化后字符串匹配（_normalize_time_scope_for_query）
        - metric_label LIKE 兜底（口语"净利润"→DB"归属于母公司股东的净利润"）

        Args:
            include_notes: 是否包含注释表数据。默认 False 只查三表，避免 key 碰撞。
                True 时加上 source_section='notes' 的记录。
        """
        select_cols = (
            "SELECT company_name, company_code, metric_name, metric_label, "
            "time_scope, period_end, value, unit, currency, "
            "source_type, source_document_id, source_table_id, "
            "source_caption, confidence, statement_type, source_section "
            "FROM metric_records"
        )
        stmt_order = self._STMT_PRIORITY
        # source_section 过滤：默认只查三表，include_notes=True 加上注释
        if include_notes:
            section_filter = (
                "source_section IN ('balance_sheet', 'income_statement', "
                "'cash_flow_statement', 'equity_statement', 'notes', 'unknown')"
            )
        else:
            section_filter = (
                "source_section IN ('balance_sheet', 'income_statement', "
                "'cash_flow_statement', 'equity_statement', 'unknown')"
            )
        with closing(sqlite3.connect(self._sqlite_path)) as conn:
            # 新格式优先：company_code + period_end 日期查询
            row = self._query_by_code_and_period(
                conn, select_cols, stmt_order, query, section_filter
            )
            if row is not None:
                return self._row_to_record(row)

            # 旧格式 fallback：company_name LIKE + time_scope 字符串匹配
            row = self._query_legacy_fallback(
                conn, select_cols, stmt_order, query, section_filter
            )
        return self._row_to_record(row) if row else None

    def _query_by_code_and_period(
        self, conn, select_cols: str, stmt_order: str, query: MetricQuery,
        section_filter: str,
    ):
        """新格式查询：company_code 精确 + period_end 日期匹配。

        覆盖：
        1. company_code + metric_name + period_end 精确（合并口径优先）
        2. company_code + metric_label LIKE + period_end（口语兜底）
        3. company_code + metric_name + latest（period_end DESC）
        4. company_name LIKE + metric_name + period_end（company_code 缺失时 fallback）
        """
        # 没有 company_code，跳过新格式
        if not query.company_code:
            return None

        # period_end 是日期格式：精确匹配
        if query.period_end and _DATE_PATTERN.match(query.period_end):
            # 第 1 层：company_code + metric_name + period_end 精确
            row = conn.execute(
                f"{select_cols} WHERE company_code = ? AND metric_name = ? "
                f"AND period_end = ? AND {section_filter} "
                f"ORDER BY {stmt_order} LIMIT 1",
                (query.company_code, query.metric_name, query.period_end),
            ).fetchone()
            if row is not None:
                return row
            # 第 2 层：company_code + metric_label LIKE + period_end
            if query.metric_label_raw:
                row = conn.execute(
                    f"{select_cols} WHERE company_code = ? "
                    f"AND metric_label LIKE ? AND period_end = ? "
                    f"AND {section_filter} "
                    f"ORDER BY {stmt_order} LIMIT 1",
                    (query.company_code, f"%{query.metric_label_raw}%", query.period_end),
                ).fetchone()
                if row is not None:
                    return row
            return None

        # period_end 为空或 "latest"：取最新报告期
        if not query.period_end or query.period_end == "latest":
            # 第 3 层：company_code + metric_name + ORDER BY period_end DESC
            row = conn.execute(
                f"{select_cols} WHERE company_code = ? AND metric_name = ? "
                f"AND {section_filter} "
                f"ORDER BY period_end DESC, {stmt_order} LIMIT 1",
                (query.company_code, query.metric_name),
            ).fetchone()
            if row is None and query.metric_label_raw:
                row = conn.execute(
                    f"{select_cols} WHERE company_code = ? "
                    f"AND metric_label LIKE ? AND {section_filter} "
                    f"ORDER BY period_end DESC, {stmt_order} LIMIT 1",
                    (query.company_code, f"%{query.metric_label_raw}%"),
                ).fetchone()
            return row

        return None

    def _query_legacy_fallback(
        self, conn, select_cols: str, stmt_order: str, query: MetricQuery,
        section_filter: str,
    ):
        """旧格式 fallback：company_name LIKE + time_scope 字符串匹配。

        当 company_code 为空（旧格式 router 输出）或新格式未命中时使用。
        保留原 6 层降级逻辑中的核心部分。
        """
        # 归一化 time_scope：旧格式用户语义（如 '2024 年末'）映射到 DB 归一化值（如 '2024年'）
        normalized_scope = _normalize_time_scope_for_query(query.time_scope)
        if normalized_scope != query.time_scope:
            query = MetricQuery(
                company_name=query.company_name,
                metric_name=query.metric_name,
                time_scope=normalized_scope,
                allow_external_fallback=query.allow_external_fallback,
                metric_label_raw=query.metric_label_raw,
                company_code=query.company_code,
                period_end=query.period_end,
            )

        # 'latest' 或日期格式：走 period_end DESC 排序
        if query.time_scope == "latest" or _DATE_PATTERN.match(query.time_scope):
            if _DATE_PATTERN.match(query.time_scope):
                # 日期格式：period_end 精确匹配
                row = conn.execute(
                    f"{select_cols} WHERE company_name LIKE ? AND metric_name = ? "
                    f"AND period_end = ? AND {section_filter} "
                    f"ORDER BY {stmt_order} LIMIT 1",
                    (f"%{query.company_name}%", query.metric_name, query.time_scope),
                ).fetchone()
                if row is None and query.metric_label_raw:
                    row = conn.execute(
                        f"{select_cols} WHERE company_name LIKE ? "
                        f"AND metric_label LIKE ? AND period_end = ? "
                        f"AND {section_filter} "
                        f"ORDER BY {stmt_order} LIMIT 1",
                        (f"%{query.company_name}%", f"%{query.metric_label_raw}%", query.time_scope),
                    ).fetchone()
                return row
            # latest：period_end DESC
            row = conn.execute(
                f"{select_cols} WHERE company_name LIKE ? AND metric_name = ? "
                f"AND {section_filter} "
                f"ORDER BY period_end DESC, {stmt_order} LIMIT 1",
                (f"%{query.company_name}%", query.metric_name),
            ).fetchone()
            if row is None and query.metric_label_raw:
                row = conn.execute(
                    f"{select_cols} WHERE company_name LIKE ? "
                    f"AND metric_label LIKE ? AND {section_filter} "
                    f"ORDER BY period_end DESC, {stmt_order} LIMIT 1",
                    (f"%{query.company_name}%", f"%{query.metric_label_raw}%"),
                ).fetchone()
            return row

        # 描述格式（如"2024年"）：走 3 层精确/前缀匹配
        return self._query_description_scope(
            conn, select_cols, stmt_order, query, section_filter
        )

    def _query_description_scope(
        self, conn, select_cols: str, stmt_order: str, query: MetricQuery,
        section_filter: str,
    ):
        """处理描述格式 time_scope（如"2024年"）。返回 row 或 None。

        3 层：
        1. metric_name 精确 + time_scope 精确（合并口径优先）
        2. metric_label LIKE + time_scope 精确（口语→正式名兜底）
        3. metric_name 精确 + time_scope LIKE 前缀（"经重述"边缘场景，非重述优先）
        """
        # 第 1 层：metric_name + time_scope 精确
        row = conn.execute(
            f"{select_cols} WHERE company_name LIKE ? AND metric_name = ? "
            f"AND time_scope = ? AND {section_filter} "
            f"ORDER BY {stmt_order} LIMIT 1",
            (f"%{query.company_name}%", query.metric_name, query.time_scope),
        ).fetchone()
        if row is not None:
            return row
        # 第 2 层：metric_label LIKE + time_scope 精确
        if query.metric_label_raw:
            row = conn.execute(
                f"{select_cols} WHERE company_name LIKE ? "
                f"AND metric_label LIKE ? AND time_scope = ? "
                f"AND {section_filter} "
                f"ORDER BY {stmt_order} LIMIT 1",
                (f"%{query.company_name}%", f"%{query.metric_label_raw}%", query.time_scope),
            ).fetchone()
            if row is not None:
                return row
        # 第 3 层：metric_name + time_scope LIKE 前缀（经重述边缘场景）
        # 非重述记录优先；都有的话合并口径优先
        row = conn.execute(
            f"{select_cols} WHERE company_name LIKE ? AND metric_name = ? "
            f"AND time_scope LIKE ? AND time_scope NOT LIKE '%经重述%' "
            f"AND {section_filter} "
            f"ORDER BY {stmt_order} LIMIT 1",
            (f"%{query.company_name}%", query.metric_name, f"{query.time_scope}%"),
        ).fetchone()
        if row is not None:
            return row
        # 最后放宽：允许经重述
        return conn.execute(
            f"{select_cols} WHERE company_name LIKE ? AND metric_name = ? "
            f"AND time_scope LIKE ? AND {section_filter} "
            f"ORDER BY {stmt_order} LIMIT 1",
            (f"%{query.company_name}%", query.metric_name, f"{query.time_scope}%"),
        ).fetchone()

    @staticmethod
    def _row_to_record(row: tuple) -> MetricRecord:
        """把数据库行转成 MetricRecord。"""
        return MetricRecord(
            company_name=row[0],
            company_code=row[1],
            metric_name=row[2],
            metric_label=row[3],
            time_scope=row[4],
            period_end=row[5],
            value=row[6],
            unit=row[7],
            currency=row[8],
            source_type=row[9],
            source_document_id=row[10],
            source_table_id=row[11],
            source_caption=row[12],
            confidence=row[13],
            statement_type=row[14] if len(row) > 14 else "unknown",
            source_section=row[15] if len(row) > 15 else "unknown",
        )
