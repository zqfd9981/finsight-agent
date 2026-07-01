from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from shared.contracts.session_context import SessionContext

from .models import SessionSnapshot


class SessionRepository:
    """基于本地 JSON 文件的最小 session snapshot repository。"""

    def __init__(self, storage_dir: str | Path = "runtime/session_state") -> None:
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def load(self, session_id: str) -> SessionSnapshot | None:
        snapshot_path = self._snapshot_path(session_id)
        if not snapshot_path.exists():
            return None

        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        context_payload = payload.get("context", {})

        return SessionSnapshot(
            session_id=payload["session_id"],
            last_query=payload["last_query"],
            last_query_mode=payload["last_query_mode"],
            last_intent=payload["last_intent"],
            last_follow_up_type=payload["last_follow_up_type"],
            last_plan_stages=list(payload.get("last_plan_stages", [])),
            context=SessionContext(**context_payload),
            updated_at=payload.get("updated_at", ""),
        )

    def save(self, snapshot: SessionSnapshot) -> None:
        snapshot_path = self._snapshot_path(snapshot.session_id)
        payload = asdict(snapshot)
        snapshot_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _snapshot_path(self, session_id: str) -> Path:
        return self._storage_dir / f"{session_id}.json"
