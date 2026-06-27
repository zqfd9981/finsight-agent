# FinSight 前后端目录方案草案

日期：2026-06-27  
状态：探索稿，未替代现有正式 spec

## 1. 这份文档的定位

这份文档用于回答一个非常具体的问题：

**如果项目想按 `frontend/` 和 `backend/` 的工程认知来组织代码，第一版应该怎么搭。**

它不是新的正式约束，也不自动推翻当前的：

- `openspec/specs/project-implementation-architecture/spec.md`
- `项目框架结构约定.md`

目前它的作用是：

- 给出一个更符合“前后端分离”直觉的目录草案
- 明确它与当前 spec 的冲突点
- 说明如何从当前骨架平滑迁移

## 2. 结论先说

推荐采用一个**两阶段方案**：

- V1：先把 `Streamlit` 放进 `frontend/`，仍然保持单仓开发
- V2：再把 `frontend/` 从 `Streamlit` 升级为独立 Web 前端工程

也就是说，先不一步到位上 React / Vue / Next.js，但从目录和依赖边界上，提前为那次升级留接口。

这比“继续维持 `apps/api + apps/workbench + src`”更符合前后端心智模型，也比“现在立刻做独立 Web 前端”成本更低。

## 3. 推荐目标

这个方案想同时满足 4 个目标：

1. 当前 V1 依然能低成本推进
2. 目录一眼能看出“前端在哪、后端在哪”
3. 后续升级成独立 Web 前端时，不需要把后端核心代码再推翻一次
4. shared contracts 能继续作为前后端共同遵守的稳定边界

## 4. 推荐目录树

推荐目录树如下：

```text
.
├─ frontend/
│  ├─ streamlit_app/
│  │  ├─ app.py
│  │  ├─ pages/
│  │  ├─ components/
│  │  └─ state/
│  └─ README.md
├─ backend/
│  ├─ apps/
│  │  └─ api/
│  │     └─ main.py
│  ├─ src/
│  │  └─ finsight_agent/
│  │     ├─ control_plane/
│  │     ├─ capabilities/
│  │     ├─ infra/
│  │     ├─ config/
│  │     └─ workbench_api/
│  └─ tests/
├─ shared/
│  ├─ contracts/
│  ├─ enums/
│  └─ fixtures/
├─ config/
├─ fixtures/
├─ tests/
├─ scripts/
├─ var/
├─ docs/
└─ openspec/
```

## 5. 各层含义

### 5.1 `frontend/`

这里代表**前端工程**，不是“任意 UI 相关代码堆放区”。

在 V1 阶段：

- `frontend/streamlit_app/` 是当前工作台实现
- 它承担输入、结果展示、trace 展示、追问体验
- 它不拥有业务语义主权

在 V2 阶段：

- 可以把 `frontend/streamlit_app/` 替换为 `frontend/web/`
- 例如 `frontend/web/` 下放 `React`、`Vue` 或 `Next.js`

这样做的关键价值是：

- 前端始终是前端
- 只是技术实现从 `Streamlit` 升级为更典型的 Web 工程

### 5.2 `backend/`

这里代表**后端工程**。

它包含两类东西：

- `backend/apps/api/`：FastAPI 启动入口
- `backend/src/finsight_agent/`：核心业务实现

其中核心业务实现继续按现有 spec 的分层保留：

- `control_plane/`
- `capabilities/`
- `infra/`
- `config/`

也就是说，目录认知上改成“后端工程”，但后端内部的职责分层不需要推翻。

### 5.3 `shared/`

如果项目要越来越接近真正前后端分离，`shared/` 最好提升到顶层，而不是继续放在 `backend/src/` 里。

这里适合放：

- shared contracts
- shared enums
- 前后端联调用的稳定 fixture

这样做的原因是：

- 这些对象不是“后端私有实现”
- 它们是前后端共同遵守的接口边界

## 6. V1 与 V2 的关系

### V1：`frontend = Streamlit`

V1 不是严格独立前端工程，而是：

- 目录上先分成 `frontend/` 和 `backend/`
- 前端实现仍然使用 `Streamlit`
- 后端实现仍然使用 `FastAPI + Python services`

这个阶段的重点不是技术炫技，而是：

- 尽快打通链路
- 把接口边界守住
- 不让 `Streamlit` 直接侵入后端内部实现

### V2：`frontend = React / Vue / Next.js`

V2 升级时，理想状态应该只改：

- `frontend/` 工程本身
- API 调用方式
- 前端构建与部署链路

尽量不改：

- `backend/` 核心业务实现
- `shared/` 契约边界
- 后端主链路组织方式

如果 V1 阶段没有守住边界，V2 就会很痛。

## 7. 这个方案的核心前提

这个方案虽然允许 V1 先用 `Streamlit`，但必须同时遵守下面 3 条：

### 7.1 前端不直连后端内部实现

`frontend/streamlit_app/` 不应该直接 import：

- `backend/src/finsight_agent/control_plane/*`
- `backend/src/finsight_agent/capabilities/*`

更合理的方式是：

- 通过 API 调后端
- 或至少通过明确的前端适配层间接消费

### 7.2 后端对外暴露稳定响应

后端应该对前端暴露稳定的：

- `FinalResponse`
- `TraceBlock`
- `GuardrailOrErrorResponse`

前端只消费这些稳定输出，不反向塑造后端内部语义。

### 7.3 shared contracts 不能再被看成“后端内部模块”

如果还把 shared contracts 继续埋在后端内部目录里，目录上写了 `frontend/backend` 也只是表面分离。

## 8. 与现有 spec 的冲突点

这里是最重要的一部分。

### 8.1 与正式顶层目录约束冲突

当前正式 spec 明确要求顶层至少有：

