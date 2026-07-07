# Streamlit 调试与评测工作台设计

日期：2026-07-05

## 背景

当前仓库已经具备以下基础能力：

- `metric_lookup`、`evidence_lookup`、`event_impact_analysis` 三条主链可运行
- `event_impact_analysis` 已接入双层外部检索
- 事件评测与回放框架已经落地，具备 `fixtures + replay runner + checks`
- 统一分析接口 `POST /api/v1/analysis/turns` 已可返回 `response + trace_blocks`

但当前前端仍停留在非常轻的骨架阶段，存在两个明显问题：

1. 开发调试时只能看测试输出或 JSON，定位 `route / plan / stage` 问题效率低
2. 评测框架虽然已具备后端能力，但没有可视化入口，不利于回放、筛选和误判复盘

因此本轮目标不是做正式产品前端，而是在现有 Streamlit 骨架上补一套**内部调试与评测工作台**，同时兼顾分析同学的日常试用。

## 目标

第一版工作台需要同时满足三类使用场景：

1. 分析同学可以输入一条 query，快速看到最终回答、关键证据和基本运行状态
2. 开发同学可以查看 routing、planning、execution trace，以及各个 stage 的关键输出
3. 团队可以运行事件评测样本，查看 `pass / warn / fail`，并对单条 case 做回放分析

## 非目标

第一版明确不做以下内容：

- 正式面向外部用户的产品前端
- 多项目空间、用户权限、团队协作管理
- 图形化 DAG 编辑器
- LLM judge 平台
- 历史运行数据库与长期 trace 存储
- 复杂 dashboard、报表中心、导出中心
- 独立于现有 Streamlit 之外的新前端技术栈

## 方案比较

### 方案 1：单页混合工作台

在一个页面里同时展示 query 输入、最终结论、trace、stage 细节和 replay 结果。

优点：

- 实现最快
- 导航成本最低

缺点：

- 分析使用与开发调试信息混在一起
- 页面会很快膨胀
- 后续扩展 replay 和误判复盘时会变乱

### 方案 2：同一应用，双模式/多页面工作台

基于现有 Streamlit 应用拆出多个页面，在同一应用内分别服务分析、调试和评测。

优点：

- 同时兼顾分析使用与开发调试
- 复用同一套后端接口与会话状态
- 页面职责清晰，后续扩展成本低
- 与当前仓库已有 `frontend/streamlit_app` 结构最一致

缺点：

- 比单页方案多一层页面与组件组织工作

### 方案 3：两套前端

为分析同学和开发同学分别做独立前端。

优点：

- 用户边界最清晰

缺点：

- 维护成本明显过高
- 当前阶段远超必要范围
- 会把还未完全稳定的后端接口绑定两遍

## 推荐方案

采用**方案 2：同一 Streamlit 应用，多页面工作台**。

原因：

- 用户明确希望同时兼顾分析使用和调试需求
- 现有前端已经是 Streamlit 骨架，继续沿用最稳
- 当前最需要的是“可视化工作台”，不是“正式产品前端”
- 多页面结构既能控制范围，又能为后续扩展留下余地

## 总体架构

第一版工作台建立在现有 `frontend/streamlit_app` 之上，不新起技术栈。

信息流如下：

1. 用户在 Streamlit 页面输入 query 或选择评测 case
2. 前端通过现有分析接口或新增轻量 eval 接口请求后端
3. 后端返回 `AnalysisResponseEnvelope` 或 replay records
4. 前端将结果按不同页面职责可视化

工作台分为三个主页面：

- `分析视图`
- `调试视图`
- `评测视图`

## 页面设计

### 1. 分析视图

定位：面向分析同学或日常试用。

主要展示内容：

- query 输入框
- `first_turn / follow_up`
- `session_id`
- 最终回答 `summary`
- `report_blocks`
- 不确定性说明
- 简化执行元信息
  - `intent`
  - `strategy`
  - `degraded`
  - `target_count`
  - `evidence_ref_count`

设计原则：

- 默认优先可读性
- 默认不展示 raw trace
- 技术信息只展示摘要级字段

### 2. 调试视图

定位：面向开发调试与链路排障。

主要展示内容：

- routing 结果
- planning 结果
- execution trace
- 各个 stage 的状态与关键输出
- 原始 `trace_blocks` 的可展开视图

展示层次：

- 默认先显示摘要、关键字段、状态
- raw payload 放在展开区
- 不把页面做成简单 JSON dump

重点解决的问题：

- 这一轮到底走了什么 intent / strategy
- 哪个 stage 降级了
- 候选为什么为空
- 外部检索、RAG、目标分析各自产出了什么

### 3. 评测视图

定位：面向事件评测与误判回放。

主要展示内容：

- fixture case 列表
- `pass / warn / fail` 筛选
- 预期值与实际值对照
- checks 列表
- 单条 case 的 replay detail
- 可展开查看 trace 与 stage 明细

重点解决的问题：

- 当前系统对一批样本的整体表现如何
- 哪些 case 容易误判或过度降级
- provider 或分类器变更后影响了哪些场景

## 页面切换与导航

第一版采用 Streamlit 的多页面结构，通过左侧导航在三个主页面间切换。

不采用单页面多 tab 作为主结构，原因是：

