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
3. 真正落代码前，再回到对应的 `app/routes/*.py`、`app/services/*.py`、`app/templates/*.html`

## 2. 最小必读集

默认先看这 3 份，基本就能避免大多数改偏：

1. [README.md](../README.md)
2. [AI_DEVELOPMENT_KNOWLEDGE_BASE.md](./AI_DEVELOPMENT_KNOWLEDGE_BASE.md)
3. [project_long_term_memory_cn.md](./project_long_term_memory_cn.md)

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
- 前端模板：`app/templates/*.html`
- 前端静态资源：`public/css/app.css`、`public/js/app.js`

## 4. 按任务跳转

### 4.1 接口自动化 / ShowDoc 解析 / AI 生成用例

先看：

1. [api_automation_workflow_rules_cn.md](./api_automation_workflow_rules_cn.md)
2. [AI_DEVELOPMENT_KNOWLEDGE_BASE.md](./AI_DEVELOPMENT_KNOWLEDGE_BASE.md)

再看代码入口：

- `app/routes/ai_parser.py`
- `app/routes/testcase.py`
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

### 4.5 UI 自动化 / Playwright / 回归

先看：

1. [docs/ui_automation/ai_prompt_template.md](./ui_automation/ai_prompt_template.md)
2. [docs/ui_automation/python_playwright_template/README.md](./ui_automation/python_playwright_template/README.md)

如果是通过 Codex 技能工作，再看：

- `.codex/skills/ui-auto-tester/SKILL.md`

适用问题：

- 生成 UI 自动化脚本
- 套用 Playwright 模板
- 跑回归门禁

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
- [permission_system_design_draft_cn.md](./permission_system_design_draft_cn.md)
- [01_architecture.md](./01_architecture.md)
- [09_boundary_test_design.md](./09_boundary_test_design.md)
- [codex_openai_history_migration.md](./codex_openai_history_migration.md)

### 5.3 参考型

不是默认入口，但在特定问题上有价值：

- [docs/ui_automation/ai_prompt_template.md](./ui_automation/ai_prompt_template.md)
- [docs/ui_automation/python_playwright_template/README.md](./ui_automation/python_playwright_template/README.md)

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
