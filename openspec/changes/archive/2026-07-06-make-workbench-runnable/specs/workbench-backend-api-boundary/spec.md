## ADDED Requirements

### Requirement: 后端 API base URL 必须可由前端从应用配置读取

系统 MUST 允许前端在启动时从 `config/app.yaml` 读取后端 API base URL，而不是把 `http://127.0.0.1:8000` 之类的具体地址硬编码在客户端代码里。

#### Scenario: 前端从 app.workbench.backend_base_url 读取

- **WHEN** 前端初始化 `WorkbenchApiClient` 且未通过构造函数参数显式提供 `backend_base_url`
- **THEN** 客户端 MUST 从应用配置 `app.workbench.backend_base_url` 读取该地址，并将其用作后续所有 HTTP 请求的 base

#### Scenario: 缺省配置回落

- **WHEN** `config/app.yaml` 不存在、不可读、或不包含 `app.workbench.backend_base_url` 键
- **THEN** 客户端 MUST 回落到本地开发默认值 `http://127.0.0.1:8000`，以保证当前阶段本机启动不会被阻止

#### Scenario: base URL 配置错误时不静默走错地址

- **WHEN** 客户端读取到的 `backend_base_url` 与当前请求协议 / host 冲突（例如包含显式占位符、为空字符串、或非 `http(s)://` 开头）
- **THEN** 客户端 MUST 在首次请求前显式抛出 `RuntimeError`，而不是把请求发到错误的地址或静默循环
