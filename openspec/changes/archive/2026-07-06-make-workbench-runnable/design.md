## Context

FinSight Agent V1 在分支 `feat/phase1-project-runnable` 上累积了下述资产，但当前没有任何可启动入口：

- 后端 `WorkbenchBackendApiService.build_response()`（[backend/src/finsight_agent/workbench_backend_api/service.py:29](backend/src/finsight_agent/workbench_backend_api/service.py#L29)）已经能完整串起 `RouterService` → `PlannerService` → `OrchestratorService` → `SessionService`，输出 `AnalysisResponseEnvelope`
- 后端 `backend/apps/api/analysis_turns.py` 与 `event_eval.py` 各自有 `handle_*` 纯函数，但 `backend/apps/api/main.py` 只暴露路由元数据 dict（[backend/apps/api/main.py:11-17](backend/apps/api/main.py#L11) 的注释明确写"不接入真实 FastAPI 实例"）
- 前端三页 Streamlit 的 view-model 纯函数（`build_*_view_model`）已稳定，组件 builder 也已稳定，但 page 文件没有任何 `st.*` 调用
- 前端 `frontend/streamlit_app/api_client.py` 只有 `parse_*` 方法，没有 `requests.post`
- `scripts/` 下没有任何 launcher；`config/app.yaml` 没有任何 host/port/url 键

`openspec/changes/archive/2026-06-27-formalize-workbench-backend-api-boundary/` 第 3.1 节早已提出"补 FastAPI 端点骨架"作为 planned-but-not-executed 任务，本次 change 把这一意图落实为代码并扩展到让 Streamlit 工作台真正可启动。

## Goals / Non-Goals

**Goals:**

- 在 `backend/apps/api/` 下提供 FastAPI app factory `build_app()`，挂载 3 条路由（`POST /api/v1/analysis/turns`、`GET /api/v1/eval/event-cases`、`POST /api/v1/eval/event-replay`），并保留 dev 环境 CORS
- 在 `frontend/streamlit_app/` 下提供被 `streamlit run` 调用的入口脚本，并让三页各自拥有 `render_*` 薄壳
- 提供跨平台 launcher 脚本（`.py` + `.sh` + `.cmd`），让操作员在仓库根目录用 2 条命令就能拉起工作台
- 提供 `config/app.yaml` 配置解析（`app.workbench` 段），让前端从配置读取 `backend_base_url`，避免硬编码
- 提供基于 `fastapi.testclient.TestClient` 的三路由集成测试 + 基于 subprocess + `urllib.request` 的端到端 smoke 测试
- 把"工作台可启动"和"后端 base URL 可配置"两条 Requirement 显式写入既有 capability spec，作为可被验收的合约

**Non-Goals:**

- 不引入 `streamlit-autorefresh`、`streamlit-echarts` 等额外 UI 库
- 不为 `event_impact_analysis` 真实查询做 GDELT 429 容错（属于稳定性优化 follow-up）
- 不引入 `Redis` / `memcached` 等外部缓存层
- 不引入 `streamlit.testing.v1.AppTest`（如未来要做渲染层单测，再单独 add）
- 不引入 `Makefile` / `pyproject.toml`（保持纯脚本启动风格）
- 不修改 `shared-analysis-contracts/spec.md`（contract 形状本 change 不变）

## Decisions

### D1. FastAPI lifespan vs 懒构造

**Decision**：handler 内部懒构造 `WorkbenchBackendApiService` 实例，不使用 lifespan 预热。

**Rationale**：`WorkbenchBackendApiService` 默认构造时通过 `RouterService()` / `PlannerService()` / `OrchestratorService()` / `SessionService()` 实例化依赖；进一步往下 `OrchestratorService()` 默认装配 `DualSourceExternalContextRetriever`，而后者**首次真实查询会触碰 GDELT / CNInfo**。如果改用 lifespan 预热，应用启动的瞬间就会发外部网络请求，违反"启动快速、行为可观察"原则。

**Alternatives considered**：
- *Lifespan 预热（reject）*：启动期就发外部网络请求，且让 `uvicorn backend.apps.api.main:app` 的可观察性变差
- *进程级单例 + 显式 init（reject）*：需要新引入 `lru_cache` 或全局变量，超出本 change 的最小目标

### D2. CORS 配置

**Decision**：dev 环境显式 `allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"]`，`allow_credentials=False`，methods 限制为 `GET, POST`。

**Rationale**：Streamlit 默认 8501，后端默认 8000，跨端口 XHR 必须 CORS。`*` 通配在 `allow_credentials=True` 时被浏览器拒绝；本 workbench 不需要 cookie，凭据关掉即可接受显式列表。

**Alternatives considered**：
- *`*` 通配（reject）*：当未来误设 `allow_credentials=True` 会立即出安全告警
- *手工 CORS 中间件（reject）*：超出本 change 的最小目标

### D3. Streamlit 读 YAML 时机

**Decision**：`config_resolver.resolve_workbench_config()` 在 `WorkbenchApiClient.__init__` 内首次调用时读取，模块 import 期不读。

**Rationale**：`streamlit_entry.py` 顶层有 `bootstrap_streamlit_app()`，被 import 时不应强制 `config/app.yaml` 存在，否则会破坏既有"无需 YAML 也能做 smoke"的测试模式。`WorkbenchApiClient.__init__` 内部懒读等价于"首次构造时读"——对一次进程只多付出一次 `yaml.safe_load` 的代价。

**Alternatives considered**：
- *`@st.cache_resource` 包一层（reject）*：超出本 change 的最小目标
- *`streamlit_entry.py` 顶层读（reject）*：`import streamlit_entry` 时硬要求配置文件存在，会破坏既有测试

### D4. `app.yaml` mode 键设计

**Decision**：在已有 `app.mode: skeleton` 旁并列追加 `app.workbench.mode: runnable` + host/port/base_url 块。

**Rationale**：`app.mode: skeleton` 在历史文档与既有测试语义中表示"项目交付阶段"；workbench 的"可运行"状态属于运行期/部署期姿态。两者正交，可同时存在，不需要修改 `app.mode`。

**Alternatives considered**：
- *改 `app.mode: skeleton → runnable`（reject）*：会让所有引用旧语义的项目状态文档 / 测试一起被改名，引入回归

### D5. E2E smoke 端口分配

**Decision**：用 `socket.bind((127.0.0.1, 0))` 让内核分配空闲端口，再 `subprocess.Popen(["uvicorn", ..., "--port", str(port)])` 钉死；用 `urllib.request` 在 15 s 内 poll `/api/v1/eval/event-cases` 直到 200。

**Rationale**：OS 内核分配 zero-port 比扫描端口可靠得多；`/api/v1/eval/event-cases` 是一条纯本地 fixture 读取路径，**不会触发 GDELT**，保证测试稳定且快速。Windows 下用 `proc.terminate()` 优雅退出兜底 `proc.kill()`；POSIX 下用 `proc.send_signal(SIGINT)`。

**Alternatives considered**：
- *固定 8000 端口（reject）*：与开发人员本机已运行的其他 uvicorn 进程冲突
- *走 `TestClient` 取代 subprocess（reject 部分成立）*：TestClient 验证 in-process 行为是必要的，但**不能替代真实进程 smoke**，因此保留两种

### D6. 运行脚本跨平台策略

**Decision**：`scripts/run_workbench_backend.py` 作为跨平台规范入口（POSIX 与 Windows 都用 Python 调 `uvicorn.run`），外加 `.sh`（Git Bash / POSIX shell）和 `.cmd`（Windows native cmd）作为操作员便利的双格式 launcher；同时给出 `scripts/run_workbench.sh` 一键起后端+前端。

**Rationale**：仓库当前已经用 Git Bash by default，但 CI 可能在 Linux / macOS / Windows 任一环境跑；同时给两种 shell 格式 + 一个统一 Python launcher，可以让任何操作者不感知 Python 细节就能用。

**Alternatives considered**：
- *只给 Python launcher（reject）*：失去操作员便利
- *只给 `.sh`（reject）*：Windows cmd 用户无法用

### D7. API client 错误处理

**Decision**：非 2xx 响应统一抛 `RuntimeError`，把 status code 与 response body 串联到错误消息里。Streamlit render 层用 `try/except RuntimeError as exc: st.error(...)` 兜住。

**Rationale**：`requests.raise_for_status()` 会抛 `requests.HTTPError`，会引入前端对 `requests` 异常类的依赖；统一抛 `RuntimeError` 让前端只要 `except Exception` 或 `except RuntimeError` 即可。

### D8. 渲染层与 view-model 分离

**Decision**：保留 `pages/*.py` 里的 `build_*_view_model` 纯函数；新增 `render_*_view(...)` 薄壳**并列存在**，壳内调既有 view-model + `st.*`。`build_*` 不改。

**Rationale**：既有单测断言的是 `build_*` 的输出，新加的 `render_*` 改变不会让旧单测红掉；`render_*` 用 Streamlit 已经有的 session_state + state helpers，不破坏 [tests/unit/test_project_skeleton.py:184-198](tests/unit/test_project_skeleton.py#L184) 的"frontend 不能 import backend internals"守卫。

## Risks / Trade-offs

- **[R1] GDELT 429 on 真实 event_impact_analysis 查询** → E2E smoke 只打 `GET /api/v1/eval/event-cases`（无外部网络）；runbook 显式标注"首次真实事件查询可能失败"；下一 change 把缓存/超时/降级补齐。
- **[R2] Streamlit rerun 语义重建单例** → `WorkbenchApiClient.__init__` 保持零 I/O（除懒读 YAML 外），纯客户端状态用 `st.session_state`；`api_client.py` 不缓存任何跨 rerun 的对象。
- **[R3] `set_page_config` 必须是首个 `st.*` 调用** → 写在 `bootstrap_streamlit_app()` 函数体首行；page render 文件只在函数体内 `import streamlit as st`，避免顶层 `st.*` 调用污染 import 顺序。
- **[R4] Windows 下 `send_signal(SIGINT)` 抛 `ValueError`** → 测试代码用 `if sys.platform == "win32": proc.terminate()` 否则 `proc.send_signal(SIGINT)`；5 s `wait()` 后兜底 `proc.kill()`。
- **[R5] `requests` 长分析超时** → `WorkbenchApiClient` 默认 `timeout_seconds=120.0`；runbook 注明，后续稳定性 change 可以进一步细化超时分级。
- **[R6] YAML 键漂移** → `config_resolver` 写死只读 `config/app.yaml`；runbook 注明唯一可改位置；Task 5 加 `test_workbench_runnable_artifacts_exist` 钉死关键文件路径，**不**加 yaml-key-shape 测试（太脆弱）。
- **[R7] Permissive CORS 在非本地部署下风险** → `app_factory.py` 顶部注释"上线前必须收窄 CORS origins"；dev 默认 `8501` 与 `localhost`。
- **[R8] 测试隔离：subprocess uvicorn stderr 缓冲满会死锁** → 测试用 `stdout=PIPE, stderr=PIPE` 配合 `try/finally + communicate(timeout=...)`，或者退而求其次用 `DEVNULL`。
- **[R9] 前期计划 `hao#` 文档噪声** → 本 change 在 doc 同步阶段顺手修掉 [docs/superpowers/plans/2026-07-05-streamlit-debug-eval-workbench.md:1](docs/superpowers/plans/2026-07-05-streamlit-debug-eval-workbench.md#L1)，限制 diff 只在 line 1。
- **[R10] PyYAML 未声明依赖** → 运行期 streamlit/python launcher 都假定环境已装 `PyYAML`；如果未装，runbook 顶部给出 `pip install PyYAML` 兜底；本 change **不**引入 `requirements.txt`（仓库历史惯例）。

## Migration Plan

- 本 change 是工程内"骨架 → 可运行"，不涉及线上数据迁移
- 仓库现有 smoke 测试（`tests/unit/test_project_skeleton.py`、`tests/unit/test_streamlit_*.py` 等）必须继续通过
- 任何"feature flag" / "legacy mode" 都不需要——旧的纯 metadata 调用路径会被替换，但没有外部消费者依赖旧路径，所以无需 transitional shim

## Open Questions

- 是否要在 `scripts/run_workbench.sh` 默认走 `--reload` 让开发期后端热重载？**倾向默认不 reload**，让操作员自己 `--reload` 显式开启，避免 dev 数据库路径被意外重置。
- FastAPI 是否要加 `/healthz` 接口？**本 change 不加**，让健康检查由 `GET /api/v1/eval/event-cases` 一个现成路径充当，避免新增路径。
