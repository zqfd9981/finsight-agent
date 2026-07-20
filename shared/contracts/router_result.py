from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared.enums.follow_up_type import FollowUpType
from shared.enums.intent import Intent


@dataclass(slots=True)
class RouterResult:
    """V1 跨模块共享的路由结果契约对象。"""

    # 共享 contract 版本，V1 固定为 v1。
    version: str = "v1"
    # 当前问题被路由到的主意图类型。
    intent: str = Intent.OUT_OF_SCOPE.value
    # 当前轮次与历史轮次的关系，例如首轮、追问或重定向。
    follow_up_type: str = FollowUpType.NONE.value
    # 路由判断的置信度等级。
    confidence: str = "low"
    # 从用户问题中抽取出的核心语义实体。
    entities: dict[str, Any] = field(default_factory=dict)
    # SQL 约束字段（仅 metric_lookup 可能非空）：阈值筛选与 TopN 排序。
    # 经 constraint_resolver 校验后喂给 SQL 组装器；LLM 只产结构化字段，绝不拼 SQL。
    # 相对值比较（"比 xx 公司高"）无法用本结构表达，应由 Router 省略、下游自然语言兜底。
    filters: list[dict] = field(default_factory=list)
    ranking: dict | None = None
    # 后续规划和执行阶段需要调用的能力标签列表。
    needs: list[str] = field(default_factory=list)
    # 本轮执行的约束条件，例如时间范围或输出偏好。
    constraints: dict[str, Any] = field(default_factory=dict)
    # 预留的可选备注字段，不参与主路由决策。
    notes: str | None = None
    # 仅用于调试的补充元数据，下游不应依赖。
    debug_meta: dict[str, Any] = field(default_factory=dict)
