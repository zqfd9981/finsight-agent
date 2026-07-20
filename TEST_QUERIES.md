# FinSight Agent 测试 Query 集合（v2，100+ 条）

覆盖项目所有链路所有分支的查询场景，用于回归测试与问题排查。

每条 query 标注：
- `id`: 唯一编号
- `category`: 分类（对应 intent 或子分支）
- `query`: 用户查询原文
- `expect`: 预期行为关键点（用于判定是否"有问题"）

## 链路覆盖矩阵

| Intent | Strategy | 条数 | response_mode |
|---|---|---|---|
| metric_lookup | — | 48 | brief_answer |
| event_impact_analysis | event_primary | 10 | event_answer |
| event_impact_analysis | disclosure_primary | 8 | report |
| event_impact_analysis | dual_primary | 7 | report |
| general_finance_qa | — | 16 | direct |
| evidence_lookup | — | 8 | report |
| out_of_scope | — | 8 | guardrail |
| follow_up（多轮） | — | 10 | 多种 |

合计 115 条。

---

## 一、metric_lookup 路径（48条）

### 1.1 单公司单指标 direct（8条）

- id: M-001
- category: metric_lookup/单公司单指标
- query: 宁德时代2024年净利润多少
- expect: 返回 net_profit，约540.07亿元

- id: M-002
- category: metric_lookup/单公司单指标
- query: 宁德时代2024年归母净利润是多少
- expect: 返回 net_profit_attributable_to_parent，约507.45亿元

- id: M-003
- category: metric_lookup/单公司单指标
- query: 贵州茅台2024年营业收入
- expect: 返回 revenue，约1708.99亿元

- id: M-004
- category: metric_lookup/单公司单指标
- query: 比亚迪2024年总资产
- expect: 返回 total_assets（DB数据有ETL单位问题，约7.83亿元）

- id: M-005
- category: metric_lookup/单公司单指标
- query: 宁德时代2024年每股收益
- expect: 返回 basic_earnings_per_share，约11.58元/股

- id: M-006
- category: metric_lookup/单公司单指标
- query: 贵州茅台2024年归母净利润
- expect: 返回 net_profit_attributable_to_parent

- id: M-007
- category: metric_lookup/单公司单指标
- query: 中国平安2024年总资产
- expect: 返回 total_assets，银行类大额数字

- id: M-008
- category: metric_lookup/单公司单指标
- query: 宁德时代2024年经营现金流
- expect: 返回 cash_flow_from_operating

### 1.2 单公司衍生指标（6条）

- id: M-101
- category: metric_lookup/衍生指标
- query: 宁德时代2024年毛利率
- expect: 返回 (revenue-cost)/revenue，百分比

- id: M-102
- category: metric_lookup/衍生指标
- query: 宁德时代2024年ROE
- expect: 返回 net_profit/total_owners_equity，百分比

- id: M-103
- category: metric_lookup/衍生指标
- query: 贵州茅台2024年净利率
- expect: 返回 net_profit/revenue，百分比

- id: M-104
- category: metric_lookup/衍生指标
- query: 比亚迪2024年资产负债率
- expect: 返回 total_liabilities/total_assets，百分比

- id: M-105
- category: metric_lookup/衍生指标
- query: 贵州茅台2024年净资产收益率
- expect: 同 ROE，中文别名

- id: M-106
- category: metric_lookup/衍生指标
- query: 宁德时代2024年销售净利率
- expect: 同净利率，中文别名

### 1.3 多公司对比（8条）

- id: M-201
- category: metric_lookup/多公司对比
- query: 宁德时代，三一重工，赛力斯2024年的归母净利润分别是多少，哪个最多
- expect: 3家都返回，宁德时代最多

- id: M-202
- category: metric_lookup/多公司对比
- query: 宁德时代和比亚迪2024年营收谁更高
- expect: 2家都返回，宁德时代更高

- id: M-203
- category: metric_lookup/多公司对比
- query: 贵州茅台，五粮液，泸州老窖2024年净利润对比
- expect: 3家白酒公司，贵州茅台最高

- id: M-204
- category: metric_lookup/多公司对比
- query: 中国平安和中国人寿2024年总资产哪个更大
- expect: 2家保险，中国平安更大

