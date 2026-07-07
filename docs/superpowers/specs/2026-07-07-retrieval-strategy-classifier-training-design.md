# Retrieval Strategy Classifier Training Design

## 背景

截至 2026-07-07，FinSight 已经完成以下与事件链路相关的基础能力：

- `event_impact_analysis` 四阶段主链已可执行（`collect_event_context` → `analyze_targets` → `retrieve_evidence` → `synthesize_report`）
- 外部检索已拆成两层：
  - `EventSearchProvider`（Bocha，PR #11 落地）
  - `DisclosureSearchProvider`（巨潮 + 上交所）
- `DualSourceExternalContextRetriever` 已可消费分类器输出并按 plan 调两类 provider
- 事件评测框架已上线：`backend/src/finsight_agent/evaluation/event_eval/` 含 fixtures / replay runner / checks

当前控制面的核心决策点 `RetrievalStrategyClassifier` 仍只是 `StubRetrievalStrategyClassifier`：永远返回 `event_primary`，主链路实际从未被分类器驱动过。

```text
# retrieval_strategy_classifier.py:30
class StubRetrievalStrategyClassifier:
    def classify(self, *, query, router_payload, session_topic):
        del query, router_payload, session_topic
        return {
            "strategy": DEFAULT_RETRIEVAL_STRATEGY,
            "confidence": "low",
            "reason": "stub_fallback",
        }
```

这意味着：

- 主流程目前实际跑在 `event_primary`，从未走 `disclosure_primary` 或 `dual_primary`
- 即便 plan 层已经支持三种模式，模式切换功能未真正启用
- 一旦接入真实分类器，事件分析质量立刻可控可调，但也立刻引入对模型权重、推理依赖、回退语义的依赖

下一阶段的缺口是：**用真实训练的分类器替换 stub**，在不破坏现有 227 个测试与失败回退语义的前提下，让 `collect_event_context` 真正按 query 分布选择 `event_primary` / `disclosure_primary` / `dual_primary`。

## 目标

本设计目标是把 `RetrievalStrategyClassifier` 从 stub 升级到真实训练的分类器，重点包括：

- 定义清晰的训练 / 推理边界，让训练代码不污染主流程 import 路径
- 选型一个轻量、中文友好、可离线推理的中文编码器，本地微调 3 分类
- 沉淀 300+ 条有效标注样本，覆盖三类策略且分布尽量均衡
- 定义训练脚本、评测脚本、模型权重管理约定
- 定义运行时 `TrainedRetrievalStrategyClassifier`，协议层不变、失败回退等价于现状
- 让现有 4/4 `test_external_context_retriever` 测试以及更广的 227 个测试保持全绿

## 非目标

- 本轮不重写 `DualSourceExternalContextRetriever` / `ContextRetrievalPlanner` 主契约
- 本轮不动 `DisclosureSearchProvider`（巨潮 + 上交所）
- 本轮不动 Bocha 相关 `EventSearchProvider` Protocol（PR #11 已落地）
- 本轮不做 A/B 上线、不做 ONNX / TensorRT 推理加速、不引入 LLM judge 评测
- 本轮不把分类器升级为多任务（不独立训练 confidence / query_type / needs_local_rag）
- 本轮不要求首版 100% 准确率；目标是建立完整训练 → 评测 → 接入 → 兜底闭环

## 现状判断

### 协议层（完全不动）

`backend/src/finsight_agent/control_plane/orchestrator/retrieval_strategy_classifier.py`：

```python
RETRIEVAL_STRATEGIES = ("event_primary", "disclosure_primary", "dual_primary")
DEFAULT_RETRIEVAL_STRATEGY = "event_primary"

class RetrievalStrategyClassifier(Protocol):
    def classify(self, *, query, router_payload, session_topic) -> dict[str, str]: ...

class StubRetrievalStrategyClassifier:
    """训练分类器未就绪时的安全默认实现。"""
```

协议要求返回 `{strategy, confidence, reason}`，本轮不修改。

### 消费侧（只读 strategy 字段）

