# 项目记忆（project_memory 中文版）

> 本文件是 TRAE 项目记忆机制中 `project_memory.md` 的中文整理版，
> 原始路径：`c:\Users\zqcod\.trae-cn\memory\projects\-c-D-------openspec----\project_memory.md`
> TRAE 在每次会话开始时会自动注入原始英文版到 system reminder，本中文版仅作项目内可见的参考文档。

---

## 一、硬性约束（Hard Constraints）

- LLM 后端必须使用 AGICTO OpenAI 兼容 API（`https://api.agicto.cn/v1/chat/completions`），模型为 `deepseek-v4-flash`
- LLM API Key 按以下环境变量优先级读取：`AGICTO_API_KEY` → `FINSIGHT_LLM_API_KEY` → `DEVAGI_API_KEY`
- 由于国内网络限制，LLM 请求必须走系统代理
- LLM 超时设置为 30 秒，重试 3 次，以适配前端 120 秒的读超时
- 重试机制必须覆盖 429、5xx 错误以及网络/超时错误
- LLM 响应必须使用 `response_format={"type":"json_object"}`，并配正则兜底解析
- 不同查询类型必须使用独立的 prompt 文件：
  - `direct_answer.txt`（泛财经问答）
  - `event_answer.txt`（事件影响分析）
  - `brief_answer.txt`（指标查询）
  - `report_answer.txt`（证据报告）

---

## 二、工程约定（Engineering Conventions）

- LLM 客户端实现位于 `backend/src/finsight_agent/infra/llm/client.py`
- LLM 模型可通过 `FINSIGHT_LLM_MODEL` 环境变量覆盖
- LLM 请求的重试逻辑在 `complete_json` 函数中处理
- `ReportingService`（service.py）根据 `response_mode` 将查询路由到 4 个独立的 writer
- 阶段规划采用查表方式（stage_planner），不使用 LLM 规划
- 检索能力封装在 `RetrievalFacade` 中，组件位于 `capabilities/retrieval/`
- RAG 流程使用 LangGraph 状态机，包含 `query_rewrite`、`hybrid_retrieve`、`reflect`、`finalize` 节点，带条件重试循环
- PDF 语料下载使用 `ThreadPoolExecutor` 并行处理，通过 `--workers` 参数配置（默认 5）
- PDF 解析使用 `MinerUDocumentParser`，回退到 `PdfplumberDocumentParser`
- 结构化表格数据存储在 SQLite 数据库 `var/data/structured_data/metrics.db`，采用 EAV 长表结构，14 个固定字段 + 自增主键
- 指标数据采用双字段归一化：`metric_label`（原始中文）+ `metric_name`（标准化英文 key），映射存于 `config/structured_data/metric_aliases.json`
- `MetricRepository.save_records_for_company` 处理数据写入，按公司先删后插防止重复
- `TableExtractor`（table_extractor.py）含双行表头识别逻辑（如银行年报的"附注四 | 本集团"和日期行），并跳过附注序号列
- 稠密向量索引（Qdrant）只索引 `__rag` 后缀目录：page_filter 输出的 MinerU 叙述文本切片（财务表格不入 Qdrant，存 SQLite）
- bge-m3 embedding 配置：`model_name='BAAI/bge-m3'`，1024 维，存于 `var/data/qdrant`
- embedding 提供器 `bge_m3.py` 使用 GPU（cuda），`batch_size=4`，文本截断 500 字符；CPU 回退速度 0.3 chunks/s 不实用

---

## 三、经验教训（Lessons Learned）

### 网络与 LLM

- TRAE 系统代理存在间歇性 SSL 握手失败；LLM 请求必须有重试机制
- 共用的保守系统 prompt 导致回答笼统（"证据不足"类回避）；必须按查询类型使用独立 prompt 才能保证回答质量
- 早期 RAG 流程召回率低，原因是机械拼接查询 + 缺乏证据充分性评估

### PDF 下载与解析

- 串行下载公司年报太慢（100 家公司 4.5 小时）；用 5 个 worker 并行可降到约 1 小时
- pdfplumber 文本提取对复杂格式 PDF（如银行年报）造成严重碎片化和表格结构丢失
- MinerU API 可能将跨页表格拆成多个条目并留空 markdown 占位；结构化页范围应加 2 页 buffer 防止表格内容被截断
- MinerU API 能可靠识别页眉页脚为非表格元素，结构化表格提取无需额外过滤
- 2023/2024 年报切片已删除（pdfplumber 解析质量不可靠）；只有 2025 年报的 MinerU 解析 `__rag` 切片（88 文件，9706 chunks）入库 Qdrant

### Embedding 与 GPU

- bge-m3 在 CPU 上极慢：400 字文本 0.3 chunks/s（9706 chunks 需 9 小时）；GPU + `batch_size=4` + 500 字截断可达 7-8 chunks/s（23 分钟）
- GTX 1650 4GB GPU 可稳定运行 bge-m3，`batch_size=4` + 文本截断 500 字；`batch_size=8+` 会 OOM，长文本（>1000 字）会导致 GPU 静默挂死

### TableExtractor 与结构化数据

