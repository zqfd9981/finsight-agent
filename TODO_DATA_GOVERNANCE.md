# 待办：数据治理重构 — time_scope/period_end 数据模型重建

## 背景

当前 `metric_records` 表的 `time_scope` 字段存的是**年报表格的表头原文**（如"2024年"/"期末余额"/"本期"/"上期"等20+种取值），导致：

1. **同一个值重复存储**：格力货币资金1139亿存了2次（time_scope='2024年'主表 + time_scope='期末余额'注释区表）
2. **period_end 不可靠**：期初余额的 period_end 标成 2024-12-31（应为 2024-01-01 或 2023-12-31）
3. **time_scope 有 20+ 种取值**：无法用规则统一，查询时字符串精确匹配经常漏判
4. **查询语义不明确**：用户说"2024年末货币资金"，不知道该查 time_scope='2024年' 还是 '期末余额'

## 根因

TableExtractor 提取时直接把表头原文存进 time_scope，只做了部分归一化（"2024年度"→"2024年"）。period_end 从表头日期解析，但期初/期末混在同一张表时容易标错。

## time_scope 当前取值分布（5 类，20+ 种）

| 类别 | 取值示例 | 数量 | 含义 |
|---|---|---|---|
| 年份格式 | `2024年` / `2023年` / `2024年度` | 84000+ | 表头写年份，最常见 |
| 期末/期初 | `期末余额` / `期初余额` / `年末余额` / `年初余额` | 45000+ | 资产负债表时点表 |
| 本期/上期 | `本期` / `上期` / `本期金额` / `上期金额` | 16000+ | 现金流量表期间表 |
| 变动表 | `本年增加` / `本年减少` / `期末账面余额` | 1000+ | 注释区变动表 |
| 繁体/其他 | `二零二四年` / `期末` / `期初` | 1000+ | 港交所双语年报等 |

## 目标数据模型

废弃 time_scope 字符串，改用结构化字段：

```sql
-- 新增字段（或替换 time_scope）
period_end       TEXT NOT NULL,   -- 时点或期间结束日 YYYY-MM-DD（修复期初余额标错问题）
period_type      TEXT NOT NULL,   -- year_end | year_start | quarter_end | interim | period_change
statement_type   TEXT NOT NULL,   -- consolidated | parent_only（已有，需确保一致）
```

**period_type 语义**：
- `year_end`：年末时点（资产负债表期末、利润表年度数、现金流量表本期）
- `year_start`：年初时点（资产负债表期初）
- `quarter_end`：季末时点（三季度报等，当前无）
- `interim`：中期（半年报，当前无）
- `period_change`：变动数（注释区变动表的"本年增加"/"本年减少"）

## 实施步骤（工作量大，建议分阶段）

### 阶段 1：DB schema 升级 + 历史数据迁移
- 新增 period_type 字段
- 写迁移脚本：根据 time_scope + source_section 推断 period_type
  - `2024年` / `2024年度` + income_statement → `year_end`
  - `期末余额` / `年末余额` + balance_sheet → `year_end`
  - `期初余额` / `年初余额` + balance_sheet → `year_start`
  - `本期` / `本期金额` + cash_flow_statement → `year_end`
  - `上期` / `上期金额` + cash_flow_statement → `year_end`（但 period_end 应为上一年）
  - `本年增加` / `本年减少` + notes → `period_change`
- 修复 period_end：期初余额的 period_end 改为上一年的 12-31

### 阶段 2：TableExtractor 提取逻辑升级
- 提取时直接输出 period_type，不再存 time_scope 原文
- 根据 source_section + 表头关键词推断 period_type
- period_end 解析加强：期初余额时 period_end = 上一期期末

### 阶段 3：Repository 查询逻辑简化
- 查询用 `period_end + period_type + statement_type` 精确匹配
- 删除 `_normalize_time_scope_for_query` / `_query_description_scope` / time_scope LIKE 前缀等规则
- 查询"2024年末货币资金" = `period_end='2024-12-31' AND period_type='year_end' AND statement_type='consolidated'`

### 阶段 4：去重
- 同一个 value 不再因为 time_scope 不同而重复存储
- 主表和注释区表的重复值用 source_caption 区分，但 period_end + period_type + statement_type + metric_name 相同时视为同一数据点

## 关联文件

- `backend/src/finsight_agent/capabilities/structured_data/models.py`（MetricRecord 加 period_type 字段）
- `backend/src/finsight_agent/capabilities/structured_data/repository.py`（schema + 查询逻辑）
- `backend/src/finsight_agent/capabilities/structured_data/table_extractor.py`（提取时输出 period_type）
- `var/data/structured_data/metrics.db`（历史数据迁移）

## 与其他 TODO 的关联

- **[TODO_ROUTER_SEMANTIC.md](TODO_ROUTER_SEMANTIC.md)**：router 语义理解方案输出 period_end 日期，本方案提供 period_type 字段配合查询
- **[TODO_AGENT_REACT.md](TODO_AGENT_REACT.md)**：方案 C 反思 stage 用 period_end + period_type 查原料指标
- 三个 TODO 可合并成一次大的架构升级

## 当前临时方案（已实现，待替换）

- `_normalize_time_scope_for_query` 正则归一化（'2024年末'→'2024年'）
- `find_best_match` 3 层精确/前缀匹配（time_scope 字符串）
- 12/14 指标查询命中，2 个未命中是 router LLM 分类不稳定（非 time_scope 问题）

## 当前不做的理由

- 数据治理需改 DB schema + TableExtractor + repository + 历史数据迁移，工作量大
- 当前 12/14 命中率（86%）已可接受，剩余 2 个未命中是 router 问题非数据问题
- 等 router 语义理解方案实施后，查询用 period_end 绕过 time_scope，能进一步改善
- 真正的数据治理留到后续迭代
