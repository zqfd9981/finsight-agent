"""SQL 执行器：参数化执行 Assembler/T2S 产出的 SQL + 安全校验。

安全设计（融合主 T2S 方案正则集）：
- SELECT-only：必须以 SELECT 开头。
- 禁危险关键字：INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE/ATTACH/DETACH。
- 禁多语句（;）、注释（--、/* */）、UNION、INTO。
- 表名白名单：FROM/JOIN 后只能是 metric_records。
- LIMIT 上限 100：缺省或超限强制收紧。

参数化优先：params 由调用方（Assembler）传入，绝不字符串拼接用户输入。
T2S escape 路径生成的 SQL 也走同一校验。

本模块不持连接，execute_sql 接受已开的 sqlite3 连接（由 repository 注入），
便于独立单测。
"""
from __future__ import annotations

import re
import sqlite3
from typing import Sequence

from .models import MetricRecord

# 危险关键字（大小写不敏感，单词边界）
_DANGEROUS_PATTERNS = [
    re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|ATTACH|DETACH)\b"),
    re.compile(r";"),                       # 禁多语句
    re.compile(r"--"),                      # 禁行注释
    re.compile(r"/\*.*?\*/", re.DOTALL),    # 禁块注释
    re.compile(r"\bUNION\b"),               # 禁 UNION
    re.compile(r"\bINTO\b"),                # 禁 INTO
]

_ALLOWED_TABLES = {"metric_records"}
_LIMIT_MAX = 100
_LIMIT_RE = re.compile(r"LIMIT\s+(\d+)", re.IGNORECASE)

# MetricRecord 业务字段（与 _row_to_record 对齐，按列名取值）
_RECORD_FIELDS = (
    "company_name", "company_code", "metric_name", "metric_label",
    "time_scope", "period_end", "value", "unit", "currency",
    "source_type", "source_document_id", "source_table_id",
    "source_caption", "confidence", "statement_type", "source_section",
)


class SqlValidationError(ValueError):
    """SQL 安全校验未通过。"""


def validate_sql(sql: str) -> None:
    """校验 SQL 安全性，不通过抛 SqlValidationError。"""
    if not sql or not sql.strip():
        raise SqlValidationError("SQL 为空")
    sql_stripped = sql.strip()
    sql_upper = sql_stripped.upper()
    if not sql_upper.startswith("SELECT"):
        raise SqlValidationError("只允许 SELECT 语句")
    for pattern in _DANGEROUS_PATTERNS:
        m = pattern.search(sql_upper)
        if m:
            raise SqlValidationError(f"SQL 含危险关键字: {m.group(0)}")
    # 表名白名单：抓 FROM/JOIN 后的标识符
    for m in re.finditer(r"(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", sql_stripped, re.IGNORECASE):
        if m.group(1).lower() not in _ALLOWED_TABLES:
            raise SqlValidationError(f"非法表名: {m.group(1)}")


def _enforce_limit(sql: str) -> str:
    """确保 LIMIT ≤ _LIMIT_MAX；缺省或超限则收紧到 _LIMIT_MAX。"""
    m = _LIMIT_RE.search(sql)
    if m:
        n = int(m.group(1))
        if n > _LIMIT_MAX:
            return _LIMIT_RE.sub(f"LIMIT {_LIMIT_MAX}", sql)
        return sql
    # 无 LIMIT，追加。注意窗口函数 SQL 已有外层 SELECT * FROM (...)，追加 LIMIT 安全。
    return f"{sql.rstrip(';')} LIMIT {_LIMIT_MAX}"


def _row_to_record(row: sqlite3.Row, col_index: dict[str, int]) -> MetricRecord:
    """按列名从 sqlite3.Row 构建 MetricRecord。缺列用默认值。"""
    def _get(name: str, default: str = "") -> str:
        idx = col_index.get(name)
        if idx is None:
            return default
        val = row[idx]
        return str(val) if val is not None else default
    return MetricRecord(
        company_name=_get("company_name"),
        company_code=_get("company_code"),
        metric_name=_get("metric_name"),
        metric_label=_get("metric_label"),
        time_scope=_get("time_scope"),
        period_end=_get("period_end"),
        value=_get("value"),
        unit=_get("unit"),
        currency=_get("currency"),
        source_type=_get("source_type"),
        source_document_id=_get("source_document_id"),
        source_table_id=_get("source_table_id"),
        source_caption=_get("source_caption"),
        confidence=_get("confidence"),
        statement_type=_get("statement_type", "unknown"),
        source_section=_get("source_section", "unknown"),
    )


def execute_sql(
    conn: sqlite3.Connection,
    sql: str,
    params: Sequence[object],
) -> list[MetricRecord]:
    """校验 + 执行参数化 SQL，返回 MetricRecord 列表。

    Args:
        conn: 已开的 sqlite3 连接（由 repository 注入）。
        sql: Assembler 或 T2S 产出的 SQL（参数化占位符）。
        params: 占位符参数元组。

    Raises:
        SqlValidationError: 安全校验未通过。
    """
    validate_sql(sql)
    sql = _enforce_limit(sql)
    cursor = conn.execute(sql, tuple(params))
    col_index = {desc[0]: i for i, desc in enumerate(cursor.description)}
    return [_row_to_record(row, col_index) for row in cursor.fetchall()]
