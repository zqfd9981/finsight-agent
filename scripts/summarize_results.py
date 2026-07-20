"""汇总批量测试结果，按 intent/cat 分类统计并标记异常项。

用法：
    python scripts/summarize_results.py
    python scripts/summarize_results.py --jsonl scripts/test_results.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

# 已知异常项（id → 简述），由人工/上一轮分析标记
KNOWN_ISSUES: dict[str, str] = {
    "M-207": "比亚迪营收 7.77亿元（ETL 单位错误，应为 7771 亿元）",
    "M-305": "多指标查询（每股收益+归母净利润）只返回 1 个指标",
    "M-502": "连续增长判定：query 无 N 时未计算，只返回两期数据",
    "M-503": "CAGR 缺期：返回原始数据而非'缺期无法计算'提示",
    "M-504": "CAGR 缺期：返回原始数据而非'缺期无法计算'提示",
    "M-507": "2023 年同比增长率返回原始值 467.61 亿元而非增长率",
    "M-705": "全公司排名：只返回邮储银行且单位为'万元'",
    "M-706": "全公司排名：只返回邮储银行且单位为'万元'",
    "M-708": "全公司排名：单位错误（万元）",
    "M-710": "聚合：返回 4861933367.70 亿元（单位错误）",
    "G-101": "路由错误：被判为 event_impact_analysis 而非 general_finance_qa",
    "G-105": "路由错误：被判为 event_impact_analysis 而非 general_finance_qa",
    "O-007": "路由错误：'现在是牛市还是熊市'被判为 general_finance_qa 而非 out_of_scope",
    "FU-006": "summary 英文泄露：显示 net_profit 而非净利润",
    "FU-003": "比亚迪净利润 4158.79万元（单位错误，应为亿元）",
    "M-004": "比亚迪总资产 7.83亿元（单位错误，应为 7832 亿元）",
    "M-202": "比亚迪营收 7.77亿元（同 M-207，ETL 单位错误）",
    "M-205": "比亚迪净利润未查到（DB 数据问题）",
    "M-206": "五粮液毛利率未查到（数据缺失）",
    "M-208": "山西汾酒数据未查到",
    "M-402": "近三年只返回 2 期（缺 2022 年数据）",
    "M-403": "宁德时代 2023 年总资产未查到",
    "M-404": "贵州茅台 2022 年净利润未查到",
    "M-605": "市值指标未查到（结构化数据无此指标）",
    "M-701": "不存在公司：DB 返回空，summary 含'暂未命中'",
    "M-702": "不存在指标：DB 返回空，summary 含'暂未命中'",
    "M-703": "未来年份：DB 返回空（预期）",
    "M-704": "历史年份缺失：DB 返回空（预期）",
    "M-105": "贵州茅台 ROE 衍生计算失败（原料指标缺失）",
    "M-103": "summary 含日期'2024-12-31'（应清洗为'2024年'）",
    "M-101": "summary 含日期'2024-12-31'",
    "M-102": "summary 含日期'2024-12-31'",
    "M-104": "summary 含日期'2024-12-31'",
    "M-106": "summary 含日期'2024-12-31'",
}


def load_results(path: Path) -> list[dict]:
    items: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--jsonl", default="scripts/test_results.jsonl", help="结果 jsonl 路径"
    )
    args = parser.parse_args()

    path = Path(args.jsonl)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    items = load_results(path)
    print(f"=== 共加载 {len(items)} 条测试结果 ===\n")

    # 按 intent 统计
    by_intent: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        intent = it.get("intent") or "(空)"
        by_intent[intent].append(it)

    print("=== 按 intent 统计 ===")
    for intent, group in sorted(by_intent.items()):
        status_count = defaultdict(int)
        for it in group:
            status_count[it.get("status", "")] += 1
        status_str = ", ".join(f"{k}={v}" for k, v in sorted(status_count.items()))
        print(f"  {intent:30s}  {len(group):3d} 条  [{status_str}]")
    print()

    # 按 cat 统计
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        cat = it.get("cat") or "(空)"
        by_cat[cat].append(it)

    print("=== 按 cat 统计 ===")
    for cat, group in sorted(by_cat.items()):
        print(f"  {cat:45s}  {len(group):3d} 条")
    print()

    # 状态异常
    failed = [it for it in items if it.get("status") != "success"]
    print(f"=== 状态非 success：{len(failed)} 条 ===")
    for it in failed:
        print(f"  {it.get('id')}: status={it.get('status')} error={it.get('error', '')[:80]}")
    print()

    # 已知业务异常
    print(f"=== 已知业务异常：{len(KNOWN_ISSUES)} 条 ===")
    by_id = {it.get("id"): it for it in items}
    for qid, desc in sorted(KNOWN_ISSUES.items()):
        it = by_id.get(qid)
        if it is None:
            print(f"  {qid:6s} [缺失]  {desc}")
            continue
        intent = it.get("intent", "")
        elapsed = it.get("elapsed", 0)
        summary = (it.get("summary") or "").replace("\n", " ")[:70]
        print(f"  {qid:6s} [{intent:25s}] {elapsed:6.1f}s  {summary}")
        print(f"         → {desc}")
    print()

    # 耗时分布
    elapsed_list = sorted(it.get("elapsed", 0) for it in items)
    if elapsed_list:
        avg = sum(elapsed_list) / len(elapsed_list)
        p50 = elapsed_list[len(elapsed_list) // 2]
        p95 = elapsed_list[int(len(elapsed_list) * 0.95)]
        p99 = elapsed_list[-1]
        print(f"=== 耗时分布（秒）avg={avg:.1f} p50={p50:.1f} p95={p95:.1f} max={p99:.1f} ===")

    # 超 60s 的慢查询
    slow = sorted((it for it in items if it.get("elapsed", 0) > 60),
                  key=lambda x: -x.get("elapsed", 0))
    print(f"\n=== 超 60s 慢查询：{len(slow)} 条（Top 10）===")
    for it in slow[:10]:
        print(f"  {it.get('id'):6s}  {it.get('elapsed'):6.1f}s  {it.get('cat','')[:30]:30s}  {(it.get('query') or '')[:40]}")


if __name__ == "__main__":
    main()