- 当前页面职责差异明显
- `分析视图`、`调试视图`、`评测视图` 面向不同关注点
- 未来继续加页面时，多页面结构更稳定

## 前端组件边界

为了避免页面文件过胖，建议预先拆出以下组件：

- `analysis_run_form`
  - 负责 query、session、follow-up、trace 开关、提交
- `response_summary_card`
  - 负责 summary、response_type、degraded 展示
- `trace_block_viewer`
  - 负责 route / plan / execution trace 展示
- `stage_observation_card`
  - 负责单个 stage 状态与关键输出展示
- `eval_case_table`
  - 负责评测 case 列表与筛选
- `eval_result_detail`
  - 负责单条 replay record 与 checks 详情

组件复用原则：

- `分析视图` 和 `调试视图` 共享运行表单与响应摘要组件
- `调试视图` 和 `评测视图` 共享 trace / stage 展示组件

## 状态管理

第一版只采用轻量级 `st.session_state`，不引入复杂全局 store。

建议维护的状态包括：

- 最近一次分析运行结果
- 当前 `session_id`
- 当前选中的 replay case
- 当前评测筛选条件

关键约束：

- `分析视图` 与 `调试视图` 共享同一份最近运行结果
- 用户在分析视图跑完后，切到调试视图可直接查看同一轮 trace

## 后端接口设计

## 复用现有接口

以下接口直接复用：

- `POST /api/v1/analysis/turns`

用途：

- `分析视图`
- `调试视图`

原因：

- 当前统一分析接口已经能返回 `response` 与 `trace_blocks`
- 前两页无需新增独立“运行接口”

## 新增最小 eval 接口

第一版只新增两类轻量接口：

### 1. `GET /api/v1/eval/event-cases`

作用：

- 返回事件评测 fixture case 列表

返回字段至少包括：

- `case_id`
- `query`
- `expected_intent`
- `expected_strategy`
- `allow_degraded`
- `min_target_count`
- `expected_target_keywords`
- `notes`

### 2. `POST /api/v1/eval/event-replay`

作用：

- 运行一条或一组 event replay

请求支持：

- 指定 `case_ids`
- 或 `run_all=true`

返回字段至少包括：

- `records`
- `summary.total`
- `summary.pass`
- `summary.warn`
- `summary.fail`

每条 `record` 至少包含：

- `case`
- `result`
- `checks`

## 明确不新增的接口

第一版不新增以下能力：

- 历史 trace 查询接口
- stage observation 独立查询接口
- replay 结果持久化接口
- 历史运行列表接口

原因：

- 这些能力会把工作台推向平台化
- 当前目标只是做最小内部调试/评测入口

## 数据流

### 分析视图数据流

1. 前端提交 query 到 `POST /api/v1/analysis/turns`
2. 后端返回 `AnalysisResponseEnvelope`
3. 前端提取 summary、report blocks、简化元信息
4. 结果写入 `session_state.last_analysis_result`

### 调试视图数据流

1. 优先读取 `session_state.last_analysis_result`
2. 若为空，则允许用户本页发起一次运行
3. 前端解析 `trace_blocks`
4. 按 route / plan / execution / stage 结构化展示

### 评测视图数据流

1. 页面初始化调用 `GET /api/v1/eval/event-cases`
2. 用户点击运行按钮后调用 `POST /api/v1/eval/event-replay`
3. 后端返回 replay records 与 checks
4. 前端显示 case 列表、状态聚合和详情对照

## 错误处理与降级

前端需要明确区分三类情况：

1. 请求失败
   - 显示接口错误与上下文
2. 分析成功但 `degraded`
   - 在分析视图中显示降级提示
   - 在调试视图中高亮相关 stage
3. replay 中的 `warn / fail`
   - 在评测视图中做显著标识

第一版不要求复杂重试策略，只要求：

- 错误可见
- 降级可见
- replay 结果可筛选

## 测试策略

第一版需要至少覆盖以下层次：

1. 前端组件级测试或最小渲染测试
   - 关键组件能处理空数据与正常数据
2. API client 测试
   - 分析响应与 replay 响应能被正确解析
3. 评测接口集成测试
   - `event-cases` 与 `event-replay` 返回符合预期 schema
4. smoke 级前端联通测试
   - 至少验证页面能装配并调用到正确接口

## 实现顺序

建议按以下顺序推进：

1. 补 `event-cases` 与 `event-replay` 两个后端接口
2. 将 Streamlit app 扩成多页面结构
3. 先实现 `分析视图`
4. 再实现 `调试视图`
5. 最后实现 `评测视图`

原因：

- 接口先稳，前端才能顺着长
- `分析视图` 和 `调试视图` 对当前使用价值最高
- `评测视图` 依赖 replay 接口，但仍属于同一轮最小闭环

## 验收标准

第一版完成后，应满足以下标准：

1. 用户可以在工作台输入一条 query 并看到最终回答
2. 用户可以查看同一轮的 route / plan / execution trace
3. 用户可以查看单个 stage 的关键输出摘要
4. 用户可以列出事件评测样本并运行 replay
5. 用户可以看到 `pass / warn / fail` 以及预期与实际的差异
6. 全流程不要求平台化，但要求足够支持日常调试与误判复盘
