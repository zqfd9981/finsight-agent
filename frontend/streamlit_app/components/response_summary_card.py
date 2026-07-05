from __future__ import annotations

from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope


def build_response_summary_card_data(
    envelope: AnalysisResponseEnvelope,
) -> dict[str, object]:
    return {
        "response_type": envelope.response.response_type,
        "summary": getattr(envelope.response, "summary", ""),
        "session_id": envelope.session_id,
    }