`backend/src/finsight_agent/control_plane/orchestrator/dual_source_context_retriever.py:47`：

```python
strategy_payload = self._classifier.classify(
    query=query,
    router_payload=router_payload,
    session_topic="",
)
plan = self._planner.build_plan(
    strategy_payload=strategy_payload,
    router_payload=router_payload,
)
```

`ContextRetrievalPlanner` 只读 `strategy_payload["strategy"]`，对 `confidence` / `reason` 完全不消费。这意味着：

- 协议字段名稳定即可，置信度映射策略可以独立演进
- `reason` 字段当前是 observability-only，下游不依赖

### 装配点（service.py:159）

```python
def _build_default_external_context_retriever() -> DualSourceExternalContextRetriever:
    return DualSourceExternalContextRetriever(
        classifier=StubRetrievalStrategyClassifier(),
        planner=ContextRetrievalPlanner(),
        event_search_provider=BochaEventSearchProvider(),
        disclosure_search_provider=OfficialDisclosureSearchProvider(),
    )
```

本轮改造此处的 `classifier=` 注入，新类加载失败时回退到 stub。

### 已有训练数据基础

- `backend/src/finsight_agent/evaluation/event_eval/fixtures/event_cases_v1.jsonl`：6 条事件评测样本，每条已带 `expected_strategy` 字段，可直接转 `label`
- 集成测试 / 单元测试里的代表性 query："红海局势升级利好哪些A股航运股" 等 ~3 条
- 设计稿 `2026-07-02-dual-source-event-context-retrieval-design.md` 第 4 节列出 ~10 条代表性 query

合计首日能直接复用的金标 ~20 条，离训练目标 300+ 条尚有 ~280 条缺口，需在本轮 PR 中由人工续标补齐。

## 设计原则

### 1. 训练代码与运行时代码物理隔离

训练脚本（依赖 `transformers + torch`）放 `backend/training/retrieval_strategy_classifier/`，不进入 `backend/src/` 的运行时 import 路径。主流程的 `import` 链不传染重型 ML 依赖。

### 2. 协议稳定，失败回退等价于现状

`RetrievalStrategyClassifier` Protocol / `StubRetrievalStrategyClassifier` 类定义 / `RETRIEVAL_STRATEGIES` 元组完全不变。任何推理异常 → 回退到 `StubRetrievalStrategyClassifier`，主流程行为与现状一致。

### 3. 单点重型依赖，不传染主流程

`transformers + torch` 仅在 `backend/training/` 训练子项目和 `trained_strategy_classifier.py` 这两个最小范围内引入。主流程其它模块继续 urllib-only 风格。

### 4. 模型权重不 commit 到 git

训练产物加入 `.gitignore`，通过 `download_pretrained.py` + `export_model.py` 在本地 / CI 拉取。

### 5. 离线评测作为 CI gate

`evaluate.py` 在固化 test 集上必须达到 accuracy ≥ 0.85，per-class F1 ≥ 0.80，否则 CI 红。这是分类器进入主流程的硬门槛。

## 架构总览

```
                       (离线，一次性 / 按需重跑)
    ┌─────────────────────────────────────────────────────┐
    │  backend/training/retrieval_strategy_classifier/    │
    │   ├─ data/                                          │
    │   │   ├─ raw/queries.jsonl        ← 原始问题         │
    │   │   ├─ labeled/labeled.jsonl    ← 人工确认标签      │
    │   │   └─ splits/{train,val,test}.jsonl              │
    │   ├─ scripts/                                       │
    │   │   ├─ build_dataset.py        ← 聚合 + 切分       │
    │   │   ├─ download_pretrained.py  ← 拉 StructBERT base│
    │   │   ├─ train.py                ← 微调             │
    │   │   ├─ evaluate.py             ← 离线评测 (CI gate)│
    │   │   └─ export_model.py         ← copy 到运行时路径 │
    │   ├─ artifacts/                                     │
    │   │   └─ classifier_v1/          ← 训练产物 (gitignore)│
    │   └─ data/LABELING.md            ← 标注手册          │
    └─────────────────────────────────────────────────────┘
                              │
                              │ export_model.py 复制到 (运行时)
                              ▼
    var/models/retrieval_strategy_classifier/v1/   ← 运行时加载路径 (gitignore)
                              │
                              │ RETRIEVAL_STRATEGY_MODEL_DIR
                              ▼
    backend/src/finsight_agent/control_plane/orchestrator/
        ├─ retrieval_strategy_classifier.py     ← Protocol + Stub（不变）
        ├─ trained_strategy_classifier.py      ← 新增：跑微调模型的实现
        └─ service.py                          ← 装配入口改造
```

