"""批量执行测试 query 集合 v2（115条），记录结果用于排查。

通过 HTTP API 逐个查询，记录：query、intent、耗时、status、summary、answer_markdown、异常。
支持 first_turn 单轮 + follow_up 多轮（带 session_id）。
结果输出到 scripts/test_results.jsonl 和控制台汇总。

用法：
    python scripts/batch_test.py                    # 全量（115条）
    python scripts/batch_test.py --ids M-001,M-002  # 指定 id
    python scripts/batch_test.py --no-followup      # 跳过多轮
    python scripts/batch_test.py --cats metric_lookup  # 按分类筛选
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_URL = "http://127.0.0.1:8000/api/v1/analysis/turns"
TIMEOUT = 240  # 事件分析 RAG + rerank fallback 可能超过 180s
OUTPUT = REPO_ROOT / "scripts" / "test_results.jsonl"


# 测试 query 集合（与 TEST_QUERIES.md 对应，共 115 条）
TEST_QUERIES: list[dict] = [
    # ===== 一、metric_lookup 路径（48条）=====
    # 1.1 单公司单指标 direct（8条）
    {"id": "M-001", "cat": "metric_lookup/单公司单指标", "query": "宁德时代2024年净利润多少"},
    {"id": "M-002", "cat": "metric_lookup/单公司单指标", "query": "宁德时代2024年归母净利润是多少"},
    {"id": "M-003", "cat": "metric_lookup/单公司单指标", "query": "贵州茅台2024年营业收入"},
    {"id": "M-004", "cat": "metric_lookup/单公司单指标", "query": "比亚迪2024年总资产"},
    {"id": "M-005", "cat": "metric_lookup/单公司单指标", "query": "宁德时代2024年每股收益"},
    {"id": "M-006", "cat": "metric_lookup/单公司单指标", "query": "贵州茅台2024年归母净利润"},
    {"id": "M-007", "cat": "metric_lookup/单公司单指标", "query": "中国平安2024年总资产"},
    {"id": "M-008", "cat": "metric_lookup/单公司单指标", "query": "宁德时代2024年经营现金流"},
    # 1.2 单公司衍生指标（6条）
    {"id": "M-101", "cat": "metric_lookup/衍生指标", "query": "宁德时代2024年毛利率"},
    {"id": "M-102", "cat": "metric_lookup/衍生指标", "query": "宁德时代2024年ROE"},
    {"id": "M-103", "cat": "metric_lookup/衍生指标", "query": "贵州茅台2024年净利率"},
    {"id": "M-104", "cat": "metric_lookup/衍生指标", "query": "比亚迪2024年资产负债率"},
    {"id": "M-105", "cat": "metric_lookup/衍生指标", "query": "贵州茅台2024年净资产收益率"},
    {"id": "M-106", "cat": "metric_lookup/衍生指标", "query": "宁德时代2024年销售净利率"},
    # 1.3 多公司对比（8条）
    {"id": "M-201", "cat": "metric_lookup/多公司对比", "query": "宁德时代，三一重工，赛力斯2024年的归母净利润分别是多少，哪个最多"},
    {"id": "M-202", "cat": "metric_lookup/多公司对比", "query": "宁德时代和比亚迪2024年营收谁更高"},
    {"id": "M-203", "cat": "metric_lookup/多公司对比", "query": "贵州茅台，五粮液，泸州老窖2024年净利润对比"},
    {"id": "M-204", "cat": "metric_lookup/多公司对比", "query": "中国平安和中国人寿2024年总资产哪个更大"},
    {"id": "M-205", "cat": "metric_lookup/多公司对比", "query": "比亚迪和宁德时代2024年净利润哪个高"},
    {"id": "M-206", "cat": "metric_lookup/多公司对比", "query": "贵州茅台和五粮液2024年毛利率谁更高"},
    {"id": "M-207", "cat": "metric_lookup/多公司对比", "query": "宁德时代、比亚迪、赛力斯2024年营收排名"},
    {"id": "M-208", "cat": "metric_lookup/多公司对比", "query": "五粮液、泸州老窖、山西汾酒2024年净利润分别是多少"},
    # 1.4 多指标查询（5条）
    {"id": "M-301", "cat": "metric_lookup/多指标", "query": "宁德时代2024年净利润和营业收入分别是多少"},
    {"id": "M-302", "cat": "metric_lookup/多指标", "query": "贵州茅台2024年总资产和负债合计"},
    {"id": "M-303", "cat": "metric_lookup/多指标", "query": "宁德时代2024年净利润与总资产对比"},
    {"id": "M-304", "cat": "metric_lookup/多指标", "query": "贵州茅台2024年营业收入和净利润和总资产"},
    {"id": "M-305", "cat": "metric_lookup/多指标", "query": "宁德时代2024年每股收益和归母净利润"},
    # 1.5 多期对比与趋势（5条）
    {"id": "M-401", "cat": "metric_lookup/多期对比", "query": "宁德时代2023年和2024年净利润对比"},
    {"id": "M-402", "cat": "metric_lookup/多期趋势", "query": "贵州茅台近三年营收变化"},
    {"id": "M-403", "cat": "metric_lookup/多期对比", "query": "宁德时代2023和2024年总资产变化"},
    {"id": "M-404", "cat": "metric_lookup/多期趋势", "query": "贵州茅台2022到2024年净利润走势"},
    {"id": "M-405", "cat": "metric_lookup/多期对比", "query": "宁德时代2024年vs2023年营收对比"},
    # 1.6 增长率与计算（8条）
    {"id": "M-501", "cat": "metric_lookup/同比增长", "query": "宁德时代2024年净利润同比增长率是多少"},
    {"id": "M-502", "cat": "metric_lookup/连续增长", "query": "宁德时代营收连续增长几年了"},
    {"id": "M-503", "cat": "metric_lookup/复合增长", "query": "宁德时代2022到2024年净利润复合增长率是多少"},
    {"id": "M-504", "cat": "metric_lookup/复合增长", "query": "宁德时代近3年营收复合增长率"},
    {"id": "M-505", "cat": "metric_lookup/同比增长", "query": "贵州茅台2024年营收同比增长率"},
    {"id": "M-506", "cat": "metric_lookup/环比增长", "query": "宁德时代2024年净利润环比增长率是多少"},
    {"id": "M-507", "cat": "metric_lookup/同比增长", "query": "宁德时代2023年净利润同比增长率是多少"},
    {"id": "M-508", "cat": "metric_lookup/连续增长", "query": "贵州茅台营收连续增长几年了"},
    # 1.7 口语/模糊/错别字（6条）
    {"id": "M-601", "cat": "metric_lookup/口语", "query": "宁德时代去年赚了多少钱"},
    {"id": "M-602", "cat": "metric_lookup/简写", "query": "宁德时代2024净利润"},
    {"id": "M-603", "cat": "metric_lookup/口语", "query": "茅台去年赚多少"},
    {"id": "M-604", "cat": "metric_lookup/错别字", "query": "宁德时代2024年净利闰多少"},
    {"id": "M-605", "cat": "metric_lookup/口语", "query": "宁德时代现在市值多少亿"},
    {"id": "M-606", "cat": "metric_lookup/简称", "query": "平安2024年总资产"},
    # 1.8 边界与异常（10条）
    {"id": "M-701", "cat": "metric_lookup/不存在公司", "query": "某某不存在公司2024年净利润"},
    {"id": "M-702", "cat": "metric_lookup/不存在指标", "query": "宁德时代2024年某某不存在指标"},
    {"id": "M-703", "cat": "metric_lookup/未来年份", "query": "宁德时代2026年净利润"},
    {"id": "M-704", "cat": "metric_lookup/历史年份缺失", "query": "宁德时代2020年净利润"},
    {"id": "M-705", "cat": "metric_lookup/全公司排名", "query": "2024年净利润最高的公司是谁"},
    {"id": "M-706", "cat": "metric_lookup/全公司排名", "query": "2024年净利润前3名"},
    {"id": "M-707", "cat": "metric_lookup/全公司排名", "query": "2024年营收最低的公司"},
    {"id": "M-708", "cat": "metric_lookup/全公司排名", "query": "2024年总资产最大的公司"},
    {"id": "M-709", "cat": "metric_lookup/多问题", "query": "宁德时代2024年净利润和营收和总资产分别是多少，哪家公司2024年净利润最高"},
    {"id": "M-710", "cat": "metric_lookup/聚合", "query": "2024年所有公司净利润总和是多少"},

    # ===== 二、event_impact_analysis 路径（25条）=====
    # 2.1 event_primary - 地缘政治事件（4条）
    {"id": "E-001", "cat": "event_impact/event_primary/地缘", "query": "红海局势会对A股哪些板块有什么影响"},
    {"id": "E-002", "cat": "event_impact/event_primary/地缘", "query": "俄乌冲突对A股有什么影响"},
    {"id": "E-003", "cat": "event_impact/event_primary/地缘", "query": "中东局势升级利好哪些股票"},
    {"id": "E-004", "cat": "event_impact/event_primary/地缘", "query": "台海局势对军工板块影响"},
    # 2.2 event_primary - 宏观政策事件（4条）
    {"id": "E-101", "cat": "event_impact/event_primary/宏观", "query": "降息对银行股的影响"},
    {"id": "E-102", "cat": "event_impact/event_primary/宏观", "query": "加息对债市有什么冲击"},
    {"id": "E-103", "cat": "event_impact/event_primary/宏观", "query": "降准利好哪些板块"},
    {"id": "E-104", "cat": "event_impact/event_primary/宏观", "query": "房地产新政对地产股影响"},
    # 2.3 event_primary - 行业事件（2条）
    {"id": "E-201", "cat": "event_impact/event_primary/行业", "query": "近期航运板块受什么影响"},
    {"id": "E-202", "cat": "event_impact/event_primary/行业", "query": "新能源补贴退坡对宁德时代影响"},
    # 2.4 disclosure_primary - 公司公告事件（8条）
    {"id": "D-001", "cat": "event_impact/disclosure_primary/增减持", "query": "宁德时代股东减持公告影响"},
    {"id": "D-002", "cat": "event_impact/disclosure_primary/业绩", "query": "贵州茅台2024年业绩预告影响"},
    {"id": "D-003", "cat": "event_impact/disclosure_primary/并购", "query": "宁德时代收购海外锂矿对股价影响"},
    {"id": "D-004", "cat": "event_impact/disclosure_primary/回购", "query": "比亚迪回购股份意味着什么"},
    {"id": "D-005", "cat": "event_impact/disclosure_primary/高管", "query": "宁德时代高管辞职公告影响"},
    {"id": "D-006", "cat": "event_impact/disclosure_primary/分红", "query": "贵州茅台分红方案对股东影响"},
    {"id": "D-007", "cat": "event_impact/disclosure_primary/定增", "query": "赛力斯定增募资用途和影响"},
    {"id": "D-008", "cat": "event_impact/disclosure_primary/诉讼", "query": "宁德时代诉讼案件对经营影响"},
    # 2.5 dual_primary - 事件+公司双源（7条）
    {"id": "F-001", "cat": "event_impact/dual_primary", "query": "红海局势对中远海控有什么影响"},
    {"id": "F-002", "cat": "event_impact/dual_primary", "query": "锂价下跌对宁德时代和比亚迪的影响"},
    {"id": "F-003", "cat": "event_impact/dual_primary", "query": "芯片禁令对中芯国际影响"},
    {"id": "F-004", "cat": "event_impact/dual_primary", "query": "汇率波动对出口型企业影响，比如海尔智家"},
    {"id": "F-005", "cat": "event_impact/dual_primary", "query": "碳中和政策对宁德时代业务影响"},
    {"id": "F-006", "cat": "event_impact/dual_primary", "query": "特斯拉降价对国内新能源车企冲击"},
    {"id": "F-007", "cat": "event_impact/dual_primary", "query": "关税政策对宁德时代海外业务影响"},

    # ===== 三、general_finance_qa 路径（16条）=====
    # 3.1 概念解释（5条）
    {"id": "G-001", "cat": "general_finance_qa/概念", "query": "什么是市盈率"},
    {"id": "G-002", "cat": "general_finance_qa/概念", "query": "市净率和市盈率区别"},
    {"id": "G-003", "cat": "general_finance_qa/概念", "query": "什么是ROE，怎么计算"},
    {"id": "G-004", "cat": "general_finance_qa/概念", "query": "自由现金流是什么意思"},
    {"id": "G-005", "cat": "general_finance_qa/概念", "query": "资产负债率高好还是低好"},
    # 3.2 宏观机制（5条）
    {"id": "G-101", "cat": "general_finance_qa/宏观", "query": "汇率贬值对出口企业有什么影响"},
    {"id": "G-102", "cat": "general_finance_qa/宏观", "query": "降息周期下债市如何走"},
    {"id": "G-103", "cat": "general_finance_qa/宏观", "query": "通胀对股市影响"},
    {"id": "G-104", "cat": "general_finance_qa/宏观", "query": "M2增速和股市关系"},
    {"id": "G-105", "cat": "general_finance_qa/宏观", "query": "LPR下调对房贷影响"},
    # 3.3 行业常识（3条）
    {"id": "G-201", "cat": "general_finance_qa/行业", "query": "白酒行业景气度怎么看"},
    {"id": "G-202", "cat": "general_finance_qa/行业", "query": "新能源汽车渗透率现状"},
    {"id": "G-203", "cat": "general_finance_qa/行业", "query": "银行业净息差为什么下降"},
    # 3.4 开放观点与边界（3条）
    {"id": "G-301", "cat": "general_finance_qa/开放", "query": "现在适合定投基金吗"},
    {"id": "G-302", "cat": "general_finance_qa/混合", "query": "宁德时代是好公司吗"},
    {"id": "G-303", "cat": "general_finance_qa/混合", "query": "茅台和五粮液哪个更值得买"},

    # ===== 四、evidence_lookup 路径（8条）=====
    {"id": "V-001", "cat": "evidence_lookup/展开", "query": "展开说说宁德时代净利润"},
    {"id": "V-002", "cat": "evidence_lookup/原因", "query": "宁德时代净利润同比变化原因"},
    {"id": "V-003", "cat": "evidence_lookup/原文", "query": "贵州茅台营收数据出处"},
    {"id": "V-004", "cat": "evidence_lookup/依据", "query": "宁德时代ROE计算依据是什么"},
    {"id": "V-005", "cat": "evidence_lookup/详情", "query": "详细说说比亚迪资产负债率"},
    {"id": "V-006", "cat": "evidence_lookup/细节", "query": "宁德时代2024年现金流详情"},
    {"id": "V-007", "cat": "evidence_lookup/对比依据", "query": "宁德时代和比亚迪营收差距依据"},
    {"id": "V-008", "cat": "evidence_lookup/趋势原因", "query": "贵州茅台近三年营收增长原因"},

    # ===== 五、out_of_scope 路径（8条）=====
    {"id": "O-001", "cat": "out_of_scope/荐股", "query": "推荐一只股票"},
    {"id": "O-002", "cat": "out_of_scope/股价", "query": "宁德时代下周股价走势"},
    {"id": "O-003", "cat": "out_of_scope/目标价", "query": "贵州茅台目标价多少"},
    {"id": "O-004", "cat": "out_of_scope/估值", "query": "宁德时代现在估值高吗"},
    {"id": "O-005", "cat": "out_of_scope/短线", "query": "明天买什么股票能涨停"},
    {"id": "O-006", "cat": "out_of_scope/投资建议", "query": "现在该不该卖掉比亚迪"},
    {"id": "O-007", "cat": "out_of_scope/择时", "query": "现在是牛市还是熊市"},
    {"id": "O-008", "cat": "out_of_scope/非金融", "query": "今天天气怎么样"},

    # ===== 六、follow_up 多轮追问（10条，需配合 session_id）=====
    {"id": "FU-001", "cat": "follow_up/redirect", "first_query": "宁德时代2024年净利润多少", "query": "贵州茅台呢"},
    {"id": "FU-002", "cat": "follow_up/drilldown", "first_query": "宁德时代2024年净利润多少", "query": "它的营收呢"},
    {"id": "FU-003", "cat": "follow_up/compare", "first_query": "宁德时代2024年净利润多少", "query": "和比亚迪比怎么样"},
    {"id": "FU-004", "cat": "follow_up/expand", "first_query": "宁德时代2024年净利润多少", "query": "还有呢"},
    {"id": "FU-005", "cat": "follow_up/时间指代", "first_query": "宁德时代2024年净利润多少", "query": "去年呢"},
    {"id": "FU-006", "cat": "follow_up/指标指代", "first_query": "宁德时代2024年净利润多少", "query": "它的同比增长率呢"},
    {"id": "FU-007", "cat": "follow_up/redirect", "first_query": "红海局势对A股哪些板块有影响", "query": "降息呢"},
    {"id": "FU-008", "cat": "follow_up/drilldown", "first_query": "宁德时代2024年毛利率", "query": "怎么算的"},
    {"id": "FU-009", "cat": "follow_up/compare", "first_query": "贵州茅台2024年净利润", "query": "五粮液呢"},
    {"id": "FU-010", "cat": "follow_up/expand", "first_query": "宁德时代2024年净利润", "query": "还有哪些新能源公司"},
]


def _extract_intent(trace_blocks: list) -> str:
    """从 trace_blocks 提取 intent。

    TraceBlock 字段是 block_type/payload_summary（不是 stage_name/output_payload）。
    """
    for block in trace_blocks or []:
        if not isinstance(block, dict):
            continue
        if block.get("block_type") == "routing" or block.get("stage_name") == "routing":
            payload = block.get("payload_summary") or block.get("output_payload") or {}
            return str(payload.get("intent") or "")
    return ""


def _extract_strategy(trace_blocks: list) -> str:
    """从 trace_blocks 提取 retrieval_strategy（event_primary/disclosure_primary/dual_primary）。"""
    for block in trace_blocks or []:
        if not isinstance(block, dict):
            continue
        if (
            block.get("block_type") == "stage_planning"
            or block.get("stage_name") == "stage_planning"
        ):
            payload = block.get("payload_summary") or block.get("output_payload") or {}
            return str(payload.get("strategy") or "")
    return ""


def run_one(item: dict) -> dict:
    """执行单个 query，返回结果 dict。支持 follow_up 多轮。"""
    qid = item["id"]
    query = item["query"]
    is_followup = "first_query" in item
    start = time.time()
    result = {
        "id": qid,
        "cat": item["cat"],
        "query": query,
        "elapsed": 0.0,
        "status": "unknown",
        "intent": None,
        "strategy": "",
        "summary": "",
        "answer_markdown": "",
        "error": "",
    }
    try:
        # 多轮 follow_up：先发 first_query 建 session，再发 follow_up query
        session_id = None
        if is_followup:
            first_req = urllib.request.Request(
                API_URL,
                data=json.dumps({
                    "query": item["first_query"],
                    "query_mode": "first_turn",
                    "include_trace": False,
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(first_req, timeout=TIMEOUT) as resp:
                    first_data = json.loads(resp.read().decode("utf-8"))
                session_id = first_data.get("session_id") or first_data.get("response", {}).get("session_id")
            except Exception:
                session_id = None  # 首轮失败也继续，fallback 到单轮

        req = urllib.request.Request(
            API_URL,
            data=json.dumps({
                "query": query,
                "query_mode": "follow_up" if is_followup else "first_turn",
                "session_id": session_id or "",
                "include_trace": True,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - start
        result["elapsed"] = round(elapsed, 1)
        resp_obj = data.get("response", {})
        result["summary"] = str(resp_obj.get("summary") or "")[:500]
        result["answer_markdown"] = str(resp_obj.get("answer_markdown") or "")[:500]
        trace = data.get("trace_blocks") or []
        result["intent"] = _extract_intent(trace)
        result["strategy"] = _extract_strategy(trace)
        result["status"] = "success"
    except urllib.error.HTTPError as e:
        result["elapsed"] = round(time.time() - start, 1)
        result["status"] = "http_error"
        result["error"] = f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        result["elapsed"] = round(time.time() - start, 1)
        result["status"] = "timeout" if "timed out" in str(e).lower() else "url_error"
        result["error"] = str(e)
    except Exception as e:
        result["elapsed"] = round(time.time() - start, 1)
        result["status"] = "error"
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def _load_existing_results() -> dict[str, dict]:
    """加载已有结果（按 id 索引），用于跨多次运行合并。

    每次运行不再清空文件，而是把新结果 merge 到已有结果上（同 id 覆盖）。
    这样可以分批跑测试，最终得到一份完整的 115 条结果。
    """
    existing: dict[str, dict] = {}
    if not OUTPUT.exists():
        return existing
    try:
        with OUTPUT.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                qid = str(item.get("id") or "")
                if qid:
                    existing[qid] = item
    except Exception:
        pass
    return existing


def _write_merged_results(merged: dict[str, dict]) -> None:
    """按 TEST_QUERIES 的 id 顺序写出合并后的结果。"""
    # 用 TEST_QUERIES 的 id 顺序排序，未在 TEST_QUERIES 中的追加到末尾
    order = {q["id"]: i for i, q in enumerate(TEST_QUERIES)}
    ordered = sorted(
        merged.values(),
        key=lambda r: (order.get(str(r.get("id", "")), 9999), str(r.get("id", ""))),
    )
    with OUTPUT.open("w", encoding="utf-8") as f:
        for item in ordered:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", default="", help="逗号分隔的 id 列表，如 M-001,M-002")
    parser.add_argument("--cats", default="", help="分类前缀，如 metric_lookup")
    parser.add_argument("--no-followup", action="store_true", help="跳过多轮 follow_up")
    parser.add_argument("--no-events", action="store_true", help="跳过事件类")
    parser.add_argument("--clear", action="store_true", help="清空旧结果（默认 merge）")
    args = parser.parse_args()

    # 加载已有结果（除非 --clear）
    existing = {} if args.clear else _load_existing_results()
    if existing:
        print(f"已加载 {len(existing)} 条历史结果（merge 模式）")

    # 筛选
    queries = list(TEST_QUERIES)
    if args.ids:
        id_set = {x.strip() for x in args.ids.split(",") if x.strip()}
        queries = [q for q in queries if q["id"] in id_set]
    if args.cats:
        queries = [q for q in queries if q["cat"].startswith(args.cats)]
    if args.no_followup:
        queries = [q for q in queries if "first_query" not in q]
    if args.no_events:
        queries = [q for q in queries if not q["cat"].startswith("event_impact")]

    print(f"=== 开始批量测试，共 {len(queries)} 条 ===\n")
    results: list[dict] = []
    for i, item in enumerate(queries, 1):
        qid = item["id"]
        query = item["query"]
        prefix = f"[{i}/{len(queries)}] {qid}"
        print(f"{prefix} {query}")
        result = run_one(item)
        results.append(result)
        # 实时合并到 existing 并写出（防止中途崩溃丢失）
        existing[qid] = result
        _write_merged_results(existing)
        status_icon = "OK" if result["status"] == "success" else "FAIL"
        print(f"  -> [{status_icon}] {result['status']} | intent={result['intent']} | {result['elapsed']}s")
        if result["status"] != "success":
            print(f"     error: {result['error']}")
        if result["summary"]:
            print(f"     summary: {result['summary'][:150]}")
        print()

    # 汇总（仅本次运行）
    total = len(results)
    success = sum(1 for r in results if r["status"] == "success")
    fail = total - success
    print("=" * 60)
    print(f"本次运行: {success}/{total} 成功 ({fail} 失败)")
    # 全量汇总（合并后）
    all_success = sum(1 for r in existing.values() if r.get("status") == "success")
    print(f"累计合并: {all_success}/{len(existing)} 成功")
    print(f"结果已写入 {OUTPUT}")
    if fail > 0:
        print("\n本次失败列表:")
        for r in results:
            if r["status"] != "success":
                print(f"  {r['id']} [{r['status']}] {r['query'][:40]} | {r['error'][:80]}")
    # 按 intent 统计（全量）
    intent_count: dict[str, int] = {}
    for r in existing.values():
        intent = r.get("intent") or "unknown"
        intent_count[intent] = intent_count.get(intent, 0) + 1
    print("\n按 intent 统计（全量）:")
    for k, v in sorted(intent_count.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    # 超时统计
    timeouts = [r for r in results if r["status"] == "timeout"]
    if timeouts:
        print(f"\n超时 query ({len(timeouts)} 条):")
        for r in timeouts:
            print(f"  {r['id']} {r['query'][:40]} | {r['elapsed']}s")


if __name__ == "__main__":
    main()
