## Why

V1 后端 `WorkbenchBackendApiService` 已经能完整产出 `AnalysisResponseEnvelope`，前端三页 Streamlit 骨架的 view-model 也都已稳定，但当前仓库无法被任何人在本地真正启动运行：`backend/apps/api/main.py` 只暴露路由元数据 dict（注释明确写"不接入真实 FastAPI 实例"），`frontend/streamlit_app/app.py` 同样只是元数据入口，三个 page 文件都没有 `st.*` 调用，`api_client.py` 也没有 `requests.post`，并且 `scripts/` 下没有任何启动脚本、`config/app.yaml` 里也没有 host/port/url 配置。本 change 已经在分支 `feat/phase1-project-runnable` 上悬而未决，正是为了让"项目能本地一键启动"这一首要目标闭环。

## What Changes

- 新增 [backend/apps/api/app_factory.py](backend/apps/api/app_factory.py)：FastAPI app factory `build_app()`，挂载既有的 `handle_analysis_turn` / `handle_event_cases` / `handle_event_replay` 三个 handler，并附 dev 环境 CORS（来源仅限 `localhost:8501` 与 `127.0.0.1:8501`）。
- 修改 [backend/apps/api/main.py](backend/apps/api/main.py)：保留既有 `main()` dict 元数据以兼容旧 smoke 测试，再追加 `app = build_app()` 让 `uvicorn backend.apps.api.main:app` 起得来。
- 新增 [frontend/streamlit_app/streamlit_entry.py](frontend/streamlit_app/streamlit_entry.py)：被 `streamlit run` 直接调用的入口，组装 `st.set_page_config` + 侧边栏页面切换 + 调用三个 `render_*`。
- 修改 [frontend/streamlit_app/api_client.py](frontend/streamlit_app/api_client.py)：新增 `send_request` / `fetch_event_cases` / `fetch_event_replay` 三个 `requests` 调用；构造时若未传 `backend_base_url` 则从 `config_resolver` 读取。
- 新增 [frontend/streamlit_app/config_resolver.py](frontend/streamlit_app/config_resolver.py)：从 `config/app.yaml` 解析 `app.workbench` 段，含缺省回退。
- 修改 [config/app.yaml](config/app.yaml)：追加 `app.workbench` 块（mode / backend_host / backend_port / backend_base_url / frontend_host / frontend_port）。
- 修改 [frontend/streamlit_app/pages/analysis_view.py](frontend/streamlit_app/pages/analysis_view.py) / [debug_view.py](frontend/streamlit_app/pages/debug_view.py) / [eval_view.py](frontend/streamlit_app/pages/eval_view.py)：每个文件**追加**一个 `render_*` 薄壳，调既有 `build_*_view_model` 并调用 `st.*`。
- 新增 [scripts/run_workbench_backend.py](scripts/run_workbench_backend.py)：跨平台 Python uvicorn launcher；新增 [scripts/run_workbench_frontend.sh](scripts/run_workbench_frontend.sh) 与 [scripts/run_workbench_backend.sh](scripts/run_workbench_backend.sh)（POSIX / Git Bash），以及对应的 [run_workbench_frontend.cmd](scripts/run_workbench_frontend.cmd) 与 [run_workbench_backend.cmd](scripts/run_workbench_backend.cmd)（Windows native cmd）。
- 新增 [tests/integration/test_backend_api_app.py](tests/integration/test_backend_api_app.py)：基于 `fastapi.testclient.TestClient` 的三路由集成测试。
- 新增 [tests/integration/test_workbench_end_to_end.py](tests/integration/test_workbench_end_to_end.py)：subprocess 启 uvicorn（free-port）+ `urllib.request` GET `/api/v1/eval/event-cases` smoke。
- 修改 [tests/integration/test_streamlit_workbench_smoke.py](tests/integration/test_streamlit_workbench_smoke.py)：追加 `streamlit_entry` 导入可达性 + 三页 render 函数存在性断言。
- 新增 [tests/unit/test_streamlit_config_resolver.py](tests/unit/test_streamlit_config_resolver.py) 以及在 [tests/unit/test_streamlit_api_client.py](tests/unit/test_streamlit_api_client.py) 追加 HTTP send 测试（mock `requests.post`）。
- 修改 [tests/unit/test_project_skeleton.py](tests/unit/test_project_skeleton.py)：在 `test_minimal_fast_path_files_exist` 列表追加本 change 新增的关键文件，钉死资产；并新增 `test_workbench_runnable_artifacts_exist` 子测试。
- 新增 [docs/finsight/operations/workbench-runbook.md](docs/finsight/operations/workbench-runbook.md)：启动手册 + 故障排查。
- 修改 [docs/finsight/project-status.md](docs/finsight/project-status.md)：追加 M9 "Workbench Runnable" 里程碑。
- 修改 [docs/finsight/modules/control-plane-status.md](docs/finsight/modules/control-plane-status.md) 与 [docs/finsight/modules/presentation-eval-status.md](docs/finsight/modules/presentation-eval-status.md)：各自加一段"可启动状态"引用 runbook。
- 修改 [docs/superpowers/plans/2026-07-05-streamlit-debug-eval-workbench.md](docs/superpowers/plans/2026-07-05-streamlit-debug-eval-workbench.md)：line 1 输入噪音 `hao#` 修回 `#`。

