# 待办：方案C — 插入 reflect_and_requery stage（真 ReAct 多轮工具调用）

## 背景

当前 agent 架构是**固定 stage 流水线**（stage_planner 查表 → orchestrator 顺序执行），不支持 LLM 动态决定下一步调用什么工具。在衍生指标场景（如"毛利率"未命中）下，当前用 `_DERIVED_METRICS` 规则表硬编码公式计算，扩展性差且不符合 agent 理念。

用户希望实现真正的 agent 反思：**未命中 → LLM 反思需要哪些原料指标 → 自动补查 → 计算或重新回答**。

## 目标

在 `query_structured_data` 与 `synthesize_answer` 之间插入 `reflect_and_requery` stage，支持多轮工具调用，让 LLM 参与决策"查什么、怎么算"。

## 当前架构限制（需突破）

1. **stage_planner 是纯查表**：`resolve_stages(router_result, strategy_payload)` 根据 `(intent, strategy)` 返回固定 stage 列表，无 LLM 规划。
   - 位置：`backend/src/finsight_agent/control_plane/orchestrator/stage_planner.py`
   - metric_lookup 路径固定为 `[QUERY_STRUCTURED_DATA, SYNTHESIZE_ANSWER]`

2. **orchestrator 顺序执行，不支持动态追加 stage**：
   - 位置：`backend/src/finsight_agent/control_plane/orchestrator/service.py` 的 `execute` 方法
   - `for stage_name in stages:` 循环只读 stages 列表，不追加

3. **STAGE_RUNNERS 是 5 个固定 stage 的字典**：
   - 位置：`backend/src/finsight_agent/control_plane/orchestrator/stage_runners/__init__.py`
   - 现有：collect_event_context / analyze_targets / query_structured_data / retrieve_evidence / synthesize_answer

4. **brief_answer writer 只能拿单个 structured_result**：
   - 位置：`backend/src/finsight_agent/control_plane/orchestrator/stage_runners/synthesize_answer.py::_synthesize_brief`
   - prompt 明确禁止编造数值，无法触发二次查询

## 实施步骤

### Step 1: 新增 StageName 枚举
- 文件：`shared/enums/stage_name.py`
- 新增：`REFLECT_AND_REQUERY = "reflect_and_requery"`

### Step 2: 新增 reflect_and_requery stage runner
- 文件：`backend/src/finsight_agent/control_plane/orchestrator/stage_runners/reflect_and_requery.py`（新建）
- 逻辑：
  1. 读取 `execution_state["query_structured_data"]` 的 `structured_result`
  2. 若 `is_degraded=false`（已命中）：直接 no-op，返回空结果
  3. 若 `is_degraded=true`（未命中）：调用 LLM 反思
     - LLM 输入：query + company + metric + time_scope + 已知指标库 schema（metric_name 列表）
     - LLM 输出：`{need_requery: true, ingredient_metrics: ["revenue", "operating_cost"], reasoning: "毛利率需从收入和成本计算"}`
  4. 若 `need_requery=true`：逐个调用 `StructuredDataService.query_metric_lookup` 查原料指标
  5. 把原料结果累积进 `execution_state["reflect_and_requery"]` 的 `output_payload`
  6. （可选）LLM 二次反思：原料是否齐全？是否需要再查？最多 N 轮（建议 N=2）

### Step 3: 注册新 stage runner
- 文件：`backend/src/finsight_agent/control_plane/orchestrator/stage_runners/__init__.py`
- 在 STAGE_RUNNERS 字典加入 `StageName.REFLECT_AND_REQUERY.value: run_reflect_and_requery_stage`

### Step 4: 修改 stage_planner
- 文件：`backend/src/finsight_agent/control_plane/orchestrator/stage_planner.py`
- 修改 `_build_metric_lookup_plan`：stages 改为 `[QUERY_STRUCTURED_DATA, REFLECT_AND_REQUERY, SYNTHESIZE_ANSWER]`

### Step 5: 修改 synthesize_answer._synthesize_brief
- 文件：`backend/src/finsight_agent/control_plane/orchestrator/stage_runners/synthesize_answer.py`
- 读取 `execution_state` 里的 `reflect_and_requery` 结果（若有）
- 把"主结果 + 反思补查结果列表"都传给 LLM context
- 允许 LLM 基于多个原料指标计算并回答

### Step 6: 扩展 brief_answer.txt prompt
- 文件：`backend/src/finsight_agent/capabilities/reporting/prompts/brief_answer.txt`
- 新增字段说明：`ingredient_results`（反思补查的原料指标列表）
- 允许 LLM 表达"基于X和Y计算出Z"
- 放宽"不得编造数值"约束：允许基于 ingredient_results 做数学计算

### Step 7: 处理 orchestrator 条件分支
- 文件：`backend/src/finsight_agent/control_plane/orchestrator/service.py`
- 当前 for 循环不支持 stage 间条件跳转
- 方案：让 reflect_and_requery 在命中时直接 no-op（返回空 StageExecutionResult），synthesize_answer 检测空结果则走原逻辑
- 这样不需要改 orchestrator 的执行模型

## 关键设计决策

1. **LLM 反思的频率**：建议最多 2 轮（主查询 + 1 次反思补查），避免无限循环
2. **原料查询的并发**：ingredient_metrics 可批量查询，但当前 query_metric_lookup 是单次，可加批量接口
3. **公式计算位置**：让 LLM 在 synthesize_answer 阶段自己算（LLM 有数学能力），还是在 reflect 阶段算好传过去？
   - 推荐：LLM 在 synthesize_answer 算，reflect 只负责"决定查什么"
4. **回退策略**：若 LLM 反思失败（JSON 解析错误等），回退到当前 `_try_derived_metric` 规则计算

## 验证标准

- 茅台毛利率：LLM 反思后查 revenue + operating_cost，计算结果 ≈ 91.6%
- 比亚迪净利率：LLM 反思后查 revenue + net_profit，计算结果 ≈ 5.4%
- 宁德时代资产负债率：LLM 反思后查 total_liabilities + total_assets（若数据存在）
- 直接指标（如净利润）：reflect stage no-op，走原逻辑，无性能损耗
- 未命中且非衍生指标：reflect stage LLM 反思后说"无法计算"，走 degraded 路径

## 关联文件

- `backend/src/finsight_agent/control_plane/orchestrator/stage_planner.py`
- `backend/src/finsight_agent/control_plane/orchestrator/service.py`
- `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/__init__.py`
- `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/query_structured_data.py`
- `backend/src/finsight_agent/control_plane/orchestrator/stage_runners/synthesize_answer.py`
- `backend/src/finsight_agent/capabilities/structured_data/service.py`（现有 _try_derived_metric 作为回退）
- `backend/src/finsight_agent/capabilities/reporting/prompts/brief_answer.txt`
- `shared/enums/stage_name.py`

## 临时方案（当前已实现）

在方案C完成前，`StructuredDataService._try_derived_metric` 提供基于规则表 `_DERIVED_METRICS` 的衍生指标计算（毛利率/净利率/ROE/资产负债率），作为临时方案。方案C完成后可保留作为 LLM 反思失败的回退路径。
