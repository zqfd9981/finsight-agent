## Purpose

定义 FinSight Agent V1 并行开发所需的跨模块共享 contract 目录，包括核心对象定义、语义 owner、producer / consumer 关系以及降级语义约定。

## 重点关注

- 哪些对象属于跨模块共享 canonical object
- 每个共享对象由谁拥有语义主权
- 并行开发中如何通过统一 contract 和示例 payload 降低联调歧义

## 非职责范围

- 不取代现有业务 capability 对自身领域语义的 ownership
- 不负责具体运行时代码的 schema 校验实现

## 上下游关系

- 上游输入：现有 7 个 capability 的共享对象需求
- 下游输出：canonical contract 定义、owner 约定、mock payload 基线

## Requirements

### Requirement: 共享 contract 目录定义跨模块 canonical object
项目 MUST 维护一份统一的共享 contract 目录，用于定义 FinSight Agent V1 中被多个模块复用的核心对象，包括 `RouterResult`、`Plan`、`SessionContext`、`StageObservation`、`EvidenceBundle`、`FinalResponse`、`TraceBlock` 以及 guardrail / error response。

#### Scenario: 团队需要查询共享对象定义
- **WHEN** 任一模块团队需要生产或消费某个 V1 共享对象
- **THEN** 共享 contract 目录 MUST 提供该对象的必填字段、字段语义、producer、consumer 和 degraded-state 约定

### Requirement: 每个共享 contract 具有唯一语义 owner
每一个共享 contract MUST 指定且仅指定一个语义 owner capability，由它负责审批 required field 变更并维护对象语义边界。

#### Scenario: 有团队提出 required field 变更
- **WHEN** 某个团队提出新增、删除或重定义共享 contract 的 required field
- **THEN** 该变更 MUST 经过对应 owner capability 评审，并识别受影响的下游 consumer 之后才能接受

### Requirement: 共享 contract 提供并行开发示例
共享 contract 目录 MUST 为关键对象提供示例 payload 或等价 fixture，使下游团队在上游实现未完成前也能开展 mock-based 开发。

#### Scenario: 下游在上游实现完成前启动开发
- **WHEN** 某个消费方团队需要早于上游 producer 完成实现而开始开发
- **THEN** 共享 contract 目录 MUST 提供符合 canonical contract 的示例 payload，足以支持本地开发和联调准备

### Requirement: 共享 contract 目录必须定义前后端 API 边界对象
项目 MUST 在共享 contract 目录中定义 workbench 与 backend API boundary 所需的稳定对象，至少覆盖统一分析请求对象和统一分析响应 envelope，避免前后端各自发明 payload。

#### Scenario: 团队需要消费统一分析请求对象
- **WHEN** 前端工作台或后端 API 入口需要发送、接收或校验一轮分析请求
- **THEN** 共享 contract 目录 MUST 提供该请求对象的稳定字段定义，至少覆盖 `query`、optional `session_id` 和 optional trace 请求字段

#### Scenario: 团队需要消费统一分析响应 envelope
- **WHEN** 前端工作台或后端 API 入口需要发送、接收或校验一轮分析响应
- **THEN** 共享 contract 目录 MUST 提供稳定的响应 envelope 定义，至少覆盖 `version`、`session_id`、主 `response` 对象和 `trace_blocks`