## Capabilities

### New Capabilities

<!-- 本 change 不新增 capability。可启动与 base URL 配置语义归属既有 capability。 -->

### Modified Capabilities

- `analysis-workbench`: 增加 Requirement "分析工作台必须可从工程根目录启动并联通后端"，覆盖后端 + 前端同进程共存、首轮请求可联通后端、失败不崩溃三项 Scenario。
- `workbench-backend-api-boundary`: 增加 Requirement "后端 API base URL 必须可由前端从配置读取"，覆盖客户端从 `app.workbench.backend_base_url` 读取、缺失回落、以及显式报告配置不可用三项 Scenario。

## Impact

- 受影响 spec：
  - `openspec/specs/analysis-workbench/spec.md`（MODIFIED，加 1 Requirement / 3 Scenarios）
  - `openspec/specs/workbench-backend-api-boundary/spec.md`（MODIFIED，加 1 Requirement / 3 Scenarios）
  - `openspec/specs/shared-analysis-contracts/spec.md` **不变**（contract 形状本 change 不动）
- 受影响代码骨架：
  - `backend/apps/api/`（新增 `app_factory.py`，改造 `main.py`，handler 函数原样复用）
  - `frontend/streamlit_app/`（新增 `streamlit_entry.py` / `config_resolver.py`，扩展 `api_client.py`，pages 下追加 render 薄壳）
  - `config/app.yaml`（追加 `app.workbench` 段）
  - `scripts/`（新增 5 个 launcher：`run_workbench_backend.py` + 双格式前后端 + 一键脚本）
- 受影响联调资产：
  - `tests/integration/`（新增 2 个 + 扩展 1 个）
  - `tests/unit/`（新增 1 个 + 扩展 2 个）
  - `docs/finsight/operations/`（新增 runbook）
  - `docs/finsight/project-status.md` + 两个 module status（同步进度）
- 外部依赖：
  - 复用现有 env 已装的 `fastapi 0.135.2` / `streamlit 1.57.0` / `requests 2.32.5` / `uvicorn 0.42.0`
  - 新增 `PyYAML` 作为 `config_resolver` 的解析依赖（用于解析 `app.yaml`；如环境未装则需在 runbook 中标注 `pip install PyYAML`）
- 风险已知项：
  - 真实 `event_impact_analysis` 查询会触发 GDELT 429；E2E smoke 不打真实分析路径，只验 `GET /api/v1/eval/event-cases`，以保证测试稳定
  - 跨平台启动：脚本同时提供 POSIX sh 与 Windows cmd，Python launcher 作为规范入口