- id: M-205
- category: metric_lookup/多公司对比
- query: 比亚迪和宁德时代2024年净利润哪个高
- expect: 2家新能源公司对比

- id: M-206
- category: metric_lookup/多公司对比
- query: 贵州茅台和五粮液2024年毛利率谁更高
- expect: 衍生指标多公司对比

- id: M-207
- category: metric_lookup/多公司对比
- query: 宁德时代、比亚迪、赛力斯2024年营收排名
- expect: 3家新能源车企营收排序

- id: M-208
- category: metric_lookup/多公司对比
- query: 五粮液、泸州老窖、山西汾酒2024年净利润分别是多少
- expect: 3家白酒公司净利润

### 1.4 多指标查询（5条）

- id: M-301
- category: metric_lookup/多指标
- query: 宁德时代2024年净利润和营业收入分别是多少
- expect: 返回 net_profit + revenue 两个指标

- id: M-302
- category: metric_lookup/多指标
- query: 贵州茅台2024年总资产和负债合计
- expect: 返回 total_assets + total_liabilities（拆分"和"连接词）

- id: M-303
- category: metric_lookup/多指标
- query: 宁德时代2024年净利润与总资产对比
- expect: 返回 net_profit + total_assets

- id: M-304
- category: metric_lookup/多指标
- query: 贵州茅台2024年营业收入和净利润和总资产
- expect: 3指标查询

- id: M-305
- category: metric_lookup/多指标
- query: 宁德时代2024年每股收益和归母净利润
- expect: EPS + 归母净利润

### 1.5 多期对比与趋势（5条）

- id: M-401
- category: metric_lookup/多期对比
- query: 宁德时代2023年和2024年净利润对比
- expect: 返回2期数据

- id: M-402
- category: metric_lookup/多期趋势
- query: 贵州茅台近三年营收变化
- expect: 返回多期营收（DB可能只有2023/2024）

- id: M-403
- category: metric_lookup/多期对比
- query: 宁德时代2023和2024年总资产变化
- expect: 2期总资产

- id: M-404
- category: metric_lookup/多期趋势
- query: 贵州茅台2022到2024年净利润走势
- expect: 区间年份查询

- id: M-405
- category: metric_lookup/多期对比
- query: 宁德时代2024年vs2023年营收对比
- expect: 2期营收对比

### 1.6 增长率与计算（8条）

- id: M-501
- category: metric_lookup/同比增长
- query: 宁德时代2024年净利润同比增长率是多少
- expect: compute yoy，约15.5%

- id: M-502
- category: metric_lookup/连续增长
- query: 宁德时代营收连续增长几年了
- expect: compute consecutive_growth

- id: M-503
- category: metric_lookup/复合增长
- query: 宁德时代2022到2024年净利润复合增长率是多少
- expect: compute cagr（缺2022数据时降级返回已有期）

- id: M-504
- category: metric_lookup/复合增长
- query: 宁德时代近3年营收复合增长率
- expect: compute cagr

- id: M-505
- category: metric_lookup/同比增长
- query: 贵州茅台2024年营收同比增长率
- expect: compute yoy

- id: M-506
- category: metric_lookup/环比增长
- query: 宁德时代2024年净利润环比增长率是多少
- expect: compute qoq（年报场景等同 yoy）

- id: M-507
- category: metric_lookup/同比增长
- query: 宁德时代2023年净利润同比增长率是多少
- expect: compute yoy（DB缺2022数据时降级）

- id: M-508
- category: metric_lookup/连续增长
- query: 贵州茅台营收连续增长几年了
- expect: compute consecutive_growth

### 1.7 口语/模糊/错别字（6条）

- id: M-601
- category: metric_lookup/口语
- query: 宁德时代去年赚了多少钱
- expect: "去年"消解为2023年，net_profit

- id: M-602
- category: metric_lookup/简写
- query: 宁德时代2024净利润
- expect: 简写省略"年"和"多少"

- id: M-603
- category: metric_lookup/口语
- query: 茅台去年赚多少
- expect: "茅台"别名消解为贵州茅台

