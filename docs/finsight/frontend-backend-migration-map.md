# 前后端骨架迁移映射说明

日期：2026-06-27  
用途：为 `formalize-frontend-backend-architecture` change 提供目录映射、首批迁移范围和边界检查依据

## 1. 当前目录到目标目录的映射

| 当前路径 | 目标路径 | 说明 |
| --- | --- | --- |
| `apps/api/` | `backend/apps/api/` | 后端 API 入口壳整体前移到 `backend/` 工程 |
| `apps/workbench/` | `frontend/streamlit_app/` | V1 Streamlit 工作台入口转入前端工程 |
| `src/finsight_agent/control_plane/` | `backend/src/finsight_agent/control_plane/` | 后端控制面直接平移 |
| `src/finsight_agent/capabilities/` | `backend/src/finsight_agent/capabilities/` | 后端能力层直接平移 |
| `src/finsight_agent/evaluation/` | `backend/src/finsight_agent/evaluation/` | 评测相关代码保留在后端工程 |
| `src/finsight_agent/infra/` | `backend/src/finsight_agent/infra/` | 基础设施适配层直接平移 |
| `src/finsight_agent/config/` | `backend/src/finsight_agent/config/` | 代码内配置读取壳直接平移 |
| `src/finsight_agent/shared/contracts/` | `shared/contracts/` | 升级为跨工程共享 contract |
| `src/finsight_agent/shared/enums/` | `shared/enums/` | 升级为跨工程共享 enum |
| `src/finsight_agent/workbench/pages/` | `frontend/streamlit_app/pages/` | UI 占位目录随前端工程迁移 |
| `src/finsight_agent/workbench/components/` | `frontend/streamlit_app/components/` | UI 占位目录随前端工程迁移 |
| `src/finsight_agent/workbench/state/` | `frontend/streamlit_app/state/` | UI 状态占位目录随前端工程迁移 |

## 2. 第一批迁移到 shared 的对象

当前第一批直接迁移到顶层 `shared/` 的对象如下：

### 2.1 contracts

- `RouterResult`
- `Plan`
- `SessionContext`
- `StageObservation`
- `EvidenceBundle`
- `FinalResponse`
- `TraceBlock`
- `GuardrailOrErrorResponse`

### 2.2 enums

- `Intent`
- `FollowUpType`
- `StageName`
- `ResponseMode`
- `ResponseType`
- `SupportStrength`

## 3. 暂不在第一批新增的结构

当前 change 不额外引入以下新结构：

- `shared/entities/`
- `shared/utils/`
- `frontend/web/`
- 独立前端 API client 生成链路

原因是这次目标仍然是“工程骨架迁移”，而不是发明新业务层次或提前切换技术栈。

## 4. 本轮必须修正的导入和启动路径

当前代码迁移后，以下几类路径必须同步调整：

### 4.1 shared 导入路径

以下后端模块当前仍从 `finsight_agent.shared.*` 导入，迁移后应改为 `shared.*`：

- `control_plane/router/service.py`
- `control_plane/orchestrator/stage_planner.py`
- `capabilities/structured_data/service.py`
- `capabilities/reporting/service.py`
- `shared/contracts/router_result.py`

### 4.2 测试路径注入

当前测试把 `src/` 加入 `sys.path`。  
迁移后应改为：

- 将 `backend/src/` 加入 `sys.path`，用于导入 `finsight_agent`
- 保持仓库根目录可见，便于导入顶层 `shared`

### 4.3 工作台边界

`frontend/streamlit_app/` 迁移后仍不得出现下面这类依赖：

- `from finsight_agent.control_plane ...`
- `from finsight_agent.capabilities ...`
- `from finsight_agent.infra ...`

如果前端需要消费结果，只能通过：

- 稳定后端接口
- `shared/contracts/*`
- `shared/enums/*`

## 5. 迁移完成后的检查点

完成目录迁移后，应至少确认：

- 顶层已存在 `frontend/`、`backend/`、`shared/`
- `apps/` 与旧 `src/finsight_agent/shared/` 不再作为主骨架存在
- 后端入口位于 `backend/apps/api/main.py`
- 前端入口位于 `frontend/streamlit_app/app.py`
- 共享对象位于 `shared/contracts/` 和 `shared/enums/`
- 自动化测试已切换到新目录和新导入路径
