# API Test Platform

一个基于 Flask 的测试平台，覆盖三条主线能力：

- API 测试设计、执行、报告
- UI 自动化脚本管理、执行、回放
- Android APK 下载、安装、启动与可配置 UI 流程校验

项目当前以本地 SQLite 为默认运行形态，适合单机开发、联调和功能迭代。

## AI 接手须知

后续 AI 接手这个仓库时，默认先记住这几条：

- 这是一个 Flask 单体测试平台，主线包括 API 自动化、浏览器 UI 自动化和 Android UI 自动化
- 默认数据库是本地 SQLite，路径为 `instance/app.db`
- 当前真正生效的静态资源目录是 `public/`，不是 `app/static/`
- 系统存在“当前项目”上下文，很多页面和接口会按 `project_id` / `active_project_id` 过滤
- API 执行会把提取值回写到环境变量，执行链路带状态副作用
- 权限系统已经有骨架，不要按“从 0 到 1 的全新设计题”理解

## AI 文档入口

后续无论是人还是 AI，文档入口统一从这里进入：

- [AI 文档索引](docs/DOC_INDEX.md)

三份核心文档的职责分工：

- `DOC_INDEX.md`：文档导航，告诉你按任务该读哪份
- `AI_DEVELOPMENT_KNOWLEDGE_BASE.md`：当前代码真实运行机制
- `project_long_term_memory_cn.md`：历史语境、高频业务场景、默认工作方式

## 核心能力

- 项目、模块、环境、变量管理
- API 用例管理
- 场景编排与串行执行
- AI 辅助生成 API 测试用例
- API 执行历史与测试报告
- UI 自动化脚本管理
- UI 定位器库
- Playwright Worker 执行与产物回放
- Android Worker 执行 APK 与设备/流程校验
- 用户、角色、项目成员、审计日志

## 技术栈

- Backend: Flask, Flask-SQLAlchemy, SQLAlchemy
- Database: SQLite
- Frontend: Vue 3, Ant Design Vue, Axios, Pinia, Tailwind CSS, ECharts, highlight.js
- New frontend workspace: Vue 3, Ant Design Vue, Axios, Pinia, Tailwind CSS, ECharts, highlight.js
- Execution: requests, pytest, playwright

## 目录概览

```text
api-test-platform/
├── app/          # Flask 应用、路由、服务、模板、模型
├── api/          # 部署入口
├── docs/         # 架构与知识文档
├── public/       # 当前实际生效的静态资源
├── frontend/     # 独立 Vue 3 前端工作区（Vite）
├── scripts/      # 回归脚本、worker 启动、辅助脚本
├── instance/     # 本地运行数据与 SQLite 数据库
├── config.py
├── run.py
├── start_project.bat  # Windows 本地一键起服（迁移 + 两个 Worker + Web）
├── seed_data.py
└── requirements.txt
```

## 安装依赖

建议使用 Python 3.10+。

```bash
pip install -r requirements.txt
```

浏览器 UI 自动化还需要在每台执行机安装 Playwright 的 Chromium 二进制（Python 包本身不包含浏览器）：

```bash
python -m playwright install chromium
```

## 启动项目

Windows 本地联调推荐运行：

```bat
start_project.bat
```

它会执行数据库迁移，并在缺失时启动浏览器 UI Worker 和 Android UI Worker。只运行 Web 服务时可使用：

```bash
python run.py
```

默认访问地址：

