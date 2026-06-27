## 1. 准备治理文件目录

- [x] 1.1 创建 `docs/finsight/modules/`，用于存放模块进度文件
- [x] 1.2 创建 `docs/finsight/templates/`，用于存放任务卡、同步卡、交接卡模板

## 2. 补三份模块进度文件

- [x] 2.1 新增 `control-plane-status.md`，写清模块范围、当前里程碑、本轮目标、输入、输出、卡点和阶段检查信息
- [x] 2.2 新增 `data-evidence-status.md`，写清模块范围、当前里程碑、本轮目标、输入、输出、卡点和阶段检查信息
- [x] 2.3 新增 `presentation-eval-status.md`，写清模块范围、当前里程碑、本轮目标、输入、输出、卡点和阶段检查信息

## 3. 补窗口协作模板

- [x] 3.1 新增 `task-card.md`，给主控窗口派发短期任务使用
- [x] 3.2 新增 `sync-card.md`，给阶段同步进度使用
- [x] 3.3 新增 `handoff-card.md`，给暂停或关闭窗口时交接使用

## 4. 把新模板接入现有治理文档

- [x] 4.1 更新 `parallel-delivery-governance.md`，补充模块进度文件和窗口模板的角色说明
- [x] 4.2 更新 `project-status.md`，说明全局状态和模块进度文件怎么配合更新

## 5. 试跑第一轮流程

- [x] 5.1 用第一批并行任务（`RouterResult + Plan`、`EvidenceBundle`、`FinalResponse + TraceBlock`）检查这些模板够不够用
- [x] 5.2 确认这套治理文档已经足够支持“先用 mock，再按阶段收口”的开发方式
