# FinSight Query 路由与节点链路说明（业务视角）

日期：2026-07-08

## 1. 这份文档是写给谁看的

这不是一份 OpenSpec 设计稿，也不是研发实现细节清单。

这份文档的目标是：

- 用业务语言说明 FinSight 现在不同问题是怎么走链路的
- 说明我们在这次讨论里收敛出的理想链路应该是什么样
- 说明哪些问题需要新闻，哪些问题需要公告，哪些问题需要公司证据
- 说明关键中间字段应该承载什么信息，避免后面再把链路设计得过重或过乱


## 2. 先说结论

当前系统最核心的问题不是“没有分类器”，而是：

- `event_impact_analysis` 一旦命中，planner 现在几乎固定走四段链路
- 现有 `event_primary / disclosure_primary / dual_primary` 分类结果，只影响“优先搜什么源”
- 这个分类结果还没有真正上升为“决定 stage 编排”的信号

我们这次讨论后的理想方向是：

- `metric_lookup`、`evidence_lookup` 继续走自己的短链路
- 只有 `intent = event_impact_analysis` 时，才进入检索策略分类
- 分类器输出 `event_primary / disclosure_primary / dual_primary`
- planner 再根据这个 label 决定后续 stage 组合
- 不新增 router 字段作为第一步改造前提


## 3. 当前系统里实际存在的几类能力

### 3.1 顶层 intent

当前共享枚举里有 4 个 intent：

- `metric_lookup`
- `event_impact_analysis`
- `evidence_lookup`
- `out_of_scope`

含义可以简单理解为：

- `metric_lookup`：问一个结构化数值
- `event_impact_analysis`：问一个事件或事件影响
- `evidence_lookup`：要证据、原文、依据
- `out_of_scope`：超出能力范围

### 3.2 当前系统已有的 stage

当前共享 stage 枚举有 6 个：

- `collect_event_context`
- `analyze_targets`
- `retrieve_evidence`
- `synthesize_report`
- `query_structured_data`
- `synthesize_brief_answer`

业务上可以这么理解：

- `collect_event_context`：补外部事件背景
- `analyze_targets`：从事件背景收缩到板块/公司/标的候选
- `retrieve_evidence`：去内部证据库补证据
- `synthesize_report`：生成偏完整的分析答复
- `query_structured_data`：查结构化指标
- `synthesize_brief_answer`：生成简短指标答复

### 3.3 当前系统已有的两类外部上下文接口

当前外部上下文检索已经天然拆成两类接口：

- 新闻搜索 `event_search`
  - 当前实现是 Bocha
- 公告搜索 `disclosure_search`
  - 当前实现是 CNInfo + SSE 聚合

所以接口层其实已经拆开了，当前真正还没拆开的，是：

- 什么时候只用新闻
- 什么时候只用公告
- 什么时候两者都用


## 4. 当前系统里不同 query 的实际执行路径

这一节只描述“现在代码里大体怎么走”，不讨论理想情况。

### 4.1 结构化指标查询

示例：

- `宁德时代 2024H1 利润多少`
- `贵州茅台 2024 营收是多少`

当前路径：

`router -> metric_lookup -> planner -> query_structured_data -> synthesize_brief_answer`

这条路径是合理的。

它不需要：

- 新闻搜索
- 公告搜索
- 事件背景
- 候选池

### 4.2 事件影响分析

示例：

- `红海局势升级对 A 股哪些板块有影响`
- `红海局势升级利好哪些 A 股航运股`
- `宁德时代扩产公告意味着什么`

当前路径大体都是：

`router -> event_impact_analysis -> planner -> collect_event_context -> analyze_targets -> retrieve_evidence -> synthesize_report`

也就是说，现在 planner 对 `event_impact_analysis` 基本采用固定四段链路。

其中：

- `collect_event_context` 内部才会再调用分类器
- 分类器输出 `event_primary / disclosure_primary / dual_primary`
- 然后只影响 `collect_event_context` 内部优先搜新闻还是公告

这会带来一个问题：

- 问“哪些板块”的 query，往往不需要 `analyze_targets`
- 问“某公司公告意味着什么”的 query，往往也不需要候选池
- 但当前系统会统一多走很多步

### 4.3 证据追问

示例：

- `中远海能受益的依据是什么`
- `把宁德时代扩产逻辑的证据展开`

当前路径：

`router -> evidence_lookup -> planner -> retrieve_evidence -> synthesize_report`

这条路径整体是合理的，因为这类 query 的目标就是补证据。


