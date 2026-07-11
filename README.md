# FinSight V1

金融分析 AI Workbench。控制面三层架构 `router → classifier（仅 event 触发）→ orchestrator（查表 + 执行）`，支持 5 类 query：

| intent | 典型问题 | 链路 |
| --- | --- | --- |
| `metric_lookup` | 宁德时代 2024 年净利润 | `query_structured_data → synthesize_answer` |
| `general_finance_qa` | 降息对债市意味着什么 | `synthesize_answer`（LLM 直答） |
| `event_impact_analysis` | 红海局势升级利好哪些航运股 | 按 strategy 分叉，2-4 个 stage |
| `evidence_lookup` | 中远海能受益的依据是什么 | `retrieve_evidence → synthesize_answer` |
| `out_of_scope` | 推荐一只股票 | guardrail 短路 |

---

## 快速启动

### 1. 前置依赖

Python 3.10+，安装：

```bash
pip install fastapi 'uvicorn[standard]' streamlit requests PyYAML
```

### 2. 配置环境变量

LLM API key（必需，否则所有 LLM 调用会降级）：

```bash
# Windows
set AGICTO_API_KEY=<your_agicto_api_key>

# POSIX / Git Bash
export AGICTO_API_KEY=<your_agicto_api_key>
```

> 支持 `AGICTO_API_KEY` / `FINSIGHT_LLM_API_KEY` 任一环境变量。默认模型 `deepseek-v4-flash`（AGICTO OpenAI 兼容端点 `https://api.agicto.cn/v1`），可通过 `FINSIGHT_LLM_MODEL` 覆盖。

博查搜索 API key（可选，event_impact_analysis 需要）：

```bash
# Windows
set BOCHA_API_KEY=<your_key>

# POSIX / Git Bash
export BOCHA_API_KEY=<your_key>
```

> 未配置 BOCHA_API_KEY 时 `metric_lookup` / `general_finance_qa` / `evidence_lookup` 正常工作；`event_impact_analysis` 会降级到披露源 + 本地 RAG。

### 3. 启动工作台

**方式 A：一键启动（POSIX / Git Bash）**

```bash
./scripts/run_workbench.sh
```

先后台起后端 → 就绪检测 → 前台起前端，`Ctrl+C` 自动清理两个进程。

**方式 B：分两个终端**

终端 1（后端，默认 127.0.0.1:8000）：

```bash
# 跨平台 Python launcher
python scripts/run_workbench_backend.py

# 或 Windows native cmd
scripts\run_workbench_backend.cmd

# 开发期热重载
python scripts/run_workbench_backend.py --reload
```

终端 2（前端，默认 127.0.0.1:8501）：

```bash
# POSIX / Git Bash
./scripts/run_workbench_frontend.sh

# Windows native cmd
scripts\run_workbench_frontend.cmd
```

### 4. 访问

浏览器打开 <http://127.0.0.1:8501>，侧边栏三个视图：

- **分析视图**：填 query 点「运行分析」
- **调试视图**：查看 routing / stage execution / trace
- **评测视图**：批量回放事件评测样本

### 5. 试几条 demo

| 视图 | 输入 query | 预期 |
| --- | --- | --- |
| 分析视图 | `宁德时代 2024 年净利润是多少` | 走 metric_lookup，返回数值 |
| 分析视图 | `降息对债市意味着什么` | 走 general_finance_qa，LLM 直答 |
| 分析视图 | `红海局势升级对 A 股哪些板块有影响` | 走 event_impact_analysis（需 BOCHA_API_KEY） |

---

## 配置

端口与 base URL 在 [config/app.yaml](config/app.yaml) 的 `app.workbench` 段：

```yaml
app:
  workbench:
    backend_host: 127.0.0.1
    backend_port: 8000
    backend_base_url: http://127.0.0.1:8000
    frontend_host: 127.0.0.1
    frontend_port: 8501
```

改端口只需改这一处，前后端都读同一个配置。

---

## 故障排查

| 症状 | 对策 |
| --- | --- |
| 端口占用（`Errno 98` / `WinError 10048`） | 改 `config/app.yaml` 的 `backend_port` / `frontend_port`，或 `netstat -ano \| findstr :8000` 找占用进程 |
| `ModuleNotFoundError: No module named 'yaml'` | `pip install PyYAML` |
| 前端报 `backend POST ... failed` | 确认后端进程在跑；`curl http://127.0.0.1:8000/api/v1/eval/event-cases` 自检 |
| event 查询结果稀疏 / `bocha_used: false` | 检查 `BOCHA_API_KEY` 是否设置、配额是否耗尽；会自动降级到披露源 |
| Streamlit 页面空白 | 检查 `http://127.0.0.1:8501/_stcore/health` 是否 200 |

完整故障排查见 [docs/finsight/operations/workbench-runbook.md](docs/finsight/operations/workbench-runbook.md)。

---

## 运行测试

```bash
# 全量
python -m pytest tests/ -q

# 仅骨架守卫
python -m unittest tests.unit.test_project_skeleton -v

# 工作台可启动性
python -m unittest \
  tests.integration.test_backend_api_app \
  tests.integration.test_workbench_end_to_end \
  tests.integration.test_streamlit_workbench_smoke \
  tests.unit.test_project_skeleton \
  -v
```

---

## 项目结构

```
.
├── shared/                  # 跨工程共享 contracts 与 enums
├── backend/
│   ├── apps/api/            # FastAPI 入口
│   └── src/finsight_agent/
│       ├── control_plane/   # router / classifier / orchestrator（含 stage_planner）
│       ├── capabilities/    # structured_data / retrieval / reporting
│       ├── config/          # settings / feature_flags
│       └── infra/           # LLM client / 外部 API fetcher
├── frontend/
│   └── streamlit_app/       # 分析 / 调试 / 评测 三视图
├── config/app.yaml          # 端口与路径配置
├── scripts/                 # 启动脚本
├── tests/                   # unit + integration
├── openspec/                # specs + change proposals
└── docs/finsight/           # 项目状态与业务说明
```

控制面重构细节见 [REFACTOR_PLAN.md](REFACTOR_PLAN.md)，change proposal 见 [openspec/changes/2026-07-09-collapse-planner-and-synthesize-stages/](openspec/changes/2026-07-09-collapse-planner-and-synthesize-stages/)。