## 组件设计

### 1. 训练子项目（`backend/training/retrieval_strategy_classifier/`）

#### 1.1 数据集 schema

每条样本 JSONL 一行：

```json
{
  "sample_id": "rsc_000001",
  "query": "红海局势升级利好哪些A股航运股？",
  "intent": "event_impact_analysis",
  "event": "红海局势升级",
  "themes": ["航运", "油运"],
  "target": "A股航运股",
  "time_scope": "recent",
  "session_topic": "",
  "label": "dual_primary",
  "label_source": "human_reviewed",
  "notes": "事件背景+A股标的影响"
}
```

字段说明：
- `sample_id`：稳定字符串标识（前缀 `rsc_`，6 位序号）
- `label` ∈ `{"event_primary", "disclosure_primary", "dual_primary"}`
- `label_source` ∈ `{"human_authored", "human_reviewed", "transferred_from_event_eval"}`
- 缺字段一律写空字符串或空列表，不省略 key

#### 1.2 序列化模板

喂给 StructBERT 的文本：

```text
[QUERY] {query} [INTENT] {intent} [EVENT] {event or "无"} [THEMES] {",".join(themes) or "无"}
[TARGET] {target or "无"} [TIME_SCOPE] {time_scope or "无"} [SESSION_TOPIC] {session_topic or "无"}
```

空字段一律填"无"，避免序列结构漂移。模板生成函数放在 `data/dataset.py`，训练和推理共用同一份实现。

#### 1.3 样本规模与分布

| 阶段 | 来源 | 数量 |
|---|---|---|
| A. 现有金标直转 | `event_eval/fixtures/event_cases_v1.jsonl` 6 条 + 集成测试 3 条 + 设计稿示例 12 条 | ~21 |
| B. 现有 query 人工补标签 | 从仓库历史 query 池挑选 | ~30 |
| C. 新写 query | 按 paraphrase 模板覆盖三类（含边界） | ~270 |
| **合计** | | **~321** |

类别分布目标：`event_primary` / `disclosure_primary` / `dual_primary` 各 ~100 条，任一类不得少于 80、不得超过 160。

#### 1.4 切分策略

按 `sample_id` 后两位整数哈希模 100：
- `< 10` → test
- `< 25` → val
- 其它 → train

切分结果固化到 `data/splits/{train,val,test}.jsonl`，可复现。训练脚本读固化切分，不在脚本内随机切。

#### 1.5 标注手册（`data/LABELING.md`）

主判定问题：
1. 这个 query 首先要不要先理解外部事件本身？
2. 这个 query 首先要不要先看公司/公告/披露？
3. 这两个是否都明显必需？

判定准则：
- 标 `event_primary`：不先理解事件就无法开展后续分析；query 没有明显单公司公告中心
- 标 `disclosure_primary`：query 本身就是公司内生事项；主语已明确落在公司披露
- 标 `dual_primary`：query 同时在问外部事件 + A 股/公司影响；任意单源都明显不够

边界处理：
- 模糊 query：按"首个必要检索动作"判断
- 同等必要 → 标 `dual_primary`
- 不允许 `unknown` / `other`

双人复核：首标 + 复标抽检 + 分歧入冲突池 + 最终裁决。

### 2. 训练脚本（`scripts/train.py`）

#### 2.1 模型