## 5. 当前系统里已经有的分类器在做什么

当前检索策略分类器只在 `intent = event_impact_analysis` 时才有意义。

它的 3 个 label 是：

- `event_primary`
- `disclosure_primary`
- `dual_primary`

业务含义不是“最终回答类型”，而是“外部上下文优先从哪里拿”：

- `event_primary`
  - 事件新闻优先
- `disclosure_primary`
  - 公司公告优先
- `dual_primary`
  - 事件新闻 + 公司公告都重要

注意：

- 这 3 个 label 当前更像“检索策略”
- 还没有真正变成“执行路径”

但在我们这次讨论里，已经收敛出一个更实用的方向：

- 第一阶段不新增 router 字段
- 直接让这 3 个 label 上升为 planner 编排 stage 的输入信号


## 6. 理想中的 query 类型与链路

为了让链路更清晰，这里不再只看顶层 intent，而是看“用户到底在问什么类型的问题”。

我们这次讨论收敛出的理想 query 类型有 5 类。

### 6.1 `metric_lookup`

示例：

- `宁德时代 2024H1 利润多少`
- `贵州茅台 2024 营收是多少`

目标：

- 要一个明确的结构化数值

理想路径：

`router -> metric_lookup -> query_structured_data -> synthesize_brief_answer`

不需要：

- 新闻
- 公告
- 事件背景
- 候选池
- 公司证据检索

### 6.2 `event_context_answer`

示例：

- `红海局势最近怎么了`
- `红海局势升级对 A 股哪些板块有影响`

目标：

- 要事件背景
- 要事件演化
- 要影响链条
- 可能要板块级归纳
- 但不一定要收缩到具体公司

理想路径：

`router -> event_impact_analysis -> classifier -> collect_event_context -> synthesize_event_answer`

这类 query 的关键点：

- 搜完事件背景后通常就可以答
- 没必要强行走 `analyze_targets`
- 也没必要默认继续 `retrieve_evidence`

### 6.3 `target_discovery`

示例：

- `红海局势升级利好哪些 A 股航运股`
- `关税升级对哪些消费电子公司冲击更大`

目标：

- 不是只理解事件
- 而是要从事件进一步收缩到具体板块 / 公司 / 标的

理想路径：

`router -> event_impact_analysis -> classifier -> collect_event_context -> analyze_targets -> retrieve_evidence -> synthesize_report`

这类 query 的关键点：

- `analyze_targets` 在这里是有必要的
- `retrieve_evidence` 也有必要
- 这是当前四段链路最合理的适用场景

### 6.4 `disclosure_interpretation`

示例：

- `宁德时代扩产公告意味着什么`
- `某公司业绩预告是否释放积极信号`
- `某公司回购公告怎么看`

目标：

- 解读公司公告 / 业绩预告 / 公司内生事件
- 重点是正式披露了什么、释放了什么信号

理想路径：

`router -> event_impact_analysis -> classifier -> collect_event_context -> retrieve_evidence -> synthesize_report`

这类 query 的关键点：

- 目标公司通常已经比较明确
- 重点是公告和公司证据
- 一般不需要 `analyze_targets`

### 6.5 `evidence_lookup`

示例：

- `中远海能受益的依据是什么`
- `把这个判断的证据展开`

目标：

- 直接索要证据

理想路径：

`router -> evidence_lookup -> retrieve_evidence -> synthesize_report`

这类 query 的关键点：

- 不需要事件背景
- 不需要候选池
- 重点是证据补全和证据组织


## 7. 理想中的“分类器 label -> stage 路径”关系

我们最终讨论后更倾向的第一阶段方案是：

- 不给 router 新增字段
- 只有 `intent = event_impact_analysis` 时，调用分类器
- planner 根据分类器输出的 label 编排 stage

在当前这批 query 里，3 个 label 和理想路径的关系可以先收敛成下面这样：

### 7.1 `event_primary`

适合：

- `红海局势最近怎么了`
- `红海局势升级对 A 股哪些板块有影响`

理想路径：

`collect_event_context -> synthesize_event_answer`

### 7.2 `disclosure_primary`

适合：

- `宁德时代扩产公告意味着什么`
- `某公司业绩预告是否释放积极信号`

理想路径：

`collect_event_context -> retrieve_evidence -> synthesize_report`

### 7.3 `dual_primary`

适合：

- `红海局势升级利好哪些 A 股航运股`

理想路径：

`collect_event_context -> analyze_targets -> retrieve_evidence -> synthesize_report`

