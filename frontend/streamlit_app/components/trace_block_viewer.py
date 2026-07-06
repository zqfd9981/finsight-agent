from __future__ import annotations

from shared.contracts.trace_block import TraceBlock


def build_trace_block_data(block: TraceBlock) -> dict[str, object]:
    return {
        "block_type": block.block_type,
        "title": block.title,
        "status": block.status,
        "payload_summary": dict(block.payload_summary),
        "raw_refs": list(block.raw_refs),
    }
