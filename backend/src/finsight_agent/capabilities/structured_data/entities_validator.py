"""entities 校验层：router 抽出的列表型 entities 进 Assembler 前的确定性防线。

职责：
- metric 的 standard_name 必须在 metric_aliases.json 受控词表内，否则剔除该实体。
- company_code 基本格式校验（非空、字母数字、长度 4-12），剔除非法值。
- period_end 日期格式校验（YYYY-MM-DD），剔除非法值。
- 校验失败的实体**剔除而非整体失败**；剔除后 metrics/companies 为空则标记 need_fallback=True，
  由 service 直接降级 find_best_match，不进 Assembler，不浪费一次构造。

这把"router 抽错"从"悄悄拼出错误 SQL"变成"剔除坏实体 → 列表空 → 兜底"，
是 ANOTHER 方案缺失的一层防线。

输入兼容：单值（dict，旧格式）和列表（list，新格式）都接受——单值包装成单元素列表。
受控词表：启动时一次性加载 metric_aliases.json 的 values() 到内存 set（约 4000+ key，5-10MB）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

# period_end 日期格式：YYYY-MM-DD
_PERIOD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# company_code 基本格式：字母数字，长度 4-12（覆盖 A 股 6 位、港股 4-5 位、美股字母代码）
# 主要防注入字符（空格/引号/分号），不做交易所严格校验——查不到自然降级。
_CODE_RE = re.compile(r"^[A-Za-z0-9]{4,12}$")


def load_metric_keys(aliases_path: str | Path) -> set[str]:
    """从 metric_aliases.json 加载受控 metric key 集合（values() 去重）。

    文件格式：{"中文标签": "英文key", ...}（扁平 dict）。
    启动时一次性加载到内存，避免每次查询一次 DB。
    """
    path = Path(aliases_path)
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return set()
    return {str(v) for v in data.values() if v}


class EntitiesValidator:
    """entities 校验器。受控词表在构造时一次性加载。"""

    def __init__(self, valid_metric_keys: Optional[set[str]] = None) -> None:
        self._valid_keys = valid_metric_keys if valid_metric_keys is not None else set()

    @classmethod
    def from_aliases_path(cls, aliases_path: str | Path) -> "EntitiesValidator":
        return cls(valid_metric_keys=load_metric_keys(aliases_path))

    def validate(self, entities: dict) -> dict:
        """校验并清洗 router 输出的 entities。

        返回:
            {
              "companies": [company_code, ...],      # 校验通过的 code 列表
              "metrics": [metric_key, ...],          # 校验通过的 key 列表
              "periods": [period_end, ...],          # 校验通过的日期列表
              "company_names": [name, ...],          # 配套的公司名（用于 synthesize 展示）
              "metric_raws": [raw, ...],             # 配套的指标中文名（用于展示）
              "filters": [...],                      # 原样透传（Phase 1 不强校验）
              "ranking": {...} or None,              # 原样透传
              "need_fallback": bool,                 # companies/metrics 为空则 True
            }
        """
        cleaned = {
            "companies": [],
            "metrics": [],
            "periods": [],
            "company_names": [],
            "metric_raws": [],
            "filters": entities.get("filters"),
            "ranking": entities.get("ranking"),
            "need_fallback": False,
        }

        for c in self._as_list(entities.get("company")):
            code = str(c.get("stock_code", "") or "").strip()
            name = str(c.get("standard_name") or c.get("raw") or "").strip()
            if code and _CODE_RE.match(code):
                cleaned["companies"].append(code)
                cleaned["company_names"].append(name or code)

        for m in self._as_list(entities.get("metric")):
            key = str(m.get("standard_name", "") or "").strip()
            raw = str(m.get("raw", "") or "").strip()
            # 受控词表为空时（测试场景）放行所有非空 key；否则必须命中词表
            if key and (not self._valid_keys or key in self._valid_keys):
                cleaned["metrics"].append(key)
                cleaned["metric_raws"].append(raw or key)

        for t in self._as_list(entities.get("time_scope")):
            p = str(t.get("period_end", "") or "").strip()
            if p and _PERIOD_RE.match(p):
                cleaned["periods"].append(p)

        if not cleaned["companies"] or not cleaned["metrics"]:
            cleaned["need_fallback"] = True
        return cleaned

    @staticmethod
    def _as_list(value) -> list[dict]:
        """单值（dict）包装成单元素列表；None/空返回空列表。"""
        if value is None:
            return []
        if isinstance(value, list):
            return [v for v in value if isinstance(v, dict)]
        if isinstance(value, dict):
            return [value]
        return []