- id: M-604
- category: metric_lookup/错别字
- query: 宁德时代2024年净利闰多少
- expect: "净利闰"错别字消解为"净利润"

- id: M-605
- category: metric_lookup/口语
- query: 宁德时代现在市值多少亿
- expect: 市值不在DB，降级返回

- id: M-606
- category: metric_lookup/简称
- query: 平安2024年总资产
- expect: "平安"消解为中国平安

### 1.8 边界与异常（10条）

- id: M-701
- category: metric_lookup/不存在公司
- query: 某某不存在公司2024年净利润
- expect: 降级，说明公司不存在

- id: M-702
- category: metric_lookup/不存在指标
- query: 宁德时代2024年某某不存在指标
- expect: 降级

- id: M-703
- category: metric_lookup/未来年份
- query: 宁德时代2026年净利润
- expect: 降级，说明无未来数据

- id: M-704
- category: metric_lookup/历史年份缺失
- query: 宁德时代2020年净利润
- expect: 降级或返回空

- id: M-705
- category: metric_lookup/全公司排名
- query: 2024年净利润最高的公司是谁
- expect: ranking limit=1，全公司排序

- id: M-706
- category: metric_lookup/全公司排名
- query: 2024年净利润前3名
- expect: ranking limit=3

- id: M-707
- category: metric_lookup/全公司排名
- query: 2024年营收最低的公司
- expect: ranking desc=false

- id: M-708
- category: metric_lookup/全公司排名
- query: 2024年总资产最大的公司
- expect: ranking limit=1 by total_assets

- id: M-709
- category: metric_lookup/多问题
- query: 宁德时代2024年净利润和营收和总资产分别是多少，哪家公司2024年净利润最高
- expect: 复合查询（多指标 + 排名）

- id: M-710
- category: metric_lookup/聚合
- query: 2024年所有公司净利润总和是多少
- expect: compute sum

---

## 二、event_impact_analysis 路径（25条）

### 2.1 event_primary - 地缘政治事件（4条）

- id: E-001
- category: event_impact/event_primary/地缘
- query: 红海局势会对A股哪些板块有什么影响
- expect: event_primary，航运/能源板块

- id: E-002
- category: event_impact/event_primary/地缘
- query: 俄乌冲突对A股有什么影响
- expect: event_primary，能源/军工/农业板块

- id: E-003
- category: event_impact/event_primary/地缘
- query: 中东局势升级利好哪些股票
- expect: event_primary，石油/黄金板块

- id: E-004
- category: event_impact/event_primary/地缘
- query: 台海局势对军工板块影响
- expect: event_primary，军工板块

### 2.2 event_primary - 宏观政策事件（4条）

- id: E-101
- category: event_impact/event_primary/宏观
- query: 降息对银行股的影响
- expect: event_primary，银行股净息差影响

- id: E-102
- category: event_impact/event_primary/宏观
- query: 加息对债市有什么冲击
- expect: event_primary，债券价格下跌

- id: E-103
- category: event_impact/event_primary/宏观
- query: 降准利好哪些板块
- expect: event_primary，银行/地产/基建

- id: E-104
- category: event_impact/event_primary/宏观
- query: 房地产新政对地产股影响
- expect: event_primary，地产板块

### 2.3 event_primary - 行业事件（2条）

- id: E-201
- category: event_impact/event_primary/行业
- query: 近期航运板块受什么影响
- expect: event_primary，航运板块

- id: E-202
- category: event_impact/event_primary/行业
- query: 新能源补贴退坡对宁德时代影响
- expect: event_primary，新能源产业链

### 2.4 disclosure_primary - 公司公告事件（8条）

- id: D-001
- category: event_impact/disclosure_primary/增减持
- query: 宁德时代股东减持公告影响
- expect: disclosure_primary，公司内生事项

- id: D-002
- category: event_impact/disclosure_primary/业绩
- query: 贵州茅台2024年业绩预告影响
- expect: disclosure_primary，业绩预告

- id: D-003
- category: event_impact/disclosure_primary/并购
- query: 宁德时代收购海外锂矿对股价影响
- expect: disclosure_primary，并购事项

