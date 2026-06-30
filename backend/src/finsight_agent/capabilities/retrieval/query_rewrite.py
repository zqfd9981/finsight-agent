from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RewriteQuery:
    """保守补充出来的检索 query 变体。"""

    query_text: str
    rewrite_type: str


def build_alias_queries(raw_query: str) -> list[RewriteQuery]:
    """基于极小术语表生成首版 alias 查询，不改写原问题意图。"""

    stripped_query = raw_query.strip()
    if not stripped_query:
        return []

    alias_queries: list[RewriteQuery] = []
    seen: set[str] = set()

    for source_term, replacements in _TERM_ALIASES.items():
        if source_term not in stripped_query:
            continue
        for replacement in replacements:
            candidate = stripped_query.replace(source_term, replacement)
            if candidate == stripped_query or candidate in seen:
                continue
            seen.add(candidate)
            alias_queries.append(
                RewriteQuery(
                    query_text=candidate,
                    rewrite_type="alias",
                )
            )
    return alias_queries


_TERM_ALIASES: dict[str, tuple[str, ...]] = {
    # 首版只保留财报里最稳定、最高频的少数口径映射。
    "归母净利润": (
        "归属于上市公司股东的净利润",
        "净利润",
    ),
    "营收": ("营业收入",),
}
