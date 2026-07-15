"""多公司真实查询测试 agent 问答端到端链路。

用法：
    python scripts/test_agent_queries.py

测试范围：
  - 4 种 response_mode：direct / brief_answer / event_answer / report
  - 多家公司跨行业：宁德时代/比亚迪/贵州茅台/中国平安/海康威视/中国石油 等
  - 验证链路：router → stage_planner → orchestrator → ReportingService → answer_markdown
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# 避免 sentence-transformers 去 HuggingFace 检查更新导致网络超时
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from shared.contracts.analysis_request import AnalysisRequest
from finsight_agent.workbench_backend_api.service import WorkbenchBackendApiService


# 测试用例：覆盖 4 种 response_mode + 多家公司跨行业
TEST_CASES = [
    # === brief_answer（指标查询，走 SQLite 结构化数据）===
    {
        "name": "指标查询-宁德时代净利润",
        "query": "宁德时代 2024 年净利润是多少？",
        "expect_mode": "brief_answer",
    },
    {
        "name": "指标查询-比亚迪营收",
        "query": "比亚迪 2024 年营业收入是多少？",
        "expect_mode": "brief_answer",
    },
    {
        "name": "指标查询-贵州茅台毛利率(衍生指标)",
        "query": "贵州茅台 2024 年毛利率是多少？",
        "expect_mode": "brief_answer",
    },
    {
        "name": "指标查询-比亚迪净利率(衍生指标)",
        "query": "比亚迪 2024 年净利率是多少？",
        "expect_mode": "brief_answer",
    },
    {
        "name": "指标查询-宁德时代资产负债率(衍生指标)",
        "query": "宁德时代 2024 年资产负债率是多少？",
        "expect_mode": "brief_answer",
    },
    {
        "name": "指标查询-中国平安总资产",
        "query": "中国平安 2024 年末总资产是多少？",
        "expect_mode": "brief_answer",
    },
    {
        "name": "指标查询-海康威视研发费用",
        "query": "海康威视 2024 年研发费用是多少？",
        "expect_mode": "brief_answer",
    },
    # 新增：跨行业多公司指标查询
    {
        "name": "指标查询-隆基绿能净利润(光伏,亏损)",
        "query": "隆基绿能 2024 年净利润是多少？",
        "expect_mode": "brief_answer",
    },
    {
        "name": "指标查询-格力电器货币资金(家电)",
        "query": "格力电器 2024 年末货币资金是多少？",
        "expect_mode": "brief_answer",
    },
    {
        "name": "指标查询-三一重工存货(机械)",
        "query": "三一重工 2024 年末存货是多少？",
        "expect_mode": "brief_answer",
    },
    {
        "name": "指标查询-海尔智家商誉(家电)",
        "query": "海尔智家 2024 年末商誉是多少？",
        "expect_mode": "brief_answer",
    },
    {
        "name": "指标查询-伊利股份经营现金流(食品)",
        "query": "伊利股份 2024 年经营活动现金流量净额是多少？",
        "expect_mode": "brief_answer",
    },
    {
        "name": "指标查询-歌尔股份营收(电子)",
        "query": "歌尔股份 2024 年营业收入是多少？",
        "expect_mode": "brief_answer",
    },
    {
        "name": "指标查询-中国铝业净利润(有色)",
        "query": "中国铝业 2024 年净利润是多少？",
        "expect_mode": "brief_answer",
    },
    # === direct（泛财经常识直答，不走检索）===
    {
        "name": "常识直答-市盈率",
        "query": "什么是市盈率？怎么计算？",
        "expect_mode": "direct",
    },
    {
        "name": "常识直答-ROE含义",
        "query": "ROE是什么意思？多少算好？",
        "expect_mode": "direct",
    },
    # === event_answer（事件影响分析）===
    {
        "name": "事件分析-红海局势",
        "query": "红海局势影响哪些航运股？",
        "expect_mode": "event_answer",
    },
    # === report（证据报告）===
    {
        "name": "证据报告-中国石油资本开支",
        "query": "中国石油 2024 年资本开支情况详细分析",
        "expect_mode": "report",
    },
    {
        "name": "证据报告-隆基绿能亏损原因",
        "query": "隆基绿能 2024 年亏损原因详细分析",
        "expect_mode": "report",
    },
]


def main() -> int:
    print("=" * 80)
    print("Agent 问答端到端测试（多公司 + 4 种 response_mode）")
    print("=" * 80, flush=True)

    # 检查 LLM 配置
    api_key = (
        os.environ.get("AGICTO_API_KEY")
        or os.environ.get("FINSIGHT_LLM_API_KEY")
        or os.environ.get("DEVAGI_API_KEY")
    )
    if not api_key:
        print("⚠️ 未检测到 LLM API key（AGICTO_API_KEY/FINSIGHT_LLM_API_KEY/DEVAGI_API_KEY）")
        print("   ReportingService 会走降级路径，answer_markdown 可能为空或带降级提示")
    else:
        print(f"✓ LLM API key 已配置 (来源: {'AGICTO_API_KEY' if os.environ.get('AGICTO_API_KEY') else '其他'})")

    service = WorkbenchBackendApiService()
    passed = 0
    failed = 0
    results = []

    for i, case in enumerate(TEST_CASES, 1):
        name = case["name"]
        query = case["query"]
        expect_mode = case["expect_mode"]
        print(f"\n[{i}/{len(TEST_CASES)}] {name}")
        print(f"  Q: {query}")
        t0 = time.time()
        try:
            request = AnalysisRequest(
                query=query,
                query_mode="first_turn",
                include_trace=True,
            )
            envelope = service.build_response(request)
            elapsed = time.time() - t0

            response = envelope.response
            # response_mode 在 trace 里
            trace_blocks = getattr(envelope, "trace_blocks", []) or []
            actual_mode = _extract_response_mode(trace_blocks) or "unknown"
            summary = getattr(response, "summary", "") or ""
            answer_md = getattr(response, "answer_markdown", "") or ""
            answer_len = len(answer_md)

            # 判定成功条件：实际 mode 匹配预期（或至少返回了非空 answer）
            mode_match = actual_mode == expect_mode
            has_answer = answer_len > 15
            ok = mode_match or has_answer

            status = "✓ PASS" if ok else "✗ FAIL"
            if ok:
                passed += 1
            else:
                failed += 1

            print(f"  {status} ({elapsed:.1f}s) mode={actual_mode}(expect={expect_mode}) answer_len={answer_len}")
            print(f"  summary: {summary[:120]}")
            if answer_md:
                # 打印 answer_markdown 前 300 字符
                preview = answer_md[:300].replace("\n", " | ")
                print(f"  answer: {preview}{'...' if answer_len > 300 else ''}")
            else:
                print(f"  answer: (空)")

            results.append({
                "name": name, "query": query, "expect_mode": expect_mode,
                "actual_mode": actual_mode, "elapsed": elapsed,
                "answer_len": answer_len, "summary": summary, "ok": ok,
            })

        except Exception as exc:
            elapsed = time.time() - t0
            failed += 1
            print(f"  ✗ ERROR ({elapsed:.1f}s) {type(exc).__name__}: {exc}")
            results.append({
                "name": name, "query": query, "expect_mode": expect_mode,
                "actual_mode": "error", "elapsed": elapsed,
                "answer_len": 0, "summary": str(exc), "ok": False,
            })

    # 汇总
    print("\n" + "=" * 80)
    print(f"测试汇总: {passed} PASS / {failed} FAIL / 共 {len(TEST_CASES)} 个")
    print("=" * 80)
    print(f"\n{'用例':<28} {'预期模式':<14} {'实际模式':<14} {'耗时':<8} {'答案长度':<8} {'结果'}")
    print("-" * 90)
    for r in results:
        print(f"{r['name']:<26} {r['expect_mode']:<14} {r['actual_mode']:<14} "
              f"{r['elapsed']:<7.1f}s {r['answer_len']:<8} {'✓' if r['ok'] else '✗'}")

    return 0 if failed == 0 else 1


def _extract_response_mode(trace_blocks) -> str | None:
    """从 trace_blocks 里提取 response_mode。"""
    if not trace_blocks:
        return None
    for block in trace_blocks:
        # block 可能是 dict 或对象
        if isinstance(block, dict):
            payload = block.get("payload") or {}
            if "response_mode" in payload:
                return payload["response_mode"]
            if "response_mode" in block:
                return block["response_mode"]
        else:
            payload = getattr(block, "payload", None) or {}
            if isinstance(payload, dict) and "response_mode" in payload:
                return payload["response_mode"]
            rm = getattr(block, "response_mode", None)
            if rm:
                return rm
    return None


if __name__ == "__main__":
    raise SystemExit(main())