备注：

- 这说明分类器完全可以不只影响“搜什么源”
- 在第一阶段，它已经可以直接影响“后面要不要继续跑哪些 stage”


## 8. 为什么新闻搜索和公告搜索应该逻辑拆开

当前系统里新闻搜索和公告搜索已经是两个接口，所以这里讨论的不是“接口要不要拆”，而是“执行策略要不要拆”。

答案是：有必要按场景拆。

### 8.1 只搜新闻就够的场景

示例：

- `红海局势最近怎么了`
- `美国加征关税会影响哪些板块`

这类 query 更关心：

- 近期发生了什么
- 事件怎么演化
- 影响传导链是什么

这类场景里：

- 新闻是主源
- 公告不是主源

### 8.2 只搜公告就够的场景

示例：

- `宁德时代扩产公告意味着什么`
- `某公司业绩预告是否释放积极信号`

这类 query 更关心：

- 公司正式披露了什么
- 释放了什么边际信号
- 标题、措辞、数字、时间点意味着什么

这类场景里：

- 公告是主源
- 新闻容易成为噪音

### 8.3 新闻和公告都要的场景

示例：

- `红海局势升级利好哪些 A 股航运股`

这类 query 同时需要：

- 事件背景
- 公司层面验证

这类场景里：

- 新闻和公告都需要


## 9. 关键中间字段应该承载什么

这一节只写业务上应该怎么理解，不按底层代码逐行展开。

### 9.1 `RouterResult`

建议业务理解：

- `intent`
  - 这是第一层大分流
- `follow_up_type`
  - 这是多轮场景的附加信号
- `entities`
  - 这是本轮 query 抽出来的关键语义实体
- `constraints`
  - 这是 planner 可消费的执行提示

当前不建议第一步就给 router 再加新字段。

### 9.2 分类器输出 `strategy_payload`

建议至少保留：

- `strategy: str`
  - 值域：`event_primary | disclosure_primary | dual_primary`
- `confidence: str`
  - 值域：`high | medium | low`
- `reason: str`
  - 调试和回放用

业务理解：

- 这是“事件类问题该优先从哪类外部上下文切入”

### 9.3 `Plan`

建议业务理解：

- `plan_id: str`
- `intent: str`
- `stages: list[str]`
- `stage_constraints: dict[str, object]`
- `response_mode: str`

其中最关键的是：

- `stages`
  - 决定实际执行链路
- `stage_constraints`
  - 决定每个 stage 的预算、模式和提示

### 9.4 `collect_event_context` 的核心输出 `event_context`

这层不建议做成太重的结构化 schema。

我们这次讨论更倾向一个“轻结构”：

```json
{
  "event": "红海局势升级",
  "themes": ["航运", "油运"],
  "time_scope": "recent",
  "context_summary": "红海局势近期升级，多家船公司继续绕行，航线时效拉长，运价存在上行压力。",
  "supporting_points": [
    "部分航线继续绕行",
    "运价和运输时效受到影响"
  ],
  "evidence_refs": ["bocha:item_001", "cninfo:123456"],
  "candidate_hints": ["航运", "港口", "油运"]
}
```

这里最重要的是：

- `context_summary`
  - 给后续 LLM 看的主内容
- `supporting_points`
  - 给后续 LLM 和前端 trace 看
- `evidence_refs`
  - 用于回溯来源
- `candidate_hints`
  - 仅在需要继续做标的发现时使用

### 9.5 `analyze_targets` 的输出

这一层和 `event_context` 不一样，应该继续保持结构化。

建议保留：

- `target_scope: list[str]`
- `ranked_targets: list[object]`
- `open_questions: list[str]`
- `confidence: str`
- `analysis_mode: str`

其中 `ranked_targets` 的单项建议至少包括：

- `target: str`
- `target_type: str`
- `impact_direction: str`
- `reasoning_summary: str`
- `confidence: str`

业务理解：

- 这一步不是最终回答
- 这一步只是把“事件背景”收缩成“值得继续补证据的对象”

### 9.6 `retrieve_evidence` 的输出

业务理解：

- 这一步的结果是公司/公告/内部证据块集合
- 不负责事件背景补全
- 只负责围绕目标补证据

所以它输出里最关键的不是摘要，而是：

- `retrieval_result`
- `evidence_refs`


## 10. 最终喂给 LLM 的内容粒度应该是什么

这是我们这次讨论里非常重要的一个结论。

