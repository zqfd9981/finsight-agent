## Purpose

定义 FinSight Agent V1 的结构化市场数据支持能力，包括主题映射、候选对象筛选和有限结构化字段供给。

## 重点关注

- 从事件语义到主题、行业、概念、候选公司的结构化映射
- V1 所需的基础筛选字段与对比字段

## 非职责范围

- 不负责全文证据验证
- 不扩张成完整 XBRL 或重型投研数据库

## 上下游关系

- 上游输入：event entities、impact hypotheses、candidate narrowing requests
- 下游输出：主题集合、候选公司集合、排序/过滤字段

## Requirements

### Requirement: 结构化市场数据支持主题与公司映射
系统 MUST 提供结构化市场数据查询能力，把事件或概念分析映射到 A 股主题、行业、概念和候选公司。

#### Scenario: 事件假设映射到市场对象
- **WHEN** target-analysis 阶段接收到 event entities 和 impact hypotheses
- **THEN** structured data 层必须返回与这些假设相关的主题、行业、概念以及候选公司集合

#### Scenario: 置信度不足时停留在主题层
- **WHEN** concept mapping 的置信度不足以收敛到公司级别
- **THEN** structured data 层必须允许工作流停留在主题或板块层，而不能强行给出公司推荐

### Requirement: 结构化市场数据支持基础公司筛选
系统 MUST 支持利用核心元数据和 V1 分析所需的有限财务或分类字段，对候选公司进行筛选。

#### Scenario: 工作流收窄宽泛候选集
- **WHEN** target analysis 需要缩小一个较宽的候选公司列表
- **THEN** structured data 层必须支持按主题归属、行业、概念标签和可用核心财务字段进行筛选

#### Scenario: 对比流程需要可排序字段
- **WHEN** planner 为一个已有候选集请求 comparative analysis
- **THEN** structured data 层必须提供 V1 基础排序和并排对比所需的可排序字段

### Requirement: 结构化市场数据保持 V1 范围有界
系统 MUST 只暴露 V1 所需的中量级结构化数据能力，而不能要求完整的 XBRL 级投研数据库。

#### Scenario: V1 请求受支持的财务字段
- **WHEN** 某个工作流请求 V1 数据契约中包含的基础财务指标
- **THEN** structured data 层必须通过受支持的查询接口返回这些字段

#### Scenario: 工作流请求不受支持的深度投研字段
- **WHEN** 某个工作流请求不受支持的估值模型数据或完整三表重建数据
- **THEN** structured data 层必须返回明确的不支持结果，而不是伪造深度投研覆盖能力
