## ADDED Requirements

### Requirement: 分析工作台必须可从工程根目录启动并联通后端

系统 MUST 提供从仓库根目录启动分析工作台的可执行入口，使后端 API 服务与 Streamlit 前端可以在本地同时运行，并通过稳定后端接口完成一次端到端分析请求。

#### Scenario: 操作员从仓库根目录启动工作台

- **WHEN** 操作员先后启动后端 API 服务（`python scripts/run_workbench_backend.py` 或等价 `uvicorn backend.apps.api.main:app`）以及 Streamlit 前端（`streamlit run frontend/streamlit_app/streamlit_entry.py` 或等价 `.sh/.cmd` 脚本）
- **THEN** 系统 MUST 在两个进程就绪后允许前端发起首轮分析请求，并通过既有 API boundary 接收到稳定的 response envelope

#### Scenario: 配置文件驱动后端与前端端口

- **WHEN** 操作员在 `config/app.yaml` 的 `app.workbench` 段调整 `backend_host` / `backend_port` / `backend_base_url` / `frontend_host` / `frontend_port` 后重新启动工作台
- **THEN** 系统 MUST 让后端与前端使用新配置值，并将前端构造的 API 请求发往 `backend_base_url`，而不是默认值或硬编码地址

#### Scenario: 工作台首轮分析请求失败时不能崩溃

- **WHEN** 工作台向后端提交首轮分析请求而后端返回 guardrail / 降级响应或 5xx 错误
- **THEN** 工作台 MUST 在不退出 Streamlit 进程的前提下展示稳定的错误态，并允许用户继续重试或切换页面

#### Scenario: 工作台切换页面后仍可回到分析结果

- **WHEN** 用户在「分析视图」得到一份 envelope 后切换到「调试视图」或「评测视图」
- **THEN** 系统 MUST 让最近一次 envelope 在 Streamlit 会话内可继续被「调试视图」消费，而无需重新运行分析
