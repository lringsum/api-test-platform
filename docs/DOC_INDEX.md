# AI 文档索引

这是一份给“后续任何 AI / 新接手开发者”的单页入口。

目标只有一个：

- 先看这一页，就能知道这个项目是什么
- 先看哪几份文档
- 做不同任务时该继续读哪里
- 哪些文档是默认高优先级，哪些只是按需进入

如果时间很紧，至少先读完本页里的“最小必读集”。

## 1. 这份索引怎么用

这份文档只负责一件事：导航，不负责重复解释系统细节。

如果你刚接手仓库，建议顺序是：

1. 先看 `README.md` 里的“AI 接手须知”
2. 再用本页决定下一步该读哪份文档
3. 真正落代码前，再回到对应的 `frontend/src/`、`app/routes/api_v1.py`、`app/services/*.py`

## 2. 最小必读集

默认先看这 3 份，基本就能避免大多数改偏：

1. [README.md](../README.md)
2. [AI_DEVELOPMENT_KNOWLEDGE_BASE.md](./AI_DEVELOPMENT_KNOWLEDGE_BASE.md)
3. [project_long_term_memory_cn.md](./project_long_term_memory_cn.md)

### 2.1 近期必读增量（数据库与回归）

如果任务涉及数据库结构、执行性能或回归门禁，请额外先读：

1. [migrations/README](../migrations/README)
2. [pytest.ini](../pytest.ini)
3. [scripts/run_backend_regression.py](../scripts/run_backend_regression.py)

这些文件定义了当前默认工作流：migration-first（默认关闭 bootstrap）+ 后端最小回归门禁。

这 3 份的分工是：

- `README.md`：项目入口、启动方式、运行注意事项
- `AI_DEVELOPMENT_KNOWLEDGE_BASE.md`：当前代码真实结构与运行机制
- `project_long_term_memory_cn.md`：旧项目历史经验、默认业务语境、容易踩坑的上下文

## 3. 推荐阅读顺序

### 3.1 通用改动

适用于还没明确要改哪块功能时：

1. [README.md](../README.md)
2. [AI_DEVELOPMENT_KNOWLEDGE_BASE.md](./AI_DEVELOPMENT_KNOWLEDGE_BASE.md)
3. [project_long_term_memory_cn.md](./project_long_term_memory_cn.md)
4. 再进入对应模块的路由和服务代码

### 3.2 改代码时优先看的真实入口

- 业务路由：`app/routes/*.py`
- 业务服务：`app/services/*.py`
- 数据模型：`app/models.py`
- 权限相关：`app/security.py`
- 项目上下文：`app/project_context.py`
- Vue 应用壳与全局辅助：`frontend/src/components/AppShell.vue`（含项目切换、会话退出、`Ctrl/Cmd + K` 全局页面搜索，以及“总览 + 模块分组 + 二级功能”侧边导航）
- 历史 URL 兼容映射：`app/routes/legacy_spa.py`；旧业务链接会重定向到 `/app/*`，不再渲染模板页面
- Vue 前端工作区：`frontend/src/`（路由、Pinia 状态、Axios 数据层与页面组件）；生产构建由 `app/routes/spa.py` 在登录后的 `/app/` 提供
- SPA JSON API：`app/routes/api_v1.py`（`/api/v1`，复用登录态、权限和当前项目上下文；会话接口位于 `/session/*`，权限管理接口位于 `/security/*`）
- Vue 认证页：`frontend/src/views/AuthPage.vue`；`/login`、`/forbidden`、`/logout` 仅保留兼容跳转，Jinja/Bootstrap 认证模板已移除
- Web 自动化 SPA：`frontend/src/views/WebAutomationPage.vue`；环境、脚本、定位器（按页面功能分组筛选）、运行回放与产物接口位于 `/api/v1/ui-automation/*`
- Android 自动化 SPA：`frontend/src/views/AndroidAutomationPage.vue`；流程预设/步骤、设备批量配置与标注、执行产物/停止、异常批量重试接口位于 `/api/v1/android-automation/*`

## 4. 按任务跳转

### 4.1 接口自动化 / ShowDoc 录入 / 用例设计

先看：

1. [api_automation_workflow_rules_cn.md](./api_automation_workflow_rules_cn.md)
2. [AI_DEVELOPMENT_KNOWLEDGE_BASE.md](./AI_DEVELOPMENT_KNOWLEDGE_BASE.md)

再看代码入口：

- `app/routes/api_v1.py`
- `app/services/testcase_service.py`
- `app/services/execution_service.py`

适用问题：

- 给一份 ShowDoc / YYDocs 链接自动生成用例
- 保存到某项目某模块
- 执行正向用例，再补异常/边界用例

### 4.2 权限系统 / 角色 / 项目成员 / 数据隔离

先看：

1. [permission_system_design_draft_cn.md](./permission_system_design_draft_cn.md)
2. [AI_DEVELOPMENT_KNOWLEDGE_BASE.md](./AI_DEVELOPMENT_KNOWLEDGE_BASE.md)

再看代码入口：

- `app/models.py`
- `app/security.py`
- `app/services/security_service.py`
- `app/routes/auth.py`
- `app/routes/admin.py`
- `app/project_context.py`

适用问题：

- 登录态
- 角色权限码
- 项目成员访问级别
- 菜单显示与后端授权
- Vue 权限页按权限码隐藏未授权页签；接口仍必须保留独立的 401/403 校验
- 审计日志

### 4.3 架构理解 / 新人接手 / 整体设计回顾

先看：

