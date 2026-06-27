"""FinSight Agent V1 的工作台入口骨架。"""

from frontend.streamlit_app.api_client import WorkbenchApiClient


# 当前阶段只冻结工作台通过统一 API client 构造请求的方式。
APP_ENTRY_DESCRIPTION = "Streamlit workbench placeholder for FinSight Agent V1."


def main() -> dict[str, object]:
    """返回入口说明和默认请求示例，供骨架阶段校验。"""
    client = WorkbenchApiClient()
    request = client.build_request(query="宁德时代 2024 年净利润是多少？")
    return {
        "description": APP_ENTRY_DESCRIPTION,
        "endpoint_path": client.endpoint_path,
        "default_query_mode": request.query_mode,
    }