- 预训练起点：`alibaba-pai/structbert-base-zh`（StructBERT 中文 base，~400MB）
- 任务头：`AutoModelForSequenceClassification(num_labels=3)`
- label 索引映射：`{0: "event_primary", 1: "disclosure_primary", 2: "dual_primary"}`
- 映射约定固化到 `artifacts/classifier_v1/labels.json`，推理时严格按此反查

#### 2.2 训练参数

| 参数 | 值 | 备注 |
|---|---|---|
| `max_length` | 128 | 中文短文本平均 ~60 token，128 留余量 |
| `batch_size` | 16 | CPU 可行；GPU 16 也合适 |
| `epochs` | 5 | 配合早停 |
| `learning_rate` | 2e-5 | StructBERT 标准微调 lr |
| `warmup_ratio` | 0.1 | |
| `weight_decay` | 0.01 | |
| `seed` | 42 | 可复现 |

#### 2.3 早停

val accuracy 连续 2 个 epoch 不升 → 停止训练，回滚到最优 epoch 的 checkpoint。

#### 2.4 日志

每 epoch 打：
- `train_loss`
- `val_accuracy`
- `val_macro_f1`
- 当前学习率

#### 2.5 产物

`backend/training/retrieval_strategy_classifier/artifacts/classifier_v1/`：
- `config.json`（transformers 模型配置）
- `pytorch_model.bin`（或 `model.safetensors`）
- `tokenizer.json` / `tokenizer_config.json` / `vocab.txt`
- `labels.json`（`{0: "event_primary", 1: "disclosure_primary", 2: "dual_primary"}`）
- `training_meta.json`（训练参数 + val 指标 + 时间戳 + commit hash）

整个 `artifacts/` 加入 `.gitignore`。

### 3. 离线评测脚本（`scripts/evaluate.py`）

#### 3.1 评测输入

- `artifacts/classifier_v1/`（必选）
- `data/splits/test.jsonl`（必选）

#### 3.2 输出

- 整体 accuracy
- per-class precision / recall / F1
- confusion matrix（3×3）
- 与 stub baseline 对比：在同一 test 集上跑 `StubRetrievalStrategyClassifier`，对比策略命中率

#### 3.3 退出码

- test accuracy ≥ 0.85 → 0
- 否则 → 1（CI gate 红）

### 4. 运行时推理（`backend/src/finsight_agent/control_plane/orchestrator/trained_strategy_classifier.py`）

#### 4.1 接口签名

```python
class TrainedRetrievalStrategyClassifier:
    def __init__(
        self,
        *,
        model_dir: str | Path | None = None,
        confidence_margin_high: float = 0.40,
        confidence_margin_low: float = 0.15,
        fallback: RetrievalStrategyClassifier | None = None,
    ) -> None: ...

    def classify(self, *, query, router_payload, session_topic) -> dict[str, str]: ...
```

实现 `RetrievalStrategyClassifier` Protocol。

#### 4.2 加载策略（懒加载 + 一次性）

- `__init__` 不实际加载模型权重（避免 import 时报错、避免拖慢主流程启动）
- 第一次 `classify()` 调用时懒加载；之后缓存 `self._model` / `self._tokenizer`
- `model_dir` 优先级：`__init__` 参数 > `RETRIEVAL_STRATEGY_MODEL_DIR` 环境变量 > `var/models/retrieval_strategy_classifier/v1/` 默认路径
- 若 `model_dir` 不存在 / 加载失败：标记 `self._degraded = True`，后续 `classify()` 全部走 `fallback`

#### 4.3 输入构造

`classify()` 内：
1. 从 `router_payload.get("entities", {})` 抽 `event / themes / target / time_scope`
2. 用与训练一致的模板函数（共享 `data/dataset.py` 的逻辑）拼成单字符串
3. tokenizer encode → 模型 forward → softmax → numpy
4. 取 top-1 label → 通过 `labels.json` 反查字符串
5. margin = top1_prob - top2_prob → 映射 confidence

#### 4.4 置信度映射

| margin | confidence |
|---|---|
| `>= confidence_margin_high`（默认 0.40） | `high` |
| `confidence_margin_low <= margin < confidence_margin_high`（默认 0.15–0.40） | `medium` |
| `< confidence_margin_low`（默认 < 0.15） | `low` |

