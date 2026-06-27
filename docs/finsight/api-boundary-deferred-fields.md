# FinSight V1 前后端 API Boundary Deferred Fields

日期：2026-06-27
状态：生效中

## 目的

这份文档只记录 V1 统一分析接口中暂缓冻结的字段，避免骨架阶段为了补齐未来能力而反向发明复杂协议。

## 当前冻结范围

- `AnalysisRequest`
  - 已冻结：`version`、`query`、`query_mode`、`session_id`、`include_trace`
  - 暂缓：用户身份、鉴权头、筛选器、分页、模型偏好
- `AnalysisResponseEnvelope`
  - 已冻结：`version`、`session_id`、`turn_id`、`response`、`trace_blocks`
  - 暂缓：耗时统计、服务端调试元数据、分页 trace、附件下载链接

## 延后原则

- 暂缓字段不进入前后端联调前置条件。
- 如果后续 change 需要新增 required field，必须先更新 OpenSpec change 和共享 fixture。
- 在 V1 骨架阶段，前端只能依赖已冻结字段渲染占位结果。
