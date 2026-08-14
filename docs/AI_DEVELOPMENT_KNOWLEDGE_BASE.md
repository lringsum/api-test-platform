# Float QA 开发知识库

## 当前架构

Float QA 的用户界面已完全迁移到 Vue 3 单页应用。`frontend/` 使用 Vue 3、Vite、Ant Design Vue、Axios、Pinia、Tailwind CSS、ECharts 和 highlight.js；生产构建由 Flask 在 `/app/` 提供。所有业务数据通过 `/api/v1/*` JSON API 访问，后端仍负责会话、权限、可访问项目范围和活动项目上下文。

Flask 当前只注册四类运行时路由：`api_v1`、认证兼容路由、SPA 资源路由和历史 GET URL 的 SPA 映射。历史业务 URL 由 `app/routes/legacy_spa.py` 重定向到等价 `/app/*` 路径并保留查询参数；它不再渲染 Jinja 页面。Jinja 模板、Bootstrap 和 `public/css/app.css`、`public/js/app.js` 已退出运行时。

```text
Vue SPA (frontend/) -> /api/v1 JSON API -> Flask services -> SQLAlchemy models -> SQLite/runtime artifacts
```

## 前端约定

- 新页面在 `frontend/src/views/`，全局导航、项目切换、登出和 `Ctrl/Cmd + K` 页面搜索在 `frontend/src/components/AppShell.vue`。侧边导航保留“总览 + 接口测试、UI 自动化、执行中心、智能辅助、权限管理”的模块分组和二级功能层级；当前路由所属分组会自动展开。
- 右侧详情与编辑抽屉采用统一加宽规格；图表使用 ECharts，代码展示使用 highlight.js。
- API 调用集中在 `frontend/src/services/`，跨页面会话与项目状态使用 Pinia。
- Web 自动化定位器直接复用 `pageName` 作为页面功能分类；定位器页提供按功能点击筛选、关键词检索和功能列展示。筛选条件变化或项目切换时必须清空勾选并回到第一页，避免批量操作命中隐藏记录。
- 登录和受限页由 `AuthPage.vue` 渲染；`/login`、`/forbidden`、`/logout` 仅保留兼容入口。会话接口为 `/api/v1/session/login` 和 `/api/v1/session/logout`。
- 不要重新引入模板、Bootstrap、jQuery 或全局脚本式页面行为。

## 后端约定

- Web 自动化执行回放只对失败或超时等终态做失败分析；`queued`、`pending`、`running` 不得提前显示异常。失败步骤中的定位异常优先区分为“元素定位不到”和“元素不唯一”，后者从 Playwright `resolved to N elements` 信息提取命中数量。
- Web 自动化 Worker 执行期间持续消费 `runtime-steps.jsonl`，使用 `attempt + sequence` 合并同一步骤的 `running` 与终态事件，并增量写入 `UiAutomationRunStep`；详情抽屉仅在活动状态下每秒轮询，终态、关闭抽屉或页面隐藏后停止。
- Android 自动化在运行记录创建后即按流程快照预创建步骤，Worker 逐步提交 `running/passed/failed`；详情抽屉每秒轮询并展示步骤进度。失败或手动停止时，当前步骤分别收口为 `failed/stopped`，尚未执行步骤收口为 `skipped`。

- `app/routes/api_v1.py` 是 Vue 页面使用的业务 HTTP 边界；在此层复用现有 service，而不是把业务规则搬到前端。
- 新增或修改数据结构时优先提交 migration；`AUTO_DB_BOOTSTRAP` 和 `AUTO_DB_COMPAT_PATCH` 仅用于本地兼容，不应替代迁移。
- `SecurityService.ensure_default_data()` 只在没有用户时创建本地开发管理员 `admin/admin123`。生产环境必须改用受控账号。
- Web 与 Android 自动化仍由既有 service/worker 执行，API 负责权限与项目范围校验，Vue 仅负责操作界面和产物展示。
- Web 自动化脚本版本通过 `dependencies` 关联平台已有的登录脚本。Worker 会在同一页面上下文中先执行登录前置脚本，再执行业务脚本；AI 和手工创建默认关联该依赖，只有明确传入 `needLogin=false` 才跳过。业务脚本不复制登录代码，登录凭据仍由运行环境变量 `UI_AUTOMATION_LOGIN_USERNAME`、`UI_AUTOMATION_LOGIN_PASSWORD` 注入。

## 验证

修改 Vue 页面、路由、认证或全局辅助后运行：

```powershell
.\.venv\Scripts\python.exe .\scripts\run_ui_regression.py
```

该门禁依次验证历史 URL 到 Vue 深链的映射、SPA 壳层与认证兼容行为，以及主要模块的 `/api/v1` 合同。前端构建验证：

```powershell
cd frontend
npm run build
```

## 修改清单

1. 页面能力修改：同步检查 Vue 视图、service 和 API 合同。
2. 认证或权限修改：验证未登录重定向、受限页、会话登出与 API 授权边界。
3. 路由修改：验证 `/app/*` 直接打开及对应历史 URL 的查询参数保留。
4. 文档修改：同步更新 `README.md`、`docs/DOC_INDEX.md` 和本文件。