1. [AI_DEVELOPMENT_KNOWLEDGE_BASE.md](./AI_DEVELOPMENT_KNOWLEDGE_BASE.md)
2. [01_architecture.md](./01_architecture.md)
3. [project_long_term_memory_cn.md](./project_long_term_memory_cn.md)

适用问题：

- 这个项目最初想做什么
- 当前实际架构和早期设计差了多少
- 哪些地方已经落地，哪些还只是规划

### 4.4 边界测试 / 用例补全 / 测试设计

先看：

1. [09_boundary_test_design.md](./09_boundary_test_design.md)
2. [api_automation_workflow_rules_cn.md](./api_automation_workflow_rules_cn.md)

适用问题：

- 正向用例之后怎么补边界
- 如何组织异常场景
- 测试设计如何和平台数据结构对齐

如果涉及“批量执行明细提交性能”，直接看：

- `app/services/execution_service.py`（`add_details_batch` 与 `_run_batch`）
- `tests/test_execution_batch_detail_commit.py`

### 4.5 UI 自动化 / Playwright / 回归

先看：

1. [web_automation_workflow_rules_cn.md](./web_automation_workflow_rules_cn.md)
2. [docs/ui_automation/python_playwright_template/README.md](./ui_automation/python_playwright_template/README.md)

如果是通过 Codex 技能工作，再看：

- `.codex/skills/ui-auto-tester/SKILL.md`

适用问题：

- 生成 UI 自动化脚本
- 套用 Playwright 模板
- 跑回归门禁

如果涉及 UI 自动化列表性能（N+1），优先看：

- `app/routes/ui_automation.py`
- `app/services/ui_automation_service.py`
- `tests/test_ui_automation_artifact_batching.py`
- `tests/test_ui_automation_scripts_batching.py`

### 4.5.2 平台界面改版 / 共享布局 / 交互规范

先看：

1. [ui_design_system_cn.md](./ui_design_system_cn.md)
2. [AI_DEVELOPMENT_KNOWLEDGE_BASE.md](./AI_DEVELOPMENT_KNOWLEDGE_BASE.md)

适用问题：

- 统一左侧导航、顶部栏、用户信息与页面框架
- 资源管理页采用 Float QA，执行/记录/报告详情采用 Test Stage，两套主题共用同一壳层
- 调整列表、详情、筛选、弹窗和操作栏
- 检查快速导航、软导航和响应式行为
- 将页面渐进迁移到 Vue 3 + Ant Design Vue 前端工作区

### 4.5.1 Android APK 下载 / 安装 / 启动校验

先看：
1. [android_ui_automation_manual_cn.md](./android_ui_automation_manual_cn.md)
2. [AI_DEVELOPMENT_KNOWLEDGE_BASE.md](./AI_DEVELOPMENT_KNOWLEDGE_BASE.md)

再看代码入口：
- `app/routes/android_ui_automation.py`
- `app/services/android_ui_automation_service.py`
- `app/services/android_ui_automation_worker.py`
- `scripts/run_android_ui_automation_worker.py`

适用问题：
- 给 APK 下载链接做自动下载、安装、启动和截图校验
- 想知道 Android Worker 如何启动
- 想排查 ADB / AAPT / 设备连接问题
- 想确认页面操作路径和验收口径

### 4.6 历史会话迁移 / 旧项目记忆来源

按需看：

1. [codex_openai_history_migration.md](./codex_openai_history_migration.md)

适用问题：

- 想追溯这些中文长期记忆文档是怎么来的
- 想知道旧 `openai` 登录会话和当前 `apikey` 线程之间的关系

## 5. 文档优先级分层

### 5.1 默认高优先级

这些文档几乎任何改动前都值得先看：

- [README.md](../README.md)
- [AI_DEVELOPMENT_KNOWLEDGE_BASE.md](./AI_DEVELOPMENT_KNOWLEDGE_BASE.md)
- [project_long_term_memory_cn.md](./project_long_term_memory_cn.md)
- [DOC_INDEX.md](./DOC_INDEX.md)

### 5.2 任务触发型

只有在对应任务里再深入：

- [api_automation_workflow_rules_cn.md](./api_automation_workflow_rules_cn.md)
- [web_automation_workflow_rules_cn.md](./web_automation_workflow_rules_cn.md)
- [permission_system_design_draft_cn.md](./permission_system_design_draft_cn.md)
- [01_architecture.md](./01_architecture.md)
- [09_boundary_test_design.md](./09_boundary_test_design.md)
- [codex_openai_history_migration.md](./codex_openai_history_migration.md)

### 5.3 参考型

不是默认入口，但在特定问题上有价值：

- [docs/ui_automation/python_playwright_template/README.md](./ui_automation/python_playwright_template/README.md)
- [android_ui_automation_manual_cn.md](./android_ui_automation_manual_cn.md)
- [ui_design_system_cn.md](./ui_design_system_cn.md)
- [ui_redesign_demo.html](./ui_redesign_demo.html)

### 5.4 Skill 文档

这些通常不是“默认先读”，而是当任务命中对应技能时才进入：

- `.codex/skills/api-auto-orchestrator/SKILL.md`
- `.codex/skills/showdoc-api-auto-test/SKILL.md`
- `.codex/skills/ui-auto-tester/SKILL.md`
- `.codex/skills/architecture-diagram/SKILL.md`

## 6. 维护建议

以后新增文档时，尽量同步更新这份索引，至少补这三项：

- 这份文档解决什么问题
- 哪类任务要读它
- 它属于“默认必读”还是“按需进入”

这样后续 AI 才不会再次把时间花在“先找文档入口”上。