- id: D-004
- category: event_impact/disclosure_primary/回购
- query: 比亚迪回购股份意味着什么
- expect: disclosure_primary，股份回购

- id: D-005
- category: event_impact/disclosure_primary/高管
- query: 宁德时代高管辞职公告影响
- expect: disclosure_primary，高管变动

- id: D-006
- category: event_impact/disclosure_primary/分红
- query: 贵州茅台分红方案对股东影响
- expect: disclosure_primary，分红方案

- id: D-007
- category: event_impact/disclosure_primary/定增
- query: 赛力斯定增募资用途和影响
- expect: disclosure_primary，定向增发

- id: D-008
- category: event_impact/disclosure_primary/诉讼
- query: 宁德时代诉讼案件对经营影响
- expect: disclosure_primary，法律诉讼

### 2.5 dual_primary - 事件+公司双源（7条）

- id: F-001
- category: event_impact/dual_primary
- query: 红海局势对中远海控有什么影响
- expect: dual_primary，外部事件+具体公司

- id: F-002
- category: event_impact/dual_primary
- query: 锂价下跌对宁德时代和比亚迪的影响
- expect: dual_primary，行业事件+多公司

- id: F-003
- category: event_impact/dual_primary
- query: 芯片禁令对中芯国际影响
- expect: dual_primary，地缘+公司

- id: F-004
- category: event_impact/dual_primary
- query: 汇率波动对出口型企业影响，比如海尔智家
- expect: dual_primary，宏观+公司

- id: F-005
- category: event_impact/dual_primary
- query: 碳中和政策对宁德时代业务影响
- expect: dual_primary，政策+公司

- id: F-006
- category: event_impact/dual_primary
- query: 特斯拉降价对国内新能源车企冲击
- expect: dual_primary，行业事件+多公司

- id: F-007
- category: event_impact/dual_primary
- query: 关税政策对宁德时代海外业务影响
- expect: dual_primary，贸易+公司

---

## 三、general_finance_qa 路径（16条）

### 3.1 概念解释（5条）

- id: G-001
- category: general_finance_qa/概念
- query: 什么是市盈率
- expect: direct_answer，概念解释

- id: G-002
- category: general_finance_qa/概念
- query: 市净率和市盈率区别
- expect: direct_answer，对比概念

- id: G-003
- category: general_finance_qa/概念
- query: 什么是ROE，怎么计算
- expect: direct_answer，公式解释

- id: G-004
- category: general_finance_qa/概念
- query: 自由现金流是什么意思
- expect: direct_answer

- id: G-005
- category: general_finance_qa/概念
- query: 资产负债率高好还是低好
- expect: direct_answer，开放观点

### 3.2 宏观机制（5条）

- id: G-101
- category: general_finance_qa/宏观
- query: 汇率贬值对出口企业有什么影响
- expect: direct_answer（可能超时，RAG路径）

- id: G-102
- category: general_finance_qa/宏观
- query: 降息周期下债市如何走
- expect: direct_answer

- id: G-103
- category: general_finance_qa/宏观
- query: 通胀对股市影响
- expect: direct_answer

- id: G-104
- category: general_finance_qa/宏观
- query: M2增速和股市关系
- expect: direct_answer

- id: G-105
- category: general_finance_qa/宏观
- query: LPR下调对房贷影响
- expect: direct_answer

### 3.3 行业常识（3条）

- id: G-201
- category: general_finance_qa/行业
- query: 白酒行业景气度怎么看
- expect: direct_answer

- id: G-202
- category: general_finance_qa/行业
- query: 新能源汽车渗透率现状
- expect: direct_answer

- id: G-203
- category: general_finance_qa/行业
- query: 银行业净息差为什么下降
- expect: direct_answer

### 3.4 开放观点与边界（3条）

- id: G-301
- category: general_finance_qa/开放
- query: 现在适合定投基金吗
- expect: direct_answer，开放观点

- id: G-302
- category: general_finance_qa/混合
- query: 宁德时代是好公司吗
- expect: general_finance_qa（非指标查询，非荐股）

- id: G-303
- category: general_finance_qa/混合
- query: 茅台和五粮液哪个更值得买
- expect: general_finance_qa 或 out_of_scope（投资建议边界）

