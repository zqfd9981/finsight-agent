## ADDED Requirements

### Requirement: 共享 contract 目录必须定义前后端 API 边界对象
项目 MUST 在共享 contract 目录中定义 workbench 与 backend API boundary 所需的稳定对象，至少覆盖统一分析请求对象和统一分析响应 envelope，避免前后端各自发明 payload。

#### Scenario: 团队需要消费统一分析请求对象
- **WHEN** 前端工作台或后端 API 入口需要发送、接收或校验一轮分析请求
- **THEN** 共享 contract 目录 MUST 提供该请求对象的稳定字段定义，至少覆盖 `query`、optional `session_id` 与 optional trace 请求字段

#### Scenario: 团队需要消费统一分析响应 envelope
- **WHEN** 前端工作台或后端 API 入口需要发送、接收或校验一轮分析响应
- **THEN** 共享 contract 目录 MUST 提供稳定的响应 envelope 定义，至少覆盖 `version`、`session_id`、主 `response` 对象和 `trace_blocks`
