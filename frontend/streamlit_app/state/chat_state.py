"""Chat 视图的会话状态管理。

使用 ``st.session_state`` 维护多个会话（session）与每轮消息（message），
自动生成 session_id，无需用户手动粘贴。

st.session_state 结构：
    {
        "chat_sessions": {
            "sess_xxx": {
                "session_id": "sess_xxx",
                "title": "格力电器分析",
                "messages": [
                    {"role": "user", "content": "..."},
                    {"role": "assistant", "content": "...", "trace_blocks": [...]},
                ],
                "created_at": "...",
            },
        },
        "active_session_id": "sess_xxx",
    }
"""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

import streamlit as st

_CHAT_SESSIONS_KEY = "chat_sessions"
_ACTIVE_SESSION_KEY = "active_session_id"


def ensure_chat_state() -> None:
    """初始化 chat 状态（若未初始化）。"""
    if _CHAT_SESSIONS_KEY not in st.session_state:
        st.session_state[_CHAT_SESSIONS_KEY] = {}
    if _ACTIVE_SESSION_KEY not in st.session_state:
        st.session_state[_ACTIVE_SESSION_KEY] = ""


def list_sessions() -> list[dict[str, Any]]:
    """返回所有会话（按创建时间倒序）。"""
    ensure_chat_state()
    sessions = list(st.session_state[_CHAT_SESSIONS_KEY].values())
    sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return sessions


def get_active_session() -> dict[str, Any] | None:
    """返回当前活跃会话，无则返回 None。"""
    ensure_chat_state()
    active_id = st.session_state[_ACTIVE_SESSION_KEY]
    if not active_id:
        return None
    return st.session_state[_CHAT_SESSIONS_KEY].get(active_id)


def create_new_session() -> dict[str, Any]:
    """创建新会话，设为活跃，返回会话字典。"""
    ensure_chat_state()
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    new_session = {
        "session_id": session_id,
        "title": "新会话",
        "messages": [],
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
    }
    st.session_state[_CHAT_SESSIONS_KEY][session_id] = new_session
    st.session_state[_ACTIVE_SESSION_KEY] = session_id
    return new_session


def switch_to_session(session_id: str) -> None:
    """切换活跃会话。"""
    ensure_chat_state()
    if session_id in st.session_state[_CHAT_SESSIONS_KEY]:
        st.session_state[_ACTIVE_SESSION_KEY] = session_id


def delete_session(session_id: str) -> None:
    """删除指定会话。"""
    ensure_chat_state()
    if session_id in st.session_state[_CHAT_SESSIONS_KEY]:
        del st.session_state[_CHAT_SESSIONS_KEY][session_id]
    if st.session_state[_ACTIVE_SESSION_KEY] == session_id:
        st.session_state[_ACTIVE_SESSION_KEY] = ""


def append_user_message(session_id: str, content: str) -> None:
    """追加用户消息。"""
    ensure_chat_state()
    session = st.session_state[_CHAT_SESSIONS_KEY].get(session_id)
    if session is None:
        return
    session["messages"].append({"role": "user", "content": content})
    # 首条用户消息作为会话标题
    if session["title"] == "新会话":
        session["title"] = content[:20] + ("..." if len(content) > 20 else "")


def append_assistant_message(
    session_id: str,
    content: str,
    trace_blocks: list[Any] | None = None,
    session_id_from_backend: str | None = None,
    evidence_index: dict[str, Any] | None = None,
) -> None:
    """追加 assistant 消息（含 trace_blocks 与 evidence_index）。"""
    ensure_chat_state()
    session = st.session_state[_CHAT_SESSIONS_KEY].get(session_id)
    if session is None:
        return
    session["messages"].append({
        "role": "assistant",
        "content": content,
        "trace_blocks": trace_blocks or [],
        "evidence_index": evidence_index or {},
    })
    # 后端可能返回新的 session_id（首次查询时后端生成）
    if session_id_from_backend and session_id_from_backend != session_id:
        # 迁移会话到新 session_id
        session["session_id"] = session_id_from_backend
        st.session_state[_CHAT_SESSIONS_KEY][session_id_from_backend] = session
        del st.session_state[_CHAT_SESSIONS_KEY][session_id]
        st.session_state[_ACTIVE_SESSION_KEY] = session_id_from_backend
