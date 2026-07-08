from __future__ import annotations

LABEL_TO_INDEX: dict[str, int] = {
    "event_primary": 0,
    "disclosure_primary": 1,
    "dual_primary": 2,
}

INDEX_TO_LABEL: dict[int, str] = {idx: label for label, idx in LABEL_TO_INDEX.items()}


def build_input_text(
    *,
    query: str,
) -> str:
    """Serialize query-only classifier input."""
    return f"[QUERY] {query}"
