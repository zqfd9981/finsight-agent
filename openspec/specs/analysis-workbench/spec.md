## Purpose

定义 FinSight Agent V1 分析工作台的用户交互边界，包括输入发起、结果展示、trace 展示、追问体验和降级态展示。

## 重点关注

- 用户如何发起分析、查看结果、展开 trace、继续追问
- 用户如何理解降级结果，而不是面对后端异常或空白页
- V1 工作台如何以 `frontend/` 工程归属存在，同时与后端保持稳定消费边界

## 非职责范围

- 不负责路由判别、计划生成和检索实现
- 不负责定义会话压缩策略或结构化市场数据查询逻辑

## 上下游关系

- 上游输入：后端统一 response、trace 数据、session 标识、共享 contracts
- 下游输出：用户 query、追问输入、session continuity

## Requirements

### Requirement: 分析工作台呈现 V1 分析流程
系统 MUST 提供一个位于 `frontend/` 工程中的 V1 分析工作台，在 V1 阶段以 `Streamlit` 实现，支持中文自由文本输入、展示当前分析结果，并在不要求用户查看后端日志的前提下暴露 trace 细节。

#### Scenario: 用户发起首轮分析
- **WHEN** 用户在位于 `frontend/` 工程中的工作台提交一个中文事件影响分析问题
- **THEN** 工作台必须创建新的分析轮次、显示请求进度，并在主结果区域渲染后端返回的报告

#### Scenario: 用户展开 trace 细节
- **WHEN** 一次分析响应中包含 routing、planning、retrieval 或 critic 的 trace 数据
- **THEN** 工作台必须渲染一个可展开的 trace 面板，并将这些 trace 分区与最终报告分开展示

### Requirement: 分析工作台支持追问交互
系统 MUST 允许用户在已有分析会话中继续追问，并保留关于当前主题、候选对象和既有证据的可见上下文。

#### Scenario: 用户发起 drilldown 追问
- **WHEN** 用户在一个已有会话中提交追问问题
- **THEN** 工作台必须在新轮次请求中携带当前 session 标识，并在同一会话时间线中展示追问结果

#### Scenario: 用户在同一会话中改道
- **WHEN** 后端将某一轮标记为 redirected follow-up
- **THEN** 工作台必须保留历史轮次，同时清晰地区分这次结果是一次重新规划后的新轮次

### Requirement: 分析工作台能够承接后端降级输出
系统 MUST 以用户可读的方式展示后端返回的结构化降级响应，而不是静默失败或直接展示原始异常。

#### Scenario: 后端返回信息不足结果
- **WHEN** 后端返回一个表示事件上下文不足的 guardrail 响应
- **THEN** 工作台必须在专门的报告区域中展示部分结论、阻塞原因和建议的下一步操作

#### Scenario: 后端请求出现意外失败
- **WHEN** 一次分析请求由于意外执行错误而无法完成
- **THEN** 工作台必须展示带重试指引的稳定错误态，并且不能丢弃先前已经渲染的会话内容

### Requirement: 分析工作台必须通过稳定后端接口消费结果
系统 MUST 要求前端工作台通过后端统一接口、稳定 response 或共享 contract 消费能力结果，而不是直接依赖后端内部控制面、检索或报告实现模块。

#### Scenario: 工作台发起分析请求
- **WHEN** 工作台发起首轮分析或多轮追问请求
- **THEN** 工作台必须通过后端统一接口提交 query、session 标识和必要的追问上下文，而不能直接调用后端内部 service

#### Scenario: 工作台渲染结果与降级态
- **WHEN** 工作台收到 `FinalResponse`、`TraceBlock` 或 `GuardrailOrErrorResponse` 等稳定输出
- **THEN** 工作台必须基于这些稳定输出渲染主结果、trace 和降级状态，而不应依赖后端内部中间对象的私有结构

### Requirement: 分析工作台必须可从工程根目录启动并联通后端

系统 MUST 提供从仓库根目录启动分析工作台的可执行入口，使后端 API 服务与 Streamlit 前端可以在本地同时运行，并通过稳定后端接口完成一次端到端分析请求。

#### Scenario: 操作员从仓库根目录启动工作台
- **WHEN** 操作员先后启动后端 API 服务（`python scripts/run_workbench_backend.py` 或等价 `uvicorn backend.apps.api.main:app`）以及 Streamlit 前端（`streamlit run frontend/streamlit_app/streamlit_entry.py` 或等价 `.sh/.cmd` 脚本）
- **THEN** 系统 MUST 在两个进程就绪后允许前端发起首轮分析请求，并通过既有 API boundary 接收到稳定的 response envelope

#### Scenario: 配置文件驱动后端与前端端口
- **WHEN** 操作员在 `config/app.yaml` 的 `app.workbench` 段调整 `backend_host` / `backend_port` / `backend_base_url` / `frontend_host` / `frontend_port` 后重新启动工作台
- **THEN** 系统 MUST 让后端与前端使用新配置值，并将前端构造的 API 请求发往 `backend_base_url`，而不是默认值或硬编码地址

#### Scenario: 工作台首轮分析请求失败时不能崩溃
- **WHEN** 工作台向后端提交首轮分析请求而后端返回 guardrail / 降级响应或 5xx 错误
- **THEN** 工作台 MUST 在不退出 Streamlit 进程的前提下展示稳定的错误态，并允许用户继续重试或切换页面

#### Scenario: 工作台切换页面后仍可回到分析结果
- **WHEN** 用户在「分析视图」得到一份 envelope 后切换到「调试视图」或「评测视图」
- **THEN** 系统 MUST 让最近一次 envelope 在 Streamlit 会话内可继续被「调试视图」消费，而无需重新运行分析
