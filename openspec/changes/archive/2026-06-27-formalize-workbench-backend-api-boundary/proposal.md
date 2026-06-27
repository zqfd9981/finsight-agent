## Why

当前仓库已经完成 `frontend/ + backend/ + shared/` 的工程层拆分，也明确了前端不得直接依赖后端内部模块，但“前端到底通过什么 API 调后端、请求和响应长什么样、会话如何续接、降级和错误如何稳定返回”仍缺少正式规范。  
如果现在直接开始实现最小链路，很容易边写代码边发明接口，导致前后端和 shared contract 后续返工。

## What Changes

- 新增一份 V1 workbench 到 backend 的正式 API boundary spec，定义前端分析请求的统一入口、首轮分析与追问的会话约束，以及稳定的响应 envelope。
- 明确 V1 先采用同步 HTTP 请求-响应模型，而不是 streaming、SSE 或 WebSocket。
- 把前后端边界需要稳定共享的请求对象与响应 envelope 纳入 shared contract 约束，避免各端私自扩展 payload。
- 明确什么时候返回稳定业务响应，什么时候才使用协议级非 2xx 状态码。

## Capabilities

### New Capabilities
- `workbench-backend-api-boundary`: 定义 V1 前端工作台与后端分析入口之间的稳定调用协议、会话续接规则与响应语义。

### Modified Capabilities
- `shared-analysis-contracts`: 增补前后端 API 边界相关的共享 contract，覆盖请求对象与响应 envelope 的稳定字段要求。

## Impact

- 受影响 spec：
  - `openspec/specs/shared-analysis-contracts/spec.md`
  - 新增 `openspec/specs/workbench-backend-api-boundary/spec.md`
- 受影响代码骨架：
  - `frontend/streamlit_app/`
  - `backend/apps/api/`
  - `shared/contracts/`
- 受影响联调资产：
  - `fixtures/contracts/`
  - 前后端 API contract 测试
