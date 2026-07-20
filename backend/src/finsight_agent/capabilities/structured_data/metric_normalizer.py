"""metric_name 归一化器：中文原文 → 标准英文 key。

策略：
  1. 收集所有唯一 metric_name（中文原文）
  2. 批量调 LLM 生成 {"中文": "标准英文key"} 映射表
  3. 保存到 JSON 文件复用（提取时 0 次 LLM 调用）

标准 key 命名规范：snake_case 英文，参考会计科目标准命名。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .models import MetricRecord


# 行号前缀：年报利润表常见"一、"/"二、"/"1."/"2."/"（1）"等编号
_PREFIX_PATTERNS = [
    re.compile(r"^[一二三四五六七八九十]+、"),
    re.compile(r"^\d+[.、)]"),
    re.compile(r"^（\d+）"),
    re.compile(r"^\(\d+\)"),
    re.compile(r"^第[一二三四五六七八九十\d]+[章节条款]"),
]

# 括号后缀："(净亏损以"-"号填列)"/"(亏损以"-"号填列)"等会计说明
_SUFFIX_PATTERNS = [
    re.compile(r"[(（][^()（）]*[亏损减][^()（）]*[填列）)]*[)）]\s*$"),
    re.compile(r"[(（]净亏损以.*?号填列[)）]\s*$"),
    re.compile(r"[(（]亏损以.*?号填列[)）]\s*$"),
]


def _clean_metric_label(label: str) -> str:
    """清理指标名：去行号前缀 + 去括号后缀会计说明。

    例：
    - "一、营业收入" → "营业收入"
    - "五、净利润(净亏损以"-"号填列)" → "净利润"
    - "1.归属于母公司股东的净利润(净亏损以"-"号填列" → "归属于母公司股东的净利润"
    - "减:营业成本" → "减:营业成本"（保留"减:"语义前缀）
    """
    s = label.strip()
    changed = True
    # 循环清理多层前缀（如"（1）一、营业收入"）
    while changed:
        changed = False
        for p in _PREFIX_PATTERNS:
            m = p.match(s)
            if m:
                s = s[m.end():].strip()
                changed = True
    # 去括号后缀（只去末尾的会计说明括号）
    for p in _SUFFIX_PATTERNS:
        s = p.sub("", s).strip()
    return s


# 已知的常用指标映射（作为 LLM 输出的补充和兜底）
_KNOWN_ALIASES: dict[str, str] = {
    "货币资金": "cash_and_equivalents",
    "交易性金融资产": "trading_financial_assets",
    "应收票据": "notes_receivable",
    "应收账款": "accounts_receivable",
    "预付款项": "prepayments",
    "其他应收款": "other_receivables",
    "存货": "inventory",
    "合同资产": "contract_assets",
    "持有待售资产": "assets_held_for_sale",
    "一年内到期的非流动资产": "non_current_assets_due_within_one_year",
    "其他流动资产": "other_current_assets",
    "流动资产合计": "total_current_assets",
    "可供出售金融资产": "available_for_sale_financial_assets",
    "持有至到期投资": "held_to_maturity_investments",
    "长期应收款": "long_term_receivables",
    "长期股权投资": "long_term_equity_investment",
    "投资性房地产": "investment_property",
    "固定资产": "fixed_assets",
    "在建工程": "construction_in_progress",
    "无形资产": "intangible_assets",
    "商誉": "goodwill",
    "长期待摊费用": "long_term_prepaid_expenses",
    "递延所得税资产": "deferred_tax_assets",
    "其他非流动资产": "other_non_current_assets",
    "非流动资产合计": "total_non_current_assets",
    "资产总计": "total_assets",
    "短期借款": "short_term_borrowings",
    "交易性金融负债": "trading_financial_liabilities",
    "应付票据": "notes_payable",
    "应付账款": "accounts_payable",
    "预收款项": "advance_receipts",
    "应付职工薪酬": "employee_benefits_payable",
    "应交税费": "taxes_payable",
    "其他应付款": "other_payables",
    "一年内到期的非流动负债": "non_current_liabilities_due_within_one_year",
    "其他流动负债": "other_current_liabilities",
    "流动负债合计": "total_current_liabilities",
    "长期借款": "long_term_borrowings",
    "应付债券": "bonds_payable",
    "租赁负债": "lease_liabilities",
    "预计负债": "estimated_liabilities",
    "递延收益": "deferred_income",
    "递延所得税负债": "deferred_tax_liabilities",
    "其他非流动负债": "other_non_current_liabilities",
    "非流动负债合计": "total_non_current_liabilities",
    "负债合计": "total_liabilities",
    "实收资本（或股本）": "paid_in_capital",
    "资本公积": "capital_reserve",
    "减:库存股": "treasury_stock",
    "其他综合收益": "other_comprehensive_income",
    "盈余公积": "surplus_reserve",
    "未分配利润": "undistributed_profits",
    "所有者权益合计": "total_owners_equity",
    "负债和所有者权益总计": "total_liabilities_and_equity",
    "营业收入": "revenue",
    "营业成本": "operating_cost",
    "税金及附加": "taxes_and_surcharges",
    "销售费用": "selling_expenses",
    "管理费用": "administrative_expenses",
    "研发费用": "rd_expenses",
    "财务费用": "financial_expenses",
    "营业利润": "operating_profit",
    "利润总额": "total_profit",
    "所得税费用": "income_tax_expense",
    "净利润": "net_profit",
    "归属于上市公司股东的净利润": "net_profit_attributable_to_parent",
    "归属于母公司股东的净利润": "net_profit_attributable_to_parent",
    # 口语简称（router LLM 常提取的简称形式，需显式映射避免未命中）
    "归母净利润": "net_profit_attributable_to_parent",
    "归母净利": "net_profit_attributable_to_parent",
    "扣非净利润": "deducted_net_profit",
    "扣非归母净利润": "net_profit_attributable_to_parent_excluding_non_recurring_items",
    "归母权益": "total_equity_attributable_to_parent",
    "归母所有者权益": "total_equity_attributable_to_parent",
    "归母净资产": "net_assets_attributable_to_parent_company_shareholders",
    "营收": "revenue",
    "扣除非经常性损益后的净利润": "deducted_net_profit",
    "基本每股收益": "basic_earnings_per_share",
    "稀释每股收益": "diluted_earnings_per_share",
    "每股收益": "basic_earnings_per_share",
    "每股盈利": "basic_earnings_per_share",
    "经营活动产生的现金流量净额": "net_operating_cash_flow",
    "投资活动产生的现金流量净额": "net_investing_cash_flow",
    "筹资活动产生的现金流量净额": "net_financing_cash_flow",
    "现金及现金等价物净增加额": "net_increase_in_cash",
    "期末现金及现金等价物余额": "cash_and_equivalents_at_period_end",
}


class MetricNormalizer:
    """metric_name 归一化器：中文原文 → 标准英文 key。

    用法：
        # 1. 首次构建映射表（调 LLM）
        normalizer = MetricNormalizer(aliases_path=..., llm_client=...)
        normalizer.build_aliases_from_records(records)

        # 2. 后续使用（查本地表，0 次 LLM 调用）
        normalizer = MetricNormalizer(aliases_path=...)
        standard_key = normalizer.normalize("归属于上市公司股东的净利润")
    """

    def __init__(
        self,
        *,
        aliases_path: Path,
        llm_client: Any | None = None,
    ) -> None:
        self._aliases_path = aliases_path
        self._llm_client = llm_client
        self._aliases: dict[str, str] = dict(_KNOWN_ALIASES)  # 先加载已知映射
        self._load_aliases()  # 再加载 LLM 生成的映射（覆盖已知映射）

    def normalize(self, metric_name: str) -> str:
        """返回标准 key，未命中返回原文。

        归一化策略（3 层）：
        1. 原文精确匹配（如"货币资金"直接命中）
        2. 清洗后匹配：去行号前缀("一、"/"1.")+ 去括号后缀("(净亏损...填列)")
           （如"五、净利润(净亏损以"-"号填列)" → "净利润" → 命中）
        3. 清洗后仍未命中：返回清洗后的 label（便于 LLM aliases 二次映射）
        """
        s = metric_name.strip()
        # 第 1 层：原文精确匹配
        if s in self._aliases:
            return self._aliases[s]
        # 第 2 层：清洗后匹配
        cleaned = _clean_metric_label(s)
        if cleaned in self._aliases:
            return self._aliases[cleaned]
        # 第 3 层：返回清洗后的 label（比原文更干净，便于后续 LLM aliases 映射）
        return cleaned

    def to_label(self, standard_key: str) -> str:
        """反向映射：英文 standard_key → 中文 label（用于面向用户的展示）。

        未命中时返回原文（避免空值，调用方应自行判断是否需要 fallback）。

        示例：
            to_label("net_profit_attributable_to_parent") → "归母净利润"
            to_label("unknown_key") → "unknown_key"
        """
        s = standard_key.strip()
        # 反向查找：value → key
        for label, key in self._aliases.items():
            if key == s:
                return label
        return s

    def build_aliases_from_records(
        self, records: list[MetricRecord]
    ) -> dict[str, str]:
        """收集唯一 metric_name，批量调 LLM 生成映射表，保存到 JSON。

        Returns:
            新增的映射 {"中文": "标准key"}
        """
        if self._llm_client is None:
            raise RuntimeError("llm_client is required to build aliases")

        # 收集未命中的唯一 metric_label（始终是中文原文）
        unique_names = sorted(set(r.metric_label for r in records))
        new_names = [n for n in unique_names if n not in self._aliases]

        if not new_names:
            print(f"所有 {len(unique_names)} 个 metric_label 都已有映射，无需调 LLM")
            return {}

        print(f"唯一 metric_label: {len(unique_names)} 个")
        print(f"已有映射: {len(unique_names) - len(new_names)} 个")
        print(f"需 LLM 映射: {len(new_names)} 个")

        # 分批调 LLM（每批 50 个），单批次失败不中断整体流程
        new_aliases: dict[str, str] = {}
        failed_batches: list[int] = []
        batch_size = 50
        total_batches = (len(new_names) + batch_size - 1) // batch_size
        for i in range(0, len(new_names), batch_size):
            batch_num = i // batch_size + 1
            batch = new_names[i : i + batch_size]
            print(f"  批次 {batch_num}/{total_batches}: {len(batch)} 个 ...", end=" ", flush=True)
            # 单批次最多重试 2 次
            batch_result: dict[str, str] = {}
            for attempt in range(3):
                try:
                    batch_result = self._call_llm_for_batch(batch)
                    break
                except Exception as exc:
                    if attempt < 2:
                        print(f"重试({type(exc).__name__})", end=" ", flush=True)
                        time.sleep(3 * (attempt + 1))
                    else:
                        print(f"✗ {type(exc).__name__}: {str(exc)[:60]}", flush=True)
                        failed_batches.append(batch_num)
            else:
                batch_result = {}
            new_aliases.update(batch_result)
            print(f"得到 {len(batch_result)} 条映射")
            # 增量保存：每 5 批保存一次，避免崩溃丢失
            if batch_num % 5 == 0:
                self._aliases.update(new_aliases)
                self._save_aliases()

        # 合并并保存
        self._aliases.update(new_aliases)
        self._save_aliases()
        print(f"\n保存 {len(self._aliases)} 条映射到 {self._aliases_path.name}")
        if failed_batches:
            print(f"⚠️  {len(failed_batches)} 个批次失败：{failed_batches}")

        return new_aliases

    def _call_llm_for_batch(self, names: list[str]) -> dict[str, str]:
        """调 LLM 把一批中文指标名映射到标准英文 key。"""
        from finsight_agent.infra.llm.prompt_registry import get_prompt
        # 从集中 prompts/ 目录加载 prompt 文本
        system_prompt = get_prompt("structured_data.metric_normalizer").text
        result = self._llm_client.complete_json(
            prompt_name="metric_normalizer",
            variables={
                "system_prompt": system_prompt,
                "metric_names": names,
            },
        )
        # result 应该是 {"货币资金": "cash_and_equivalents", ...}
        if not isinstance(result, dict):
            return {}
        return {k: str(v) for k, v in result.items() if isinstance(k, str) and v}

    def _load_aliases(self) -> None:
        """从 JSON 加载已有映射表。"""
        if not self._aliases_path.exists():
            return
        data = json.loads(self._aliases_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            self._aliases.update({str(k): str(v) for k, v in data.items()})

    def _save_aliases(self) -> None:
        """保存映射表到 JSON。"""
        self._aliases_path.parent.mkdir(parents=True, exist_ok=True)
        self._aliases_path.write_text(
            json.dumps(self._aliases, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def aliases(self) -> dict[str, str]:
        """返回当前所有映射（只读）。"""
        return dict(self._aliases)
