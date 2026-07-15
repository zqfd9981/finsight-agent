# 已完成：Router 语义理解统一方案 — 用 LLM 理解代替规则归一化

> **状态**：已完成（2026-07-15）
> **实施范围**：Step 1（router prompt）+ Step 2（消除查询阶段 normalizer 依赖）+ Step 3（period_end 日期查询）
> **保留项**：normalizer 作为旧格式 fallback（新格式下 metric 已是 standard_name，normalizer 原样返回）；_normalize_time_scope_for_query 作为旧格式 fallback

## 背景

当前 agent 问答链路有 3 个环节用"规则"做归一化，永远覆盖不了所有用户表述：

1. **Router prompt 用列表枚举公司名/指标名** → 不是语义理解，是关键词匹配
2. **MetricNormalizer 用字典查找** → 4000+ 条 alias 仍覆盖不了"营收"vs"营业收入"等口语
3. **time_scope 用正则提取年份** → 无法处理"去年""三季度末""最新"等语义表述

根本问题：**这些环节都应该用 LLM 做语义理解，而不是堆规则**。规则每加一条都是技术债，且永远有遗漏。

## 核心设计

把语义理解集中到 router LLM 一次性输出，下游全部用标准格式，消除所有规则归一化环节。

### 目标 RouterResult（entities 结构升级）

```json
{
  "intent": "metric_lookup",
  "entities": {
    "company": {
      "raw": "格力电器",
      "standard_name": "格力电器",
      "stock_code": "000651"
    },
    "metric": {
      "raw": "货币资金",
      "standard_name": "cash_and_equivalents",
      "metric_type": "direct"
    },
    "time_scope": {
      "raw": "2024年末",
      "period_end": "2024-12-31",
      "fiscal_year": 2024
    }
  }
}
```

**关键变化**：
1. **company 输出 stock_code** — LLM 理解"格力电器"→000651，DB 用 code 精确匹配，不再依赖 company_name 字符串匹配
2. **metric 直接输出 standard_name** — LLM 理解"经营活动现金流量净额"→`net_operating_cash_flow`，不再需要 normalizer 环节
3. **time_scope 输出 period_end 日期** — LLM 理解"去年"→2024-12-31，不再需要正则归一化
4. **metric_type 标识 direct/derived** — LLM 理解"毛利率"是衍生指标，下游直接走衍生计算

## 实施步骤

### Step 1: 改 router prompt（语义描述代替列表枚举）

**metric_lookup 判定条件**（从列表枚举改为语义描述）：
```
判定为 metric_lookup 的语义条件（三个都必须满足）：
1. query 明确指向某家具体上市公司（无论公司名如何表述，
   只要能识别出是哪家 A 股上市公司即可，包括简称、全称、股票代码）
2. query 明确询问某个可量化的财务指标（包括但不限于：
   资产负债表科目、利润表科目、现金流量表科目、
   基于这些科目的衍生比率如毛利率/净利率/ROE/资产负债率）
3. query 包含查询具体数值的意图（多少、是多少、多大、几何）

不要因为公司名或指标名不在某个列表中就拒绝判为 metric_lookup —
用语义理解判断，不是关键词匹配。
```

**entities 输出要求**（加标准格式）：
```
- company: {"raw": "用户原文", "standard_name": "DB 中的公司名", "stock_code": "6 位代码"}
- metric: {"raw": "用户原文", "standard_name": "标准英文 key", "metric_type": "direct|derived"}
- time_scope: {"raw": "用户原文", "period_end": "YYYY-MM-DD 格式", "fiscal_year": 数字年份}

standard_name 参考表（common 指标）：
  净利润→net_profit, 营业收入→revenue, 货币资金→cash_and_equivalents,
  存货→inventory, 商誉→goodwill, 研发费用→rd_expenses,
  总资产→total_assets, 总负债→total_liabilities, 所有者权益→total_equity,
  经营活动现金流量净额→net_operating_cash_flow...
  （未列出的指标，用你的会计知识推断 standard_name，保持 snake_case 英文命名）

period_end 理解规则：
  "2024 年"/"2024 年末"/"去年" → 上一年 12 月 31 日
  "2024 年三季度" → 2024-09-30
  "最新"/"最近" → 当前最近已披露年报的 period_end
```

### Step 2: 消除查询阶段的 normalizer

- `structured_data_service.query_metric_lookup` 直接用 router 输出的 standard_name 查询，跳过 normalizer
- normalizer 只在数据入库时用（提取阶段），查询阶段不再需要
- `metric_aliases.json` 仍保留作为提取阶段的归一化映射表

### Step 3: 消除 time_scope 归一化

