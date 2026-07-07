"""FinSight Agent V1 的 Streamlit 工作台入口。"""

from frontend.streamlit_app.api_client import WorkbenchApiClient


APP_ENTRY_DESCRIPTION = "Streamlit debug/eval workbench for FinSight Agent V1."


def get_registered_pages() -> list[str]:
    return ["分析视图", "调试视图", "评测视图"]


def main() -> dict[str, object]:
    client = WorkbenchApiClient()
    request = client.build_request(query="宁德时代 2024 年净利润是多少？")
    return {
        "description": APP_ENTRY_DESCRIPTION,
        "endpoint_path": client.endpoint_path,
        "default_query_mode": request.query_mode,
        "pages": get_registered_pages(),
    }
