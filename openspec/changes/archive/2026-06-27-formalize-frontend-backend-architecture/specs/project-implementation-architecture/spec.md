## MODIFIED Requirements

### Requirement: 顶层目录必须区分工程层、文档和运行产物
项目 MUST 在仓库顶层区分前端工程、后端工程、跨工程共享目录、说明文档、测试样本、工程脚本和本地运行产物，避免把文档、实现和临时文件混在一起。

#### Scenario: 初始化第一版工程骨架
- **WHEN** 项目开始创建采用前后端工程层方案的第一版代码目录
- **THEN** 顶层结构 MUST 至少明确 `frontend/`、`backend/`、`shared/`、`config/`、`fixtures/`、`tests/`、`scripts/`、`var/`、`docs/` 和 `openspec/` 这些职责边界

#### Scenario: 本地产生数据库、缓存或日志
- **WHEN** 开发或调试过程中产生 SQLite 文件、缓存文件或日志文件
- **THEN** 这些运行产物 MUST 默认放在 `var/` 或等价运行目录中，而不是散落在 `frontend/`、`backend/`、`shared/`、源码目录或文档目录里

### Requirement: 后端运行时代码必须按共享层、控制面、能力层和入口层分开
项目 MUST 将后端核心实现分成共享层、控制面、能力层、基础设施层和入口层，同时将 `frontend/`、`backend/`、`shared/` 作为工程层边界，使目录结构既能表达系统职责，也能表达前后端工程归属。

#### Scenario: 映射 capability spec 到后端代码目录
- **WHEN** 开发者需要根据现有 capability spec 创建后端运行时代码目录
- **THEN** 项目 MUST 允许将 `semantic-routing-and-planning` 映射到 `backend/src/finsight_agent/control_plane/router/` 与 `backend/src/finsight_agent/control_plane/planner/`，将 `event-analysis-orchestration` 映射到 `backend/src/finsight_agent/control_plane/orchestrator/`，将 `structured-market-data-support`、`evidence-retrieval-pipeline`、`report-trace-and-evaluation` 分别映射到 `backend/src/finsight_agent/capabilities/` 下的对应目录，而不是强制一比一建立 7 个长目录名

#### Scenario: 技术入口与业务实现分离
- **WHEN** 项目创建 FastAPI 后端入口和 V1 工作台入口
- **THEN** 后端启动代码 MUST 放在 `backend/apps/api/` 或等价后端入口层，V1 工作台入口 MUST 放在 `frontend/streamlit_app/` 或等价前端入口层，核心业务逻辑 MUST 放在 `backend/src/` 下的可复用模块中

### Requirement: 共享契约对象和领域对象必须按跨工程共享与后端内部复用区分存放
项目 MUST 把跨前后端共享的 canonical contracts 与仅供后端内部复用的领域小对象区分开，避免所有结构都堆在一个目录里。

#### Scenario: 新增前后端共同消费的稳定输入输出对象
- **WHEN** 某个对象会被前端与后端共同作为稳定接口或展示协议消费，例如 `FinalResponse`、`TraceBlock`、`GuardrailOrErrorResponse` 或其他 canonical contracts
- **THEN** 该对象 MUST 放在顶层 `shared/contracts/`、`shared/enums/` 或等价跨工程共享目录中，并与共享 contract 文档保持对应关系

#### Scenario: 新增仅供后端多个模块复用的语义小对象
- **WHEN** 某个对象更像后端多个模块复用的语义片段，例如事件实体、候选目标、claim 或时间范围
- **THEN** 该对象 SHOULD 放在 `backend/src/` 下的共享 entities 目录中，而不是直接塞进顶层跨工程共享 contract 目录

### Requirement: 目录依赖方向必须同时限制工程层与后端实现层
项目 MUST 同时明确工程层与后端实现层之间允许的依赖方向，避免前端反向依赖后端内部实现、共享层反向依赖业务层，或入口层承担业务语义。

#### Scenario: 前端工作台消费后端结果
- **WHEN** `frontend/` 需要展示报告、trace、错误状态或继续追问
- **THEN** `frontend/` MUST 通过后端统一接口、稳定响应对象或顶层 `shared/` 契约消费结果，而不应直接 import `backend/src/` 下的控制面、能力层或基础设施层实现

#### Scenario: 后端内部共享层被多个模块复用
- **WHEN** `backend/src/` 下的共享层被控制面、能力层和工作台相关后端适配代码共同依赖
- **THEN** 该共享层 MUST 不依赖这些上层业务模块，只提供基础对象、枚举和通用小工具

#### Scenario: 能力层调用基础设施适配器
- **WHEN** retrieval、structured data 或 reporting 需要使用向量库、外部 API 或文件解析能力
- **THEN** 这些底层接入 SHOULD 通过 `backend/src/finsight_agent/infra/` 或等价基础设施层暴露，而不是在业务模块中随意直连和重复封装

### Requirement: 工程骨架必须先支持最小可运行链路并为后续前端升级预留边界
项目 MUST 先搭出能承接 `metric_lookup` 快路径、共享 contracts 和 V1 前端工作台的最小骨架，再逐步扩展长路径能力，并为后续独立 Web 前端升级保留清晰边界。

#### Scenario: 开始第一轮真正代码实现
- **WHEN** 项目进入采用前后端工程层方案的第一轮代码开发
- **THEN** 第一批骨架 MUST 至少为顶层 `shared/contracts/`、`shared/enums/`、`frontend/streamlit_app/`、`backend/src/finsight_agent/control_plane/router/`、`backend/src/finsight_agent/control_plane/planner/`、`backend/src/finsight_agent/capabilities/structured_data/` 和 `backend/src/finsight_agent/capabilities/reporting/` 留出明确目录与文件位置

#### Scenario: 后续扩展完整事件分析链路
- **WHEN** 项目从简单快路径扩展到 `event_impact_analysis`
- **THEN** 现有工程层与后端实现层结构 MUST 能在不推翻 `frontend/`、`backend/`、`shared/` 边界的前提下，继续容纳 `collect_event_context`、`analyze_targets`、`retrieve_evidence` 和 `synthesize_report`