- repository 直接用 period_end 日期查询，不再用 time_scope 字符串匹配
- 删除 `_normalize_time_scope_for_query` 和 `_query_description_scope`
- 只保留 `_query_latest_or_date`（latest + 日期格式）
- time_scope 字段在 DB 里仍保留（提取时记录），但查询时不再用它做匹配条件

## 关联文件

- `backend/src/finsight_agent/control_plane/router/prompts/system.txt`（Step 1）
- `backend/src/finsight_agent/control_plane/router/schema.py`（entities 解析适配新结构）
- `backend/src/finsight_agent/capabilities/structured_data/service.py`（Step 2）
- `backend/src/finsight_agent/capabilities/structured_data/repository.py`（Step 3）

## 与方案 C 的关联

本方案与 [方案 C ReAct 反思](TODO_AGENT_REACT.md) 有关联：
- router 输出 standard_name 后，方案 C 的 reflect stage 能直接用 standard_name 查原料指标
- router 输出 metric_type=derived 后，方案 C 能直接判断是否需要反思
- 两个方案可以合并成一次大的架构升级

## 验证标准

- 格力货币资金：router 输出 stock_code=000651 + standard_name=cash_and_equivalents + period_end=2024-12-31 → 直接命中 ✓
- 伊利现金流：router 输出 standard_name=net_operating_cash_flow（LLM 理解"经营活动现金流量净额"）→ 直接命中 ✓
- 比亚迪净利率：router 输出 metric_type=derived → 触发衍生计算 ✓
- "去年三季度净利润"：router 输出 period_end=2024-09-30 → 查询路径不报错（DB 无三季度数据是数据问题） ✓

## 实施记录（2026-07-15）

### 实际改动文件

1. **router/prompts/system.txt** — 重写 prompt：列表枚举改为语义条件判定 + 嵌套 entities 结构
2. **router/schema.py** — 新增 `_normalize_entities`：兼容新旧两种格式，统一输出嵌套对象 + 扁平字段
3. **orchestrator/stage_runners/query_structured_data.py** — 解包新 entities 嵌套结构，传递 company_code/metric_raw/metric_type/period_end
4. **capabilities/structured_data/models.py** — MetricQuery 新增 company_code + period_end 字段
5. **capabilities/structured_data/service.py** — 新增 company_code/metric_raw/metric_type 参数；metric_type=derived 直接走衍生计算；_DERIVED_METRICS 加英文 key 别名
6. **capabilities/structured_data/repository.py** — 新增 `_query_by_code_and_period`（company_code+period_end 精确查询）作为新格式优先路径；保留 `_query_legacy_fallback` + `_query_description_scope` 作为旧格式 fallback；新增 idx_code_period 索引
7. **orchestrator/stage_planner.py** — `_build_metric_lookup_plan` 用 period_end 优先，fallback 到 time_scope_raw
8. **session/extractor.py** — `_build_active_topic` + `_build_active_candidates` 用扁平字段 company_name/time_scope_raw/metric_raw
9. **orchestrator/stage_runners/retrieve_evidence.py** — time_scope 引用加 time_scope_raw + period_end fallback；新增 `_safe_str` 辅助函数处理 dict 格式
10. **orchestrator/stage_runners/collect_event_context.py** — time_scope 加 dict 格式防御性处理

### 设计决策

- **保留 normalizer 作为旧格式 fallback**：新格式下 metric 已是 standard_name（英文 key），normalizer.normalize(english_key) 原样返回，无副作用。旧格式（中文 metric）仍需 normalizer 归一化。
- **保留 _normalize_time_scope_for_query 作为旧格式 fallback**：新格式下 router 直接输出 period_end 日期，不走此函数。旧格式（描述字符串如"2024年末"）仍需归一化。
- **保留 _query_description_scope 作为旧格式 fallback**：新格式用 period_end 日期精确查询，旧格式用 time_scope 字符串匹配。
- **向后兼容**：所有改动都兼容旧格式 entities（扁平字符串），不会破坏现有 router LLM 输出。

### 测试结果

8/8 端到端测试通过：
- schema 新旧格式解析 ✓
- 格力货币资金（新格式 direct）→ 113900461797.94 元 ✓
- 伊利现金流（新格式 direct）→ 21739740393.38 元 ✓
- 比亚迪净利率（新格式 derived）→ 5.35% ✓
- 去年三季度净利润（period_end=2024-09-30）→ 查询路径不报错 ✓
- latest 查询 → 54006794 千元 ✓
- 旧格式 fallback → 54006794 ✓
- 宁德时代归母净利润（之前未命中的 case）→ 50744682 千元 ✓
