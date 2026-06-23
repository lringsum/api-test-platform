# API Test Platform

一个基于 Flask 的测试平台，覆盖两条主线能力：

- API 测试设计、执行、报告
- UI 自动化脚本管理、执行、回放

项目当前以本地 SQLite 为默认运行形态，适合单机开发、联调和功能迭代。

## AI 接手须知

后续 AI 接手这个仓库时，默认先记住这几条：

- 这是一个 Flask 单体测试平台，主线同时包括 API 自动化和 UI 自动化
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
- 用户、角色、项目成员、审计日志

## 技术栈

- Backend: Flask, Flask-SQLAlchemy, SQLAlchemy
- Database: SQLite
- Frontend: Jinja2, Bootstrap 5, plain JavaScript
- Execution: requests, pytest, playwright

## 目录概览

```text
api-test-platform/
├── app/          # Flask 应用、路由、服务、模板、模型
├── api/          # 部署入口
├── docs/         # 架构与知识文档
├── public/       # 当前实际生效的静态资源
├── scripts/      # 回归脚本、worker 启动、辅助脚本
├── instance/     # 本地运行数据与 SQLite 数据库
├── config.py
├── run.py
├── seed_data.py
└── requirements.txt
```

## 安装依赖

建议使用 Python 3.10+。

```bash
pip install -r requirements.txt
```

## 启动项目

```bash
python run.py
```

默认访问地址：

- [http://127.0.0.1:5000](http://127.0.0.1:5000)

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
- 项目没有启用正式 migration 体系，模型变更需要额外考虑数据库兼容
- API 执行会把提取变量回写到环境变量，运行结果可能带状态副作用
- 项目存在“当前项目”会话上下文，很多页面和接口会按当前项目自动过滤

## 常用脚本

- `python seed_data.py`
- `python scripts/run_ui_regression.py`
- `python scripts/test_ui_routes.py`
- `python scripts/test_api_gate.py`
- `python scripts/run_ui_automation_worker.py`

## 后续开发建议

无论是人还是 AI，在改动前都优先看这两处：

1. `docs/AI_DEVELOPMENT_KNOWLEDGE_BASE.md`
2. 对应功能的 `app/routes/*.py` 与 `app/services/*.py`

这样最不容易改偏。
