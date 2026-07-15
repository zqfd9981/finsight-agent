# FinSight Agent 本地 PDF 语料获取设计

日期：2026-06-30  
状态：讨论稿，待 review

## 1. 目标

这份设计文档用于收敛 FinSight Agent 首版本地 PDF 语料获取方案，为后续 `evidence-retrieval-pipeline` 提供真实语料输入。

本轮目标不是立即实现完整下载系统，而是先把以下问题定清：

- 语料应该从哪些官方源获取
- 不同交易所公司分别走哪条抓取路径
- 年报、半年报、重要公告如何识别和筛选
- 下载后的目录、命名和状态记录如何组织
- 首版采集脚本应该如何拆分

这份文档与 [2026-06-30-local-pdf-rag-design.md](/C:/D/大模型课程/openspec测试项目/docs/superpowers/specs/2026-06-30-local-pdf-rag-design.md) 配套，前者回答“数据从哪里来”，后者回答“数据拿到以后怎么组织和检索”。

## 2. 设计范围

### 2.1 本轮只做什么

本轮设计只覆盖：

- 半导体样本股 PDF 原始语料获取
- 官方披露源的列表发现与 PDF 下载
- 年报、半年报、重要公告筛选
- 下载目录、命名和状态追踪
- 首版采集脚本拆分

### 2.2 本轮不做什么

本轮不包含：

- 新闻抓取
- 非 PDF 结构化财务数据抓取
- OCR / PDF 解析实现
- retrieval / chunking / indexing 实现
- 全市场一次性批量落库
- 云端对象存储与分布式调度

## 3. 数据源结论

### 3.1 首版数据源分工

基于实际页面和前端脚本调研，首版建议采用以下分工：

- 沪市 / 科创板公司：`SSE` 作为主抓取源
- 深市公司：`CNInfo` 作为主抓取源
- `SZSE` 官网：作为抽样校验和补漏入口，不作为首版主抓取源

### 3.2 调研依据

#### 3.2.1 SSE

上交所公开页已经暴露出适合首版程序化抓取的查询路径。

调研确认点：

- 定期报告页存在独立查询脚本
- 公告页存在独立查询脚本
- 前端脚本中明确出现：
  - `queryCompanyBulletinNew.do`
  - `commonQuery.do`
  - 定期报告查询返回 `URL`、`TITLE`、`SSEDATE`

因此，`SSE` 适合作为沪市公司年报、半年报和公告的首版主抓取源。

参考页面：