- `apps/`
- `src/`
- `config/`
- `fixtures/`
- `tests/`
- `scripts/`
- `var/`
- `docs/`
- `openspec/`

而本方案希望引入：

- `frontend/`
- `backend/`
- `shared/`

这意味着：

- 不能只改目录不改 spec
- 否则目录树会偏离当前正式约束

### 8.2 与“V1 单仓 Python 工程”表述冲突

当前人话版约定明确写的是：

**V1 用单仓 Python 工程来落地。**

这句话至少隐含了两层意思：

- 不是前后端双工程心智
- 前端当前默认是 Python/Streamlit 工作台，而不是独立 Web 工程

而 `frontend/backend` 目录方案会把项目认知往：

- “一个前端工程”
- “一个后端工程”

这个方向推进。

即使 V1 仍然是单仓，工程认知已经发生变化。

### 8.3 与 `analysis-workbench` 当前映射冲突

当前映射关系是：

- `apps/workbench/`
- `src/finsight_agent/workbench/`

如果切到 `frontend/` 方案，就要改成更像：

- `frontend/streamlit_app/`
- 或者 `frontend/streamlit_app/pages/`

这会直接影响 `analysis-workbench` spec 的目录映射表达。

### 8.4 与 shared contracts 当前落点冲突

当前 shared contracts 在：

- `src/finsight_agent/shared/contracts/`

而更贴近前后端分离的落点应该是：

- `shared/contracts/`

这不是简单移动文件的问题，而是：

- shared 的归属语义要从“运行时代码共享层”转成“跨工程共享边界”

### 8.5 与测试边界组织存在二义性

当前 spec 倾向于统一 `tests/` 顶层组织。

如果引入 `frontend/` 和 `backend/`，就会出现两个方向：

- 继续保留顶层 `tests/`
- 或在 `frontend/`、`backend/` 各自维护局部测试

这个问题不先定，后面测试目录会变乱。

## 9. 推荐的冲突处理方式

如果未来要正式采用这个方案，我建议这样处理：

### 9.1 不直接否定现有 spec 的“分层思想”

要改的是：

- 顶层工程组织方式

不该改的是：

- `shared / control_plane / capabilities / infra` 这些后端内部职责边界

也就是说：

- 保留现有 spec 的模块分层
- 调整它们所处的“工程容器”

### 9.2 把 `frontend/backend` 视为工程层

建议把目录层次理解为两层：

第一层：工程层

- `frontend/`
- `backend/`
- `shared/`

第二层：后端内部实现层

- `control_plane/`
- `capabilities/`
- `infra/`
- `config/`

这样能避免把“前后端分离”和“后端内部模块分层”混成一个问题。

### 9.3 在正式 spec 中明确 V1 与 V2 的边界

如果未来改 spec，建议直接写清楚：

- V1：`frontend/` 先用 `Streamlit`
- V2：`frontend/` 可升级为独立 Web 前端

这样团队不会误以为：

- 现在就必须上 React
- 或现在用了 Streamlit，就永远不能走前后端双工程

## 10. 从当前骨架迁移的最小路径

如果后面决定采纳这个方案，建议按最小破坏迁移，而不是推倒重来。

### 第一步：先做目录级迁移

把当前：

```text
apps/api/
apps/workbench/
src/finsight_agent/
```

迁移为：

```text
frontend/streamlit_app/
backend/apps/api/
backend/src/finsight_agent/
```

这一阶段先不改业务逻辑，只改目录和 import 路径。

### 第二步：把 shared contracts 抬升

把当前：

```text
backend/src/finsight_agent/shared/contracts/
backend/src/finsight_agent/shared/enums/
```

逐步整理到：

```text
shared/contracts/
shared/enums/
```

这里要非常克制，只搬真正跨前后端共享的对象。

### 第三步：收紧前端依赖边界

在这一阶段明确禁止：

- 前端直接 import 后端内部 service
- 前端直接消费后端内部中间对象

要逐步过渡到：

- 前端只看 API 响应
- 或前端只看 shared contracts

### 第四步：再决定要不要升级 Web 前端

只有前三步完成以后，才值得判断：

- 继续 `Streamlit`
- 还是升级成 `React / Vue / Next.js`

否则太早上独立 Web 前端，只会把当前问题复制到新目录里。

## 11. 推荐的正式目录版本

如果未来这套方案被吸收进正式 spec，我更推荐下面这个版本：

```text
.
├─ frontend/
│  └─ streamlit_app/
├─ backend/
│  ├─ apps/
│  │  └─ api/
│  ├─ src/
│  │  └─ finsight_agent/
│  │     ├─ control_plane/
│  │     ├─ capabilities/
│  │     ├─ infra/
│  │     └─ config/
│  └─ tests/
├─ shared/
│  ├─ contracts/
│  ├─ enums/
│  └─ fixtures/
├─ config/
├─ fixtures/
├─ tests/
├─ scripts/
├─ var/
├─ docs/
└─ openspec/
```

这里有两个刻意保留：

- 顶层 `config / fixtures / tests / scripts / var / docs / openspec` 继续保留
- 后端内部 `control_plane / capabilities / infra` 继续保留

这样改动幅度最小，也最容易和现有 spec 融合。

## 12. 最终建议

如果只是为了“看起来像前后端分离”，不建议现在立刻大改。

如果是为了：

- 让目录认知更清楚
- 为后续独立 Web 前端升级铺路

那这套方案是合理的，但它应该先经过一次正式 spec 更新，而不是直接绕过 spec 改代码。

当前更稳妥的决策顺序应该是：

1. 先确认是否接受 `frontend/ + backend/ + shared/` 的工程层方案
2. 如果接受，先更新正式 spec
3. 再把当前骨架迁移过去
4. 最后再决定 `frontend/` 是否从 `Streamlit` 升级为独立 Web 前端