结论不是“只喂标题”，也不是“直接喂全文”，而是：

- 标题级别：用于召回、粗筛、排序
- 正文摘要级别：用于主推理
- 正文片段级别：用于校验和引用

对应到系统里：

- `collect_event_context`
  - 最适合输出一个自然语言 `context_summary`
- `analyze_targets`
  - 继续消费这个摘要和候选信息
- `synthesize_event_answer / synthesize_report`
  - 再基于事件摘要和证据完成回答

所以事件背景层更适合：

- “轻结构 + 摘要 string”

而不是：

- 非常重的 rigid schema


## 11. 当前 router 的主要风险点

### 11.1 规则 router 对事件/公告边界判断还比较脆

例如：

- `某公司业绩预告是否释放积极信号`

这种 query 在当前规则 router 下有两个风险：

- 可能直接识别不出来
- 如果带了具体公司名和 `净利润/营收` 等词，也可能被错导到 `metric_lookup`

这说明：

- 规则 router 在“查数值”与“解读公告”之间的边界处理仍然偏弱

### 11.2 router 后续更适合演进到 LLM 主判

我们这次讨论后的倾向是：

- 中长期 router 应该切到 LLM 主判
- 规则保留为 guardrail / fallback

但这是后续演进方向，不是这份文档的近期重点。


## 12. 这次讨论收敛后的最小改造方向

如果只按这次会话讨论出的共识，近期最小改造可以收敛成下面几条：

### 12.1 不先改 router 字段

第一阶段不必给 `RouterResult` 增加新的业务枚举字段。

### 12.2 只在 `intent = event_impact_analysis` 时调用分类器

分类器仍然只服务事件类问题。

### 12.3 让分类器 label 直接参与 planner 编排

让 planner 根据：

- `event_primary`
- `disclosure_primary`
- `dual_primary`

来决定后续 stage。

### 12.4 把事件类 query 从“固定四段链路”改成“按问题类型最小化执行”

推荐的近期映射：

- `event_primary`
  - `collect_event_context -> synthesize_event_answer`
- `disclosure_primary`
  - `collect_event_context -> retrieve_evidence -> synthesize_report`
- `dual_primary`
  - `collect_event_context -> analyze_targets -> retrieve_evidence -> synthesize_report`

### 12.5 `collect_event_context` 保持轻结构输出

核心是：

- `context_summary`
- `supporting_points`
- `evidence_refs`
- `candidate_hints`

不要把它做成过重的 rigid schema。


## 13. 最后一页：最实用的总表

| 用户问题类型 | 典型 query | 是否需要新闻 | 是否需要公告 | 是否需要候选池 | 是否需要公司证据 | 理想链路 |
| --- | --- | --- | --- | --- | --- | --- |
| `metric_lookup` | 宁德时代 2024H1 利润多少 | 否 | 否 | 否 | 否 | `query_structured_data -> synthesize_brief_answer` |
| `event_context_answer` | 红海局势最近怎么了 | 是 | 视情况 | 否 | 否 | `collect_event_context -> synthesize_event_answer` |
| `event_context_answer` | 红海局势升级对 A 股哪些板块有影响 | 是 | 视情况 | 否 | 否 | `collect_event_context -> synthesize_event_answer` |
| `target_discovery` | 红海局势升级利好哪些 A 股航运股 | 是 | 是 | 是 | 是 | `collect_event_context -> analyze_targets -> retrieve_evidence -> synthesize_report` |
| `disclosure_interpretation` | 宁德时代扩产公告意味着什么 | 否或弱需要 | 是 | 否 | 是 | `collect_event_context -> retrieve_evidence -> synthesize_report` |
| `disclosure_interpretation` | 某公司业绩预告是否释放积极信号 | 否或弱需要 | 是 | 否 | 是 | `collect_event_context -> retrieve_evidence -> synthesize_report` |
| `evidence_lookup` | 中远海能受益的依据是什么 | 否 | 否 | 否 | 是 | `retrieve_evidence -> synthesize_report` |


## 14. 这份文档的使用方式

后面如果再讨论链路，可以优先先回答这 4 个问题：

1. 这条 query 到底是在要数值、背景、板块、标的，还是证据？
2. 外部上下文应以新闻为主，公告为主，还是双源都要？
3. 这次是否真的需要 `analyze_targets`？
4. 这次最终应该给 LLM 喂的是事件摘要，还是公司证据，还是两者都要？

只要这 4 个问题先答清楚，后面的 stage 编排就不会再轻易失控。