阈值通过构造参数暴露，方便后续调优，无需改代码。

#### 4.5 reason 字段

固定格式：`f"structbert:margin={margin:.3f};top1={top1_label};top2={top2_label}"`。

#### 4.6 失败处理矩阵

| 触发条件 | 行为 |
|---|---|
| `transformers` 未安装 | `__init__` 不导入；首次 `classify()` 检测 → log warning → 切 fallback |
| 模型权重未下载（model_dir 缺失） | `__init__` 不报错；首次 `classify()` 检测 → log warning → 切 fallback |
| tokenizer 编码失败 | catch → fallback；log 一行 |
| 模型 forward 异常 | catch → fallback；log 一行 |
| 输出 label 不在合法集 | catch → fallback；log 一行 |
| 单次推理 > 500ms（兜底超时） | catch → fallback；log 一行 |
| 任何其他 Exception | catch + log → fallback |

`fallback` 默认是 `StubRetrievalStrategyClassifier`，行为与现状完全一致。

#### 4.7 单次推理开销预估

- 模型加载：~2-3s（一次性，懒加载）
- 单次推理（CPU，max_len=128）：~30-80ms
- 不阻塞主流程：每次 `collect_event_context` 只调用一次 classify

### 5. 主流程装配（`service.py` 改造）

#### 5.1 改动范围

```python
def _build_default_external_context_retriever() -> DualSourceExternalContextRetriever:
    return DualSourceExternalContextRetriever(
        classifier=TrainedRetrievalStrategyClassifier(
            fallback=StubRetrievalStrategyClassifier(),
        ),
        planner=ContextRetrievalPlanner(),
        event_search_provider=BochaEventSearchProvider(),
        disclosure_search_provider=OfficialDisclosureSearchProvider(),
    )
```

#### 5.2 不变量

- `StubRetrievalStrategyClassifier` 类定义完全不变
- `RetrievalStrategyClassifier` Protocol 不变
- `DualSourceExternalContextRetriever` 构造签名不变
- `ContextRetrievalPlanner` 不变

#### 5.3 trace / observability

`DualSourceExternalContextRetriever.retrieve_event_context()` 的 `source_status` 字典增量三个键：

| 键 | 值 | 含义 |
|---|---|---|
| `strategy_reason` | 透传 classifier 输出 reason | 调试信号 |
| `strategy_confidence` | 透传 confidence | 调试信号 |
| `strategy_source` | `"trained"` 或 `"stub_fallback"` | 标明本次走的是模型还是兜底 |

`StageObservation` 协议不动。

### 6. 测试策略

#### 6.1 现有测试必须保持绿

| 测试 | 现状 | 改动 |
|---|---|---|
| `test_strategy_labels_and_default_are_stable` | 断言 stub 返回 `event_primary/low/stub_fallback` | **不动**（stub 行为不变） |
| `DualSourceExternalContextRetrieverTest`（2 个） | 用本地 `_StubClassifier` 注入 | **不动**（绕开装配路径） |
| `test_service_builds_dual_source_external_context_retriever_by_default` | 断言默认装配 `DualSourceExternalContextRetriever` | **不动**（类名不变） |

#### 6.2 新增单测（`tests/unit/test_trained_strategy_classifier.py`）

| 测试 | 验证内容 |
|---|---|
| `test_uses_fallback_when_model_dir_missing` | model_dir 不存在 → fallback |
| `test_classify_returns_valid_strategy_label_after_lazy_load` | 模型 mock 加载成功后，输出在合法集 |
| `test_confidence_maps_to_three_tiers` | 验证 margin → confidence 三档映射 |
| `test_classify_handles_empty_router_payload` | router_payload 为空也能跑 |
| `test_classify_uses_fallback_on_inference_exception` | mock forward 抛异常 → fallback |
| `test_reason_field_includes_margin_and_labels` | reason 格式约定 |
| `test_lazy_load_only_happens_on_first_classify` | __init__ 不触发权重加载 |