- [上交所定期报告](https://www.sse.com.cn/disclosure/listedinfo/regular/)
- [上交所上市公司公告](https://www.sse.com.cn/disclosure/listedinfo/announcement/)

#### 3.2.2 CNInfo

巨潮资讯具备统一检索优势，且覆盖深沪京等市场。

调研确认点：

- 页面明确声明其为证监会指定信息披露网站
- 页面明确声明其为深交所法定信息披露平台
- 前端脚本中存在 `api.cninfo.com.cn`
- 全文检索与公告入口围绕公告数据构建

因此，`CNInfo` 适合作为深市公司的首版主抓取源，同时也可作为统一补漏入口。

参考页面：

- [巨潮资讯首页](https://www.cninfo.com.cn/?lang=zh)
- [巨潮全文检索](https://www.cninfo.com.cn/new/fulltextSearch?keyWord=688981)

#### 3.2.3 SZSE

深交所官网公开页更偏栏目 / CMS 结构。

本轮快速调研中，没有像 `SSE` 一样直接确认到一条同等清晰、适合首版直接消费的公司公告查询路径，因此不建议首版把 `SZSE` 官网作为主抓取入口。

参考页面：

- [深交所上市公司公告](https://www.szse.cn/disclosure/notice/company/index.html)

### 3.3 为什么不是“全部只走 CNInfo”

虽然统一走 `CNInfo` 也可行，但首版不建议这样做，原因是：

- `SSE` 对沪市公司披露列表和 PDF 链接更直接
- 按市场分源后，抓取逻辑更贴近原始披露结构
- 首版更容易定位问题是“源站问题”还是“筛选规则问题”

因此，推荐策略不是单源，而是：

- 沪市走 `SSE`
- 深市走 `CNInfo`
- `CNInfo` 兼做补漏

## 4. 采集总体路线

### 4.1 推荐路线

首版采用“列表发现 + 文档筛选 + PDF 下载 + 状态回填”的四阶段路线。

流程如下：

1. 读取样本股 manifest
2. 按公司所属市场选择 source adapter
3. 拉取披露列表 metadata
4. 根据文档类型与标题规则筛选目标文档
5. 下载 PDF 到标准目录
6. 写入下载状态与覆盖率记录

### 4.2 不推荐路线

首版不推荐：

- 直接爬 HTML 列表页做主逻辑
- 先做浏览器自动化再反推接口
- 不经过 metadata 筛选直接全量下载所有公告

原因是：

- HTML 结构更脆弱
- 浏览器自动化调试成本高
- 公告量会迅速失控

## 5. 输入与输出

### 5.1 输入

采集脚本首版应至少接收以下输入：

- 样本股 manifest 路径
- 目标公司范围
- 文档类型范围
- 时间窗口
- 输出根目录

推荐最小输入对象：

```json
{
  "manifest_path": "var/data/corpus_manifests/semiconductor_sample_universe.yaml",
  "company_codes": ["688981", "688347"],
  "doc_types": ["annual_report", "semiannual_report", "major_announcement"],
  "start_date": "2021-01-01",
  "end_date": "2026-06-30",
  "output_root": "var/data/raw_filings"
}
```

### 5.2 输出

采集脚本首版应产出三类结果：

- 原始 PDF 文件
- 文档级 manifest / metadata
- 下载状态与覆盖率记录

原始 PDF 输出目录沿用 RAG 设计稿中的结构：

```text
var/data/raw_filings/
  <company_code>_<company_name>/
    annual/
    semiannual/
    announcements/
```

## 6. 文档类型识别规则

### 6.1 年报

首版年报识别规则建议同时依赖：

- source 端的报告类型字段
- 标题关键词

标题关键词示例：

- `年度报告`
- `年报`

应显式排除：

- `摘要`
- `英文版`
- `取消`
- `更正后摘要`

默认策略：

- 优先保留正式 PDF 正文
- 避免把摘要当成主文档

### 6.2 半年报

首版半年报识别规则建议依赖：

- source 端的报告类型字段
- 标题关键词

标题关键词示例：

- `半年度报告`
- `半年报`

应显式排除：

- `摘要`
- `英文版`
- `取消`

### 6.3 重要公告

首版重要公告只保留既定三类：

1. `业绩预告 / 业绩快报`
2. `重大合同 / 产能扩张 / 投资建设`
3. `并购重组 / 股权激励 / 大额减值等重大事项`

建议采用“两层识别”：

- 第一层：source metadata 中的公告类型字段
- 第二层：标题关键词兜底

关键词兜底示例：

- `业绩预告`
- `业绩快报`
- `签订重大合同`
- `投资建设`
- `产能扩张`
- `收购`
- `并购`
- `重组`
- `股权激励`
- `减值`

## 7. Source Adapter 设计

### 7.1 `SseAdapter`

职责：

- 拉取沪市 / 科创板公司的定期报告列表
- 拉取沪市 / 科创板公司的公告列表
- 输出统一的 `FilingRecord`

建议支持的查询维度：

- `company_code`
- `date range`
- `market type`
- `title keyword`

统一输出字段建议：

- `source_name`
- `company_code`
- `company_name`
- `title`
- `publish_date`
- `source_doc_type`
- `pdf_url`
- `announcement_id`
- `market`

### 7.2 `CninfoAdapter`

职责：

- 拉取深市公司的定期报告和公告列表
- 作为沪市补漏的统一搜索入口
- 输出统一的 `FilingRecord`

统一输出字段应与 `SseAdapter` 对齐，避免下游筛选逻辑分叉。

### 7.3 `SzseVerifier`

职责：

- 对深市样本做抽样校验
- 在 `CNInfo` 缺漏时做人工或半自动补漏支持

首版不要求它具备完整下载能力。

## 8. 统一记录模型

### 8.1 `FilingRecord`

建议各 adapter 对外统一输出 `FilingRecord`：

```json
{
  "source_name": "sse",
  "company_code": "688981",
  "company_name": "中芯国际",
  "market": "sse_kcb",
  "title": "中芯国际2024年年度报告",
  "publish_date": "2025-03-29",
  "source_doc_type": "regular_report",
  "pdf_url": "https://...",
  "announcement_id": "optional",
  "raw_category": "定期报告"
}
```

### 8.2 规范化结果

在下载前，应将 `FilingRecord` 进一步规范化为项目内部文档分类：

- `annual_report`
- `semiannual_report`
- `major_announcement`
- `ignored`

这样 adapter 负责“拿列表”，分类器负责“决定要不要下载”。

## 9. 目录与命名规则

### 9.1 输出目录

下载目录沿用既有 RAG 设计：

```text
var/data/raw_filings/
  <company_code>_<company_name>/
    annual/<year>/
    semiannual/<year>/
    announcements/<year>/
```

### 9.2 文件命名

推荐命名规则：

```text
<company_code>_<company_name>_<doc_type>_<report_year>_<publish_date>.pdf
```

公告若没有明确 `report_year`，可按归属年份或发布日期年份落入对应目录。

### 9.3 重复版本处理

如果同一文档存在多个版本：

- 优先保留正式版 / 更新版
- 同日多版本允许追加 `_v2`、`_v3`
- 摘要与正文不应互相覆盖

## 10. 状态追踪

### 10.1 下载状态表

首版建议单独维护下载状态，而不是只看目录里有没有文件。

最小状态字段建议：

- `company_code`
- `source_name`
- `title`
- `publish_date`
- `normalized_doc_type`
- `download_status`
- `local_path`
- `error_message`
- `retried_count`

### 10.2 覆盖率视图

首版建议产出按公司维度的覆盖率统计：

- 年报数量
- 半年报数量
- 重要公告数量
- 最近一次成功下载时间
- 缺失状态

这样后面扩到 50 家时，能先看数据缺口，再决定补抓或放量。

## 11. 首版脚本拆分

建议首版采集脚本拆成 4 个清晰入口：

### 11.1 `fetch-filing-index`

职责：

- 读取 manifest
- 调用 source adapter
- 生成原始 `FilingRecord` 列表

### 11.2 `filter-filings`

职责：

- 根据标题、日期、文档类型规则筛选目标文档
- 输出规范化后的待下载清单

### 11.3 `download-filings`

职责：

- 下载 PDF
- 落目录
- 记录本地路径与错误状态

### 11.4 `report-coverage`

职责：

- 汇总每家公司已下载文档数量
- 输出缺失报告

## 12. 首版推进顺序

首版不建议直接全量抓 50 家。

推荐顺序：

1. 先选 manifest 里前 `8-10` 家高优先级样本
2. 跑通 `SSE + CNInfo` 两个 adapter
3. 验证目录、命名和筛选规则
4. 查看覆盖率与缺失类型
5. 修正规则后再扩到 50 家

这样能更快发现：

- 某些公司公告标题习惯不同
- 某些 PDF 链接形式不同
- 某些 source metadata 不足以单独分类

## 13. 风险与控制

### 13.1 接口稳定性风险

公开站点的前端接口可能变更。

控制方式：

- 优先使用页面已公开依赖的稳定请求
- adapter 内部封装，不把具体参数散落到上层
- 为每个 source 留好补漏策略

### 13.2 标题规则误判风险

仅靠关键词可能会把摘要或无关公告混进来。

控制方式：

- source category + title keyword 双层判断
- 首版先做人审抽样
- 将 `ignored` 结果保留日志，便于复盘

### 13.3 规模失控风险

50 家公司加 5 年窗口后，公告量很容易放大。

控制方式：

- 首版只保留三类重要公告
- 先试点 8 到 10 家
- 覆盖率通过后再放量

## 14. 建议结论

首版最推荐的语料获取路线是：

- **沪市 / 科创板公司：SSE 主抓取**
- **深市公司：CNInfo 主抓取**
- **SZSE：校验与补漏**

工程路线是：

- **先做 metadata 发现和筛选**
- **再做 PDF 下载**
- **最后做覆盖率统计**

而不是：

- 一上来就写通用爬虫
- 一上来就全量下载所有公告