---

## 四、evidence_lookup 路径（8条）

- id: V-001
- category: evidence_lookup/展开
- query: 展开说说宁德时代净利润
- expect: drilldown，检索依据

- id: V-002
- category: evidence_lookup/原因
- query: 宁德时代净利润同比变化原因
- expect: drilldown，原因分析

- id: V-003
- category: evidence_lookup/原文
- query: 贵州茅台营收数据出处
- expect: evidence_lookup，索取原文

- id: V-004
- category: evidence_lookup/依据
- query: 宁德时代ROE计算依据是什么
- expect: evidence_lookup，索取依据

- id: V-005
- category: evidence_lookup/详情
- query: 详细说说比亚迪资产负债率
- expect: drilldown

- id: V-006
- category: evidence_lookup/细节
- query: 宁德时代2024年现金流详情
- expect: drilldown

- id: V-007
- category: evidence_lookup/对比依据
- query: 宁德时代和比亚迪营收差距依据
- expect: evidence_lookup

- id: V-008
- category: evidence_lookup/趋势原因
- query: 贵州茅台近三年营收增长原因
- expect: drilldown，趋势原因

---

## 五、out_of_scope 路径（8条）

- id: O-001
- category: out_of_scope/荐股
- query: 推荐一只股票
- expect: guardrail，拒答荐股

- id: O-002
- category: out_of_scope/股价
- query: 宁德时代下周股价走势
- expect: guardrail，拒答股价预测

- id: O-003
- category: out_of_scope/目标价
- query: 贵州茅台目标价多少
- expect: guardrail，拒答目标价

- id: O-004
- category: out_of_scope/估值
- query: 宁德时代现在估值高吗
- expect: guardrail，拒答估值判断

- id: O-005
- category: out_of_scope/短线
- query: 明天买什么股票能涨停
- expect: guardrail，拒答短线投机

- id: O-006
- category: out_of_scope/投资建议
- query: 现在该不该卖掉比亚迪
- expect: guardrail，拒答买卖建议

- id: O-007
- category: out_of_scope/择时
- query: 现在是牛市还是熊市
- expect: guardrail 或 general_finance_qa（边界）

- id: O-008
- category: out_of_scope/非金融
- query: 今天天气怎么样
- expect: out_of_scope 或 general_finance_qa

---

## 六、follow_up 多轮追问（10条）

> 注：需配合 session_id 测试，首条 query 为 first_turn，后续为 follow_up

- id: FU-001
- category: follow_up/redirect
- first_query: 宁德时代2024年净利润多少
- query: 贵州茅台呢
- expect: redirect，切换公司到贵州茅台

- id: FU-002
- category: follow_up/drilldown
- first_query: 宁德时代2024年净利润多少
- query: 它的营收呢
- expect: drilldown + 公司指代"它"

- id: FU-003
- category: follow_up/compare
- first_query: 宁德时代2024年净利润多少
- query: 和比亚迪比怎么样
- expect: compare，新增对比公司

- id: FU-004
- category: follow_up/expand
- first_query: 宁德时代2024年净利润多少
- query: 还有呢
- expect: expand，延伸其他指标

- id: FU-005
- category: follow_up/时间指代
- first_query: 宁德时代2024年净利润多少
- query: 去年呢
- expect: 时间指代，"去年"消解为2023年

- id: FU-006
- category: follow_up/指标指代
- first_query: 宁德时代2024年净利润多少
- query: 它的同比增长率呢
- expect: 指标指代，沿用净利润算yoy

- id: FU-007
- category: follow_up/redirect
- first_query: 红海局势对A股哪些板块有影响
- query: 降息呢
- expect: redirect，切换话题

- id: FU-008
- category: follow_up/drilldown
- first_query: 宁德时代2024年毛利率
- query: 怎么算的
- expect: drilldown，索取计算依据

- id: FU-009
- category: follow_up/compare
- first_query: 贵州茅台2024年净利润
- query: 五粮液呢
- expect: compare，新增对比公司

- id: FU-010
- category: follow_up/expand
- first_query: 宁德时代2024年净利润
- query: 还有哪些新能源公司
- expect: expand，延伸行业