- `TABLE_TYPE_KEYWORDS` 财务表关键词必须用权益变动表专属词：`本期期末余额`/`本年期初余额`/`所有者权益内部结转`（移除易混淆的"综合收益总额"和"所有者权益合计"）
- TableExtractor 存在严重列对齐 bug，导致 time_scope 误标（数值被标为 time_scope，格式不一致如"2024年度" vs "2024 年度"，合并/母公司数据混淆），即使数据存在也查询失败
- 注释表（财务报表注释中的明细表）与三表核心指标存在同名 key 碰撞问题（如"应收账款""长期借款""财务费用"），语义不同但指标名相同，导致查询结果不可靠
- TableExtractor 基于正则的列对齐无法处理注释表的多样结构（账龄分桶、资产类别、变动列等）；应改用 `pandas.read_html` 解析 HTML 表格以保留结构信息

### 比亚迪（002594）数据验证（2026-07-13 完成）

- 验证结果：164 张表（三表 16 + 权益变动表 6 + 注释区 142），LLM 注释决策 63 章节（keep=50/skip=13），SQLite 1863 条记录
- 30 个查询全通过，原始 HTML 与 SQLite 值完全一致
  - 营业收入 777,102,455 千元 = 7771 亿元
  - 净利润 41,587,940 千元 ≈ 416 亿元
  - 资产总计 783,355,855 千元 ≈ 7834 亿元

#### 比亚迪验证发现的数据字段特征（查询时必须注意）

1. 三表 `source_section` 多为 `'unknown'`（TableExtractor 未细分，仅现金流量表部分标记为 `'cash_flow_statement'`）
2. `time_scope` 经 `_normalize_time_scope` 归一化后均为 `'YYYY年'`：
   - `'2024年度'` → `'2024年'`
   - `'2024年12月31日'` → `'2024年'`
   - `'2024年(经重述)'` → `'2024年'`
3. 比亚迪用"股东权益合计"而非"所有者权益合计"；归母权益为"归属于母公司股东权益合计"（不是"归属于母公司所有者权益合计"）
4. 营业成本 `metric_label` 为"减:营业成本"或"减：营业成本"（半角/全角冒号并存）
5. 投资活动现金流量净额为"投资活动使用的现金流量净额"（不是"产生的"）
6. 注释区指标名是明细项（如"主营业务收入""职工福利费"），不是报表原词"营业收入""管理费用"
7. 年报数值单位是"千元"，但 `unit` 字段标记为"元"

---

## 四、TRAE 记忆机制说明

### 4.1 机制性质

**TRAE 自带的跨会话记忆机制**，非用户手动维护的文档。TRAE 在每次会话开始时自动将 `project_memory.md` 和 `user_profile.md` 内容注入 system reminder，让 AI 了解项目历史。

### 4.2 路径结构

```
c:\Users\zqcod\.trae-cn\memory\
├── user_profile.md                          # 用户级（跨所有项目）：偏好、技术栈、背景
└── projects\
    └── -c-D-------openspec----\             # 项目级目录（路径编码）
        ├── project_memory.md                # 项目级：规则、约束、约定、教训
        ├── 20260713\                        # 按日期分目录
        │   ├── topics.md                    # 话题级：目标、进度、决策
        │   └── session_memory_<id>.jsonl    # 会话级：任务、TODO、相关文件
        └── ...
```

### 4.3 文件层级

| 层级 | 文件 | 作用域 | 维护方式 |
|------|------|--------|----------|
| 用户级 | `user_profile.md` | 所有项目通用 | 用户说"记住我的 xxx"时由 AI 追加 |
| 项目级 | `project_memory.md` | 仅当前项目 | 用户说"记住 xxx"时由 AI 追加 |
| 话题级 | `topics.md` | 单日话题摘要 | TRAE 自动维护 |
| 会话级 | `session_memory_<id>.jsonl` | 单次会话 | TRAE 自动维护 |

### 4.4 用户如何更新记忆

- 用户级信息（偏好、技术栈）：说"记住我的 xxx"，AI 追加到 `user_profile.md`
- 项目级信息（规则、约定）：说"记住 xxx"，AI 追加到 `project_memory.md`
- TRAE 自动维护 topics.md 和 session_memory_*.jsonl，无需用户干预

### 4.5 快速查阅命令

```bash
# 查看项目记忆
cat "c:\Users\zqcod\.trae-cn\memory\projects\-c-D-------openspec----\project_memory.md"

# 查看用户档案
cat "c:\Users\zqcod\.trae-cn\memory\user_profile.md"

# 查看最近话题
ls "c:\Users\zqcod\.trae-cn\memory\projects\-c-D-------openspec----\"
```

---

## 五、当前项目快照

### 5.1 项目目标

FinSight Agent —— 基于 RAG 的财经问答与事件影响分析系统，处理 A 股上市公司年报语料。

### 5.2 技术栈

- **后端**：Python、LangGraph、LangChain
- **前端**：Streamlit
- **LLM**：AGICTO（deepseek-v4-flash）
- **PDF 解析**：MinerU API（主）+ pdfplumber（回退）
- **向量库**：Qdrant（bge-m3，1024 维）
- **结构化数据**：SQLite（EAV 长表）
- **Embedding GPU**：GTX 1650 4GB

### 5.3 关键里程碑

- 2026-07-13：比亚迪数据严格验证完成（30/30 查询通过），输出验证方法论文档
  `table-extraction-and-validation-guide.md`（项目根目录）
- 2025 年报语料处理完成：88 份年报、51625 条 SQLite 记录、10062 个 Qdrant 点
