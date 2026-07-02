# 数据与证据面状态

日期：2026-07-02  
当前状态：可联调  
当前负责人：待分配

## 1. 模块范围

- `structured-market-data-support`
- `evidence-retrieval-pipeline`

## 2. 当前里程碑

- `Retrieval Pipeline Ready`
- `Structured Data Ready`

## 3. 当前阶段结论

数据与证据面已经从“准备接线”推进到“稳定被控制面消费”的状态：

- retrieval 主链已稳定支持 `evidence_lookup` 与 `event_impact_analysis`
- structured data 主链已稳定支持 `metric_lookup`
- orchestrator 已能同时消费：
  - 结构化指标查询
  - 本地 RAG 混合检索
  - 外部工具检索抽象

## 4. 当前输出

### retrieval 已完成能力

- 本地 PDF acquisition
- parsing + chunking
- sparse retrieval
- dense retrieval
- fusion / rerank
- retrieval output assembly
- `RetrievalResult`
- retrieval trace
- parent context expand

### structured data 已完成能力

- 本地财报表格指标抽取
- 本地指标仓储与查询
- 本地优先、外部 fallback 的服务层
- `metric_lookup` 首版真实数值返回

### 本轮新增消费方式

- `collect_event_context` 会结合外部上下文检索与本地 RAG 生成事件背景
- `retrieve_evidence` 会消费 `collect_event_context` / `analyze_targets` 输出继续补强证据
- `analyze_targets` 候选池不足时可触发一次外部候选发现检索

## 5. 活跃任务状态

- 任务：retrieval 主链稳定化  
  状态：已完成  
  说明：已具备可持续回归的单测与集成测试

- 任务：structured market data 首版闭环  
  状态：已完成  
  说明：本地财报表格 -> 指标库 -> 查询服务 -> `metric_lookup` 已打通

- 任务：事件背景与候选发现检索接线  
  状态：已完成首版  
  说明：已具备抽象层与 orchestrator 消费位点

- 任务：真实外部 provider 接入  
  状态：未开始  
  说明：当前仍以抽象接口与 stub 为主

- 任务：评测样本补齐  
  状态：未开始  
  说明：仍缺首批事件分析与指标查询联合评测集

## 6. 当前风险与卡点

- 外部检索 provider 尚未接入，近期事件覆盖仍有限
- structured data 的公司、指标与期间覆盖度仍需扩展
- 事件分析相关的候选发现质量尚缺评测集支撑

## 7. 不要改什么

- 不要让 retrieval 模块承担 orchestrator 的状态编排职责
- 不要让 structured data 服务直接暴露内部构建细节给 API boundary
- 不要把外部 provider 的不稳定返回直接冒充成本地财报真值

## 8. 下一次阶段检查

1. 检查首个真实外部检索 provider 是否落地
2. 检查 structured data 是否扩展到更多指标与期间
3. 检查事件分析候选发现检索是否有评测样本支撑

## 9. 完成定义

数据与证据面下一阶段可视为“进一步完成”的条件：

- 外部 provider 已具备真实可用的接入实现
- structured data 覆盖度明显提升
- retrieval / structured data / event analysis 形成联合评测入口
