from __future__ import annotations

from typing import Protocol


class ExternalMetricProvider(Protocol):
    """外部指标提供方的最小抽象接口。"""

    def lookup_metric(
        self,
        company_name: str,
        metric_name: str,
        time_scope: str,
    ) -> dict[str, object] | None: ...


class NullExternalMetricProvider:
    """默认外部 provider，占位但不访问网络。"""

    def lookup_metric(
        self,
        company_name: str,
        metric_name: str,
        time_scope: str,
    ) -> dict[str, object] | None:
        return None