#### 6.3 数据切分单测（`tests/unit/test_dataset_construction.py`）

| 测试 | 验证内容 |
|---|---|
| `test_template_fills_missing_fields_as_wu` | 序列化模板无字段漂移 |
| `test_split_deterministic_by_sample_id_mod100` | 切分稳定可复现 |
| `test_split_three_partitions_disjoint` | train/val/test 三方无重叠 |

#### 6.4 集成测试（`tests/integration/test_strategy_classifier_e2e.py`）

| 测试 | 验证内容 |
|---|---|
| `test_real_model_meets_minimum_accuracy_on_test_set` | 在 test 集跑真实模型 → accuracy ≥ 0.85 |

集成测试用 `unittest.skipUnless(os.environ.get("RUN_STRATEGY_MODEL_E2E") == "1", ...)` 守护。默认 CI 不跑；本地人工或发版前跑。

## 数据流

### 训练流程（离线，一次性）

```text
1. 下载 StructBERT base
   scripts/download_pretrained.py → var/models/pretrained/structbert-base-zh/

2. 数据准备
   data/raw/queries.jsonl       ← 汇集所有 query 源
   data/labeled/labeled.jsonl   ← 人工标注
   scripts/build_dataset.py → data/labeled/labeled.jsonl 校验 + 序列化

3. 切分
   scripts/build_dataset.py → data/splits/{train,val,test}.jsonl

4. 训练
   scripts/train.py
     ← data/splits/{train,val}.jsonl
     ← var/models/pretrained/structbert-base-zh/
     → artifacts/classifier_v1/

5. 离线评测（CI gate）
   scripts/evaluate.py
     ← artifacts/classifier_v1/
     ← data/splits/test.jsonl
     exit 0 if acc >= 0.85, else 1

6. 模型导出（运行时加载路径）
   scripts/export_model.py
     ← artifacts/classifier_v1/
     → var/models/retrieval_strategy_classifier/v1/
```

### 运行时流程

```text
OrchestratorService._build_default_external_context_retriever()
    → TrainedRetrievalStrategyClassifier(fallback=StubRetrievalStrategyClassifier())

DualSourceExternalContextRetriever.retrieve_event_context()
    → classifier.classify(query=..., router_payload=..., session_topic="")
      → (内部) 懒加载 model_dir 下的 StructBERT
      → 序列化输入 → tokenizer → forward → softmax
      → top1 label + margin → {strategy, confidence, reason}
      → 任何异常 → fallback.classify() → {strategy: event_primary, confidence: low, reason: stub_fallback}

ContextRetrievalPlanner.build_plan(strategy_payload, router_payload)
    → 按 strategy 翻译为 plan steps

EventSearchProvider.search_event_context(...)
DisclosureSearchProvider.search(...)
    → 合并结果 → source_status 包含 strategy_reason / strategy_confidence / strategy_source
```

## 降级与失败语义

| 触发 | 行为 | 主流程可观察 |
|---|---|---|
| 缺 `transformers` 包 | 首次 `classify()` 检测 → fallback | `strategy_source="stub_fallback"` |
| 模型权重未下载 | 首次 `classify()` 检测 → fallback | `strategy_source="stub_fallback"` |
| 推理异常 | catch → fallback | `strategy_source="stub_fallback"` |
| 单次推理 > 500ms | catch → fallback | `strategy_source="stub_fallback"` |
| label 非法 | catch → fallback | `strategy_source="stub_fallback"` |
| 模型正常但 margin < 0.15 | 主流程仍走模型预测；`confidence="low"` | `strategy_source="trained"` |
| 模型正常且 confidence=high | 主流程走模型预测 | `strategy_source="trained"` |

**任何失败路径下，主流程的实际 strategy 等于 `event_primary`**，与 stub 当前默认完全一致。这是现有 227 个测试不动的根本原因。

## 与现有系统的衔接

### 与 `OrchestratorService`

`OrchestratorService` 不感知 classifier 实现细节。装配点 `_build_default_external_context_retriever` 内部切换 classifier 实现，外部签名不变。

