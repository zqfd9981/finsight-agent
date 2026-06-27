## MODIFIED Requirements

### Requirement: 分析工作台呈现 V1 分析流程
系统 MUST 提供一个位于 `frontend/` 工程中的 V1 分析工作台，在 V1 阶段以 Streamlit 实现，支持中文自由文本输入、展示当前分析结果，并在不要求用户查看后端日志的前提下暴露 trace 细节。

#### Scenario: 用户发起首轮分析
- **WHEN** 用户在位于 `frontend/` 工程中的工作台提交一个中文事件影响分析问题
- **THEN** 工作台必须创建新的分析轮次、显示请求进度，并在主结果区域渲染后端返回的报告

#### Scenario: 用户展开 trace 细节
- **WHEN** 一次分析响应中包含 routing、planning、retrieval 或 critic 的 trace 数据
- **THEN** 工作台必须渲染一个可展开的 trace 面板，并将这些 trace 分区与最终报告分开展示

## ADDED Requirements

### Requirement: 分析工作台必须通过稳定后端接口消费结果
系统 MUST 要求前端工作台通过后端统一接口、稳定 response 或共享 contract 消费能力结果，而不是直接依赖后端内部控制面、检索或报告实现模块。

#### Scenario: 工作台发起分析请求
- **WHEN** 工作台发起首轮分析或多轮追问请求
- **THEN** 工作台必须通过后端统一接口提交 query、session 标识和必要的追问上下文，而不能直接调用后端内部 service

#### Scenario: 工作台渲染结果与降级态
- **WHEN** 工作台收到 `FinalResponse`、`TraceBlock` 或 `GuardrailOrErrorResponse` 等稳定输出
- **THEN** 工作台必须基于这些稳定输出渲染主结果、trace 和降级状态，而不应依赖后端内部中间对象的私有结构
