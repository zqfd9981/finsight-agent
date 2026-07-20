"""最小实证：LangGraph 中无 reducer 的 list 字段，靠节点返回「完整累积列表」能否跨节点累积。

复刻 graph.py 的 _append_observation 模式：每个节点返回 list(state['stage_observations']) + [new]。
若最终只有 1 个 → 累积失败（list 被覆盖）；若 2 个 → 累积成功。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for c in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(c) not in sys.path:
        sys.path.insert(0, str(c))

from typing import TypedDict

from langgraph.graph import END, StateGraph

from shared.contracts.stage_observation import StageObservation


class MiniState(TypedDict, total=False):
    stage_observations: list


def _make_obs(name: str) -> StageObservation:
    return StageObservation(
        observation_id=f"obs_{name}",
        stage_name=name,
        status="success",
        key_outputs={},
        evidence_refs=[],
    )


def node1(state: MiniState) -> dict:
    return {
        "stage_observations": list(state.get("stage_observations", []) or [])
        + [_make_obs("a")]
    }


def node2(state: MiniState) -> dict:
    return {
        "stage_observations": list(state.get("stage_observations", []) or [])
        + [_make_obs("b")]
    }


def run() -> None:
    g = StateGraph(MiniState)
    g.add_node("n1", node1)
    g.add_node("n2", node2)
    g.set_entry_point("n1")
    g.add_edge("n1", "n2")
    g.add_edge("n2", END)
    app = g.compile()
    result = app.invoke({"stage_observations": []})
    obs = result.get("stage_observations", [])
    print(f"OBS_COUNT={len(obs)}")
    print(f"OBS_NAMES={[o.stage_name for o in obs]}")
    assert len(obs) == 2, f"累积失败！只得到 {len(obs)} 个观察"
    print("PASS: LangGraph 无 reducer list 字段可跨节点累积")


if __name__ == "__main__":
    run()
