# FinSight V1 工作台启动手册

> 适用 change：`make-workbench-runnable`（首版）
> 分支：`feat/phase1-project-runnable`

本文档面向操作员，让你在仓库根目录用两条命令把工作台拉起来，并对常见故障给出对策。

---

## 1. 前置条件

- Python 3.10+
- 已安装并能 import：
  - `fastapi`
  - `uvicorn`
  - `streamlit`
  - `requests`
  - `PyYAML`（用于 `config_resolver` 解析 `config/app.yaml`）
- 当前 shell 能访问同一个 `python` 解释器（Windows 下 Git Bash / native cmd 均可）
- 后端与前端端口（默认 8000 / 8501）未被其它进程占用

如果 `PyYAML` 未装：

```bash
pip install PyYAML
```

如果想从零准备：

```bash
pip install fastapi 'uvicorn[standard]' streamlit requests PyYAML
```

---

## 2. 启动后端

### 2.1 跨平台规范入口（Python launcher）

```bash
python scripts/run_workbench_backend.py
```

可选参数：

- `--reload`：开发期热重载，源码改动自动重启 uvicorn。

后端默认监听 `127.0.0.1:8000`，可通过 `config/app.yaml` 中 `app.workbench.backend_host` / `backend_port` 调整。

### 2.2 Windows native cmd

```cmd
scripts\run_workbench_backend.cmd
scripts\run_workbench_backend.cmd --reload
```

### 2.3 一键起后端 + 前端（POSIX / Git Bash）

```bash
./scripts/run_workbench.sh
```

该脚本先后端（后台）→ poll `/api/v1/eval/event-cases` 就绪 → 前端（前台）；Ctrl+C 会自动清理后端。

---

## 3. 启动前端

单独启动前端（你需要另一个终端里同时跑着后端）：

### 3.1 POSIX / Git Bash

```bash
./scripts/run_workbench_frontend.sh
```

### 3.2 Windows native cmd

```cmd
scripts\run_workbench_frontend.cmd
```

前端默认监听 `127.0.0.1:8501`，可通过 `config/app.yaml` 中 `app.workbench.frontend_host` / `frontend_port` 调整。

浏览器访问 <http://127.0.0.1:8501>：

- 侧边栏有「分析视图 / 调试视图 / 评测视图」三个页面
- 「分析视图」可填 query、session_id（追问时）、include_trace，点「运行分析」调后端
- 「调试视图」展示最近一次 envelope 的 routing / planning / execution 分段
- 「评测视图」点「刷新样本列表」可加载事件评测 fixture，多选后「运行 replay」批量查看

---

## 4. 配置项速查

`config/app.yaml` 内 `app.workbench` 段：

```yaml
app:
  workbench:
    mode: runnable
    backend_host: 127.0.0.1
    backend_port: 8000
    backend_base_url: http://127.0.0.1:8000
    frontend_host: 127.0.0.1
    frontend_port: 8501
```

- 缺省回落：若 `app.workbench` 整段不存在，配置解析器回落到本地开发默认 `http://127.0.0.1:8000`。
- 客户端 base URL 改一处即可：修改 `backend_base_url`，无需改前端代码。

---

## 5. 故障排查

### 5.1 端口已占用

**症状**：`uvicorn` 启动时报 `OSError: [Errno 98] Address already in use`（POSIX）或 `WinError 10048`（Windows）。

**对策**：

- 修改 `config/app.yaml` 的 `backend_port` / `frontend_port`
- 或找到占用进程：`netstat -ano | findstr :8000`（Win）/ `lsof -i :8000`（POSIX）
- 或停掉占用方

### 5.2 真实 event_impact_analysis 查询失败 / GDELT 429

**症状**：在「分析视图」发起 `event_impact_analysis` 相关查询后，看到下游错误或长时间卡住。

**原因**：当前 change **未**为外部检索加超时 / 缓存 / 降级。GDELT 公共接口可能因频率限制返回 429。

**对策**：

- 这是已知遗留，参见 [`openspec/changes/make-workbench-runnable/design.md`](../../changes/make-workbench-runnable/design.md) R1
- 推荐下一份 change：补 FastAPI 端超时 + GDELT 缓存 + fallback
- 临时绕路：先在「分析视图」跑 metric_lookup / evidence_lookup 类问题（不触发事件检索）

### 5.3 前端报 `RuntimeError: backend POST ... failed`

**症状**：Streamlit 主区域显示 `后端请求失败：backend POST /api/v1/analysis/turns failed: ...`。

**对策**：

- 确认后端进程仍在跑（另一终端里没死）
- 确认 `config/app.yaml` 中 `app.workbench.backend_base_url` 与实际后端端口一致
- 直接 curl 一次自检：

  ```bash
  curl http://127.0.0.1:8000/api/v1/eval/event-cases
  ```

### 5.4 `import yaml` 失败 / `PyYAML` 未装

**症状**：启动后端或前端时 `ModuleNotFoundError: No module named 'yaml'`。

**对策**：`pip install PyYAML` 后重试。

### 5.5 Streamlit 启动后页面空白 / 一直转圈

**对策**：

- 浏览器开发者工具看 network，`http://127.0.0.1:8501/_stcore/health` 是否 200
- 前端进程是否仍在跑
- `--server.headless true` 已默认开启；如果改回 `false` 且无浏览器环境会卡住

### 5.6 Windows 上 uvicorn accept 抖动

**症状**：在 Windows 上 `uvicorn` 启动后偶发 `WinError 64`（asyncio ProactorEventLoop 已知问题），HTTP 请求短时间不可达。

**对策**：

- 重试前端请求通常即可恢复
- 长期方案：上 `SelectorEventLoop`（不在本 change 范围）

---

## 6. 优雅停止

- 前台进程直接 `Ctrl+C`
- `run_workbench.sh` 通过 `trap 'kill $BACKEND_PID' EXIT` 自动回收后端子进程
- 手动 kill：先在前端终端 Ctrl+C，再在后端终端 Ctrl+C（POSIX）；Windows 用 `Ctrl+Break` 或任务管理器终止

---

## 7. 与自动化测试的关系

下面三组测试守护着本文档覆盖的"可启动"承诺：

- `tests/integration/test_backend_api_app.py`：用 `fastapi.testclient.TestClient` 在进程内跑通 3 条路由 + 缺 query 422
- `tests/integration/test_workbench_end_to_end.py`：subprocess 跑 uvicorn 等 3s 不死 + `scripts/run_workbench_backend.py --help` 正常退出
- `tests/unit/test_project_skeleton.py::test_workbench_runnable_artifacts_exist`：钉死本 runbook 与各启动脚本的存在

跑全部：

```bash
python -m unittest \
  tests.integration.test_backend_api_app \
  tests.integration.test_workbench_end_to_end \
  tests.integration.test_streamlit_workbench_smoke \
  tests.unit.test_project_skeleton \
  -v
```