- [http://127.0.0.1:5000](http://127.0.0.1:5000)

## Vue 前端工作区

Android automation is also available in the Vue workbench at `/app/android-automation`: flow presets and editable steps, task dispatch, run detail with screenshot/log evidence and stop controls, device default/enable/disable/annotation operations, and exception-center batch retry. Its JSON API is scoped under `/api/v1/android-automation/*` and keeps the existing Android permissions and project scope.

Authentication is fully Vue-rendered at `/app/login` and `/app/forbidden`. The legacy `/login`, `/forbidden`, and `/logout` URLs are retained only as compatibility redirects; session login/logout is handled by `/api/v1/session/login` and `/api/v1/session/logout`.

`frontend/` 是基于现有 Float QA 浅色设计系统重构的 Vue 3 工作区，包含仪表盘、项目资源、模块管理、环境配置、变量管理、用例设计、场景编排、执行中心、权限管理、认证与 Web 自动化页面。生产构建后，Flask 会在登录保护下通过 `/app/` 提供该 SPA；默认数据源为同源的 `/api/v1` JSON API（会复用当前登录态、权限和项目上下文）。Web 自动化工作台覆盖 Playwright 脚本详情/版本、运行环境、定位器 CRUD 与批量导入导出/批量操作、按页面功能分组筛选定位器、运行回放和产物预览；新建 Web 自动化业务脚本默认关联并复用平台已有的用户登录前置脚本，只有明确关闭登录前置时才跳过。当前版本不提供 AI 解析、AI 生成、AI 修复或 Prompt 模板业务入口。权限页会按 `user:manage`、`role:manage`、`project_member:manage`、`audit:view` 显示对应页签，所有接口仍由后端独立校验。执行中心和场景执行均会调用既有服务，保留环境变量合并、步骤覆盖、失败继续、提取值回写及报告/明细语义。只有显式设置 `VITE_USE_DEMO_DATA=true` 时，读取类页面才会回退到演示数据。

```bash
cd frontend
npm install
npm run dev
```

构建生产静态资源：

```bash
npm run build
```

开发服务器默认地址为 [http://127.0.0.1:5173](http://127.0.0.1:5173)。构建完成并启动 Flask 后，可从 [http://127.0.0.1:5000/app/](http://127.0.0.1:5000/app/) 访问应用。历史业务 URL 会由服务端映射到等价的 Vue 路由并保留查询参数；旧模板、Bootstrap 与旧全局静态资源已移除。

如需局域网访问，可设置：

```powershell
$env:HOST="0.0.0.0"
$env:PORT="5000"
$env:FLASK_DEBUG="false"
python run.py
```

## 数据位置

SQLite 数据库固定在：

```text
instance/app.db
```

如果需要重置本地数据，停止应用后删除这个文件即可。

## 初始化示例数据

```bash
python seed_data.py
```

默认安全初始化由应用启动自动完成；`seed_data.py` 用于补充演示项目、模块、环境、变量和测试用例。

默认管理员账号：

- 用户名：`admin`
- 密码：`admin123`

## 运行注意事项

- 当前 Flask 静态资源实际来自 `public/`，不是 `app/static/`
- 项目已接入 Flask-Migrate/Alembic，结构变更请通过 migration 流程提交
- Android 任务会在执行前检查 ADB 与 `aapt.exe`；依赖缺失只会使该任务失败，不会使常驻 Worker 下线
- 项目内置 Android APK 解析工具 `tools/android/aapt.exe`；如需替换，请核对该目录 README 中的来源和校验值
- Android 设备控制仍依赖执行机上的 ADB/模拟器或真机；可通过 `ANDROID_UI_ADB_PATH` 覆盖默认 MuMu ADB 路径
- 默认情况下，任务发现本机 MuMu 设备 `127.0.0.1:<端口>` 离线时会自动拉起对应实例，最长等待 90 秒；可用 `ANDROID_UI_AUTO_START_DEVICE=false` 关闭，或通过 `ANDROID_UI_DEVICE_START_WAIT_SECONDS` 调整等待时间。USB 和远程设备不会被自动拉起
- Android 流程中的 OCR/视觉增强会尝试使用本机 `http://127.0.0.1:4723` 的 Appium 服务；未部署时会记日志降级，OCR 步骤需要补齐该服务
- `scripts/apk_ui_batch_check.py` 是单独的历史批处理工具，当前仍含个人 WorkBuddy 输入/输出目录，不属于可移植的项目起服或 Worker 流程
- API 执行会把提取变量回写到环境变量，运行结果可能带状态副作用
- 项目存在“当前项目”会话上下文，很多页面和接口会按当前项目自动过滤

## 常用脚本

- `python seed_data.py`
- `python scripts/run_ui_regression.py`
- `python scripts/run_backend_regression.py`
- `python scripts/test_ui_routes.py`
- `python scripts/test_api_gate.py`
- `python scripts/run_ui_automation_worker.py`
  - single-instance worker with heartbeat + stale-run recovery
  - preferred launcher: `.\.venv\Scripts\python.exe scripts/run_ui_automation_worker.py`
- `python scripts/run_android_ui_automation_worker.py`
  - Android APK/UI flow worker; auto-starts an offline local MuMu target by default, then requires usable ADB access and `aapt.exe`
  - preferred launcher: `.\.venv\Scripts\python.exe scripts/run_android_ui_automation_worker.py`

## 后续开发建议

无论是人还是 AI，在改动前都优先看这两处：

1. `docs/AI_DEVELOPMENT_KNOWLEDGE_BASE.md`
2. 对应功能的 `app/routes/*.py` 与 `app/services/*.py`

这样最不容易改偏。
