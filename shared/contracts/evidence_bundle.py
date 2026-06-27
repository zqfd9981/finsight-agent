from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EvidenceBundle:
    """V1 跨模块共享的证据包契约对象。"""

    # 共享 contract 版本，V1 固定为 v1。
    version: str = "v1"
    # 当前证据包的唯一标识。
    bundle_id: str = ""
    # 被验证对象的引用标识，例如公司名或候选对象 ID。
    target_ref: str = ""
    # 当前证据包试图支持或验证的判断语句。
    claim: str = ""
    # 证据支持强度，反映当前 claim 的可信度。
    support_strength: str = "weak"
    # 证据条目列表，每项通常包含来源、摘录和父引用等信息。
    evidence_items: list[dict[str, Any]] = field(default_factory=list)
    # 检索过程的补充说明，例如召回数量或命中情况。
    retrieval_notes: dict[str, Any] = field(default_factory=dict)
    # 预留的可选备注字段，不参与核心证据判断。
    notes: str | None = None