### 与 `DualSourceExternalContextRetriever`

不变。`DualSourceExternalContextRetriever.__init__` 接受任意 `classifier` 参数；新类满足同一 Protocol。

### 与 `ContextRetrievalPlanner`

不变。planner 只读 `strategy_payload["strategy"]`，对 confidence / reason 不依赖。

### 与 `event_eval` 评测框架

- 训练数据集不复用 `event_eval/fixtures/event_cases_v1.jsonl`，但内容可单向转换：前者 `expected_strategy` → 后者 `label`
- 训练完成后，`TrainedRetrievalStrategyClassifier` 上线，主流程实际跑的策略分布会从单一 `event_primary` 变成三分类；这正是 `event_eval/replay.py` 抽取 `actual_strategy` 字段要观测的核心变化
- 后续可用 `replay_event_cases` 跨多个 PR 对比分类器训练前 / 后的策略命中与目标命中

### 与 PR #11（Bocha 替换 GDELT）

完全正交。Bocha provider 在 `EventSearchProvider` 层；本轮在 `classifier` 层，互不影响。

## 实施顺序（推荐执行顺序）

1. **数据先行**：把 6 条 event_cases + 测试 query + 设计稿示例汇集成 `data/raw/`，逐条人工补 `label`，写入 `data/labeled/labeled.jsonl`
2. **切分稳定**：`scripts/build_dataset.py` 实现模板构造 + 切分；固化 train/val/test
3. **训练管线**：`download_pretrained.py` → `train.py` → 产出 `artifacts/classifier_v1/`
4. **离线评测**：`evaluate.py` 在 test 集跑通；确认 ≥ 0.85
5. **推理类**：`trained_strategy_classifier.py` 实现；含完整失败回退
6. **装配改造**：`service.py` 改用 `TrainedRetrievalStrategyClassifier(fallback=Stub())`
7. **新增测试**：单测 + 数据切分测试 + 集成测试（默认 skip）
8. **trace 透传**：`dual_source_context_retriever.py` 的 `source_status` 增量三个键
9. **全量回归**：跑全部测试确认 227 → 240+ 全绿
10. **中文 commit + 中文 PR**：按 memory 偏好

## 成功标准

- [ ] `backend/training/retrieval_strategy_classifier/` 训练子项目可独立运行
- [ ] 训练数据集 300+ 条，三类分布均衡
- [ ] `scripts/train.py` CPU 可在 30 分钟内跑完 5 epoch
- [ ] `scripts/evaluate.py` 在 test 集 accuracy ≥ 0.85、per-class F1 ≥ 0.80
- [ ] `TrainedRetrievalStrategyClassifier` 加载失败时所有 `classify()` 调用返回 stub 结果
- [ ] 现有 227 个测试全绿
- [ ] 新增 13–15 个单测全绿
- [ ] 推理超时 / label 非法 / forward 异常 → fallback，无未捕获异常抛出
- [ ] `event_eval/fixtures/event_cases_v1.jsonl` 6 条样本预测的 expected_strategy 命中率 ≥ 5/6
- [ ] 中文 commit + 中文 PR 描述（按项目偏好）

## 设计结论

把 `RetrievalStrategyClassifier` 从 stub 升级到真实训练的分类器，关键不是"训一个模型"，而是：

- 把训练代码与主流程 import 路径物理隔离，避免重型 ML 依赖传染
- 让协议层、`StubRetrievalStrategyClassifier`、失败回退语义三者完全不变，确保现有 227 个测试不破
- 选 StructBERT 中文 base 作为微调起点，300+ 条标注 + 离线评测作为 CI gate，达到"敢上生产"门槛
- 用 top1-top2 margin 把模型输出翻译成协议要求的 `high/medium/low` 置信度，reason 字段透传模型决策细节
- 主流程装配点单点切换到 `TrainedRetrievalStrategyClassifier`，加载失败时与 stub 行为完全等价

这条路线比"继续扩张规则词表"更稳，比"放任大模型自由决定一切"更可控，是当前仓库状态下最平衡的方案。