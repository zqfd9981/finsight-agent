from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from shared.contracts.session_context import ConversationTurn, SessionContext

from .models import SessionSnapshot

# v2 新增字段，v1 JSON 中不存在，读取时补默认值
_V2_FIELDS_WITH_DEFAULTS = {
    "active_metrics": list,
    "active_time_scope": dict,
    "turns": list,
}


class SessionRepository:
    """基于本地 JSON 文件的 session snapshot repository（兼容 v1/v2）。"""

    def __init__(self, storage_dir: str | Path = "runtime/session_state") -> None:
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def load(self, session_id: str) -> SessionSnapshot | None:
        snapshot_path = self._snapshot_path(session_id)
        if not snapshot_path.exists():
            return None

        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        context_payload = payload.get("context", {})

        # v1→v2 兼容：补全缺失的 v2 字段
        context_payload = self._migrate_context_payload(context_payload)

        # turns 是 list[ConversationTurn]，需特殊处理
        turns_payload = context_payload.pop("turns", [])
        turns = [ConversationTurn(**t) for t in turns_payload if isinstance(t, dict)]

        context = SessionContext(**context_payload, turns=turns)

        return SessionSnapshot(
            session_id=payload["session_id"],
            last_query=payload["last_query"],
            last_query_mode=payload["last_query_mode"],
            last_intent=payload["last_intent"],
            last_follow_up_type=payload["last_follow_up_type"],
            last_plan_stages=list(payload.get("last_plan_stages", [])),
            context=context,
            updated_at=payload.get("updated_at", ""),
        )

    def save(self, snapshot: SessionSnapshot) -> None:
        snapshot_path = self._snapshot_path(snapshot.session_id)
        payload = asdict(snapshot)
        snapshot_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _migrate_context_payload(self, payload: dict) -> dict:
        """v1→v2 迁移：补全缺失的 v2 字段，标记版本号。"""
        migrated = dict(payload)
        for field_name, default_factory in _V2_FIELDS_WITH_DEFAULTS.items():
            if field_name not in migrated:
                migrated[field_name] = default_factory()
        # 升级版本号到 v2（仅当当前是 v1 或缺失时）
        if migrated.get("version", "v1") == "v1":
            migrated["version"] = "v2"
        return migrated

    def _snapshot_path(self, session_id: str) -> Path:
        return self._storage_dir / f"{session_id}.json"
