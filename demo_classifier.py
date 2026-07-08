"""临时交互 demo：输入 query，看 TrainedRetrievalStrategyClassifier 输出。

用法：

    python demo_classifier.py                # 交互模式
    python demo_classifier.py --query "..."  # 单次输入

输入字段：
- query（必填）
- event / themes / target / time_scope（可空）

输出：
- strategy / confidence / reason（top1 / top2 / margin）
- 加载失败时会打印原因并改走 stub_fallback
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
    StubRetrievalStrategyClassifier,
)
from finsight_agent.control_plane.orchestrator.trained_strategy_classifier import (
    TrainedRetrievalStrategyClassifier,
)


def build_classifier():
    return TrainedRetrievalStrategyClassifier(
        fallback=StubRetrievalStrategyClassifier(),
    )


def run_once(clf, *, query, event, themes, target, time_scope, session_topic):
    router_payload = {
        "intent": "event_impact_analysis",
        "entities": {
            "event": event,
            "themes": [t.strip() for t in themes if t.strip()],
            "target": target,
            "time_scope": time_scope,
        },
    }
    payload = clf.classify(
        query=query,
        router_payload=router_payload,
        session_topic=session_topic,
    )
    return payload


def prompt_nonempty(label: str) -> str:
    while True:
        val = input(f"{label}: ").strip()
        if val:
            return val
        print(f"{label} 不能为空，请重新输入。")


def prompt_optional(label: str) -> str:
    return input(f"{label}（可空，回车跳过）: ").strip()


def interactive_mode(clf):
    print("=" * 60)
    print("检索策略分类器交互 demo（输入 q 退出）")
    print("=" * 60)
    while True:
        first = input("\nquery: ").strip()
        if first.lower() in {"q", "quit", "exit"}:
            break
        if not first:
            print("query 不能为空。")
            continue
        event = prompt_optional("event")
        themes_raw = prompt_optional("themes（逗号分隔）")
        target = prompt_optional("target")
        time_scope = prompt_optional("time_scope")
        payload = run_once(
            clf,
            query=first,
            event=event,
            themes=themes_raw.split(",") if themes_raw else [],
            target=target,
            time_scope=time_scope,
            session_topic="",
        )
        print("-" * 60)
        print(f"strategy   = {payload['strategy']}")
        print(f"confidence = {payload['confidence']}")
        print(f"reason     = {payload['reason']}")
        print("-" * 60)


def main():
    parser = argparse.ArgumentParser(description="检索策略分类器交互 demo")
    parser.add_argument("--query", default=None)
    parser.add_argument("--event", default="")
    parser.add_argument("--themes", default="", help="逗号分隔")
    parser.add_argument("--target", default="")
    parser.add_argument("--time-scope", default="")
    args = parser.parse_args()

    clf = build_classifier()

    if args.query is not None:
        themes = [t.strip() for t in args.themes.split(",") if t.strip()] if args.themes else []
        payload = run_once(
            clf,
            query=args.query,
            event=args.event,
            themes=themes,
            target=args.target,
            time_scope=args.time_scope,
            session_topic="",
        )
        print(f"strategy   = {payload['strategy']}")
        print(f"confidence = {payload['confidence']}")
        print(f"reason     = {payload['reason']}")
        return 0

    try:
        interactive_mode(clf)
    except (KeyboardInterrupt, EOFError):
        print("\nbye")
    return 0


if __name__ == "__main__":
    sys.exit(main())
