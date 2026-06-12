# Flask 接口自动化测试 Web 平台

一个基于 Flask + SQLAlchemy + SQLite + Jinja2 + Bootstrap 5 的接口自动化测试平台，支持接口文档、AI 解析、用例管理、环境管理、变量替换、接口执行、断言验证、执行报告等完整流程。

当前版本已改为本地 SQLite 数据库，数据默认保存在项目目录下的 `instance/app.db`，不会再读取公网数据库连接串。

## 1. 项目特性

- 项目管理
- 模块管理
- 环境管理
- 变量管理
- 接口用例管理
- AI 接口文档解析
- Prompt 模板管理
- 接口执行引擎
- 断言系统
- 执行历史与执行详情
- 自动生成测试报告

## 2. 技术栈

- 后端：Flask
- ORM：SQLAlchemy / Flask-SQLAlchemy
- 数据库：SQLite
- 前端：Flask + Jinja2 + Bootstrap 5
- HTTP 请求：requests

## 3. 项目结构

```text
api-test-platform/
├─ app/
├─ api/
├─ docs/
├─ config.py
├─ run.py
├─ seed_data.py
├─ requirements.txt
└─ README.md
```

## 4. 安装依赖

建议使用 Python 3.10 及以上版本。

```bash
pip install -r requirements.txt
```

## 5. 启动项目

```bash
python run.py
```

启动后访问：

[http://127.0.0.1:5000/](http://127.0.0.1:5000/)

如果需要局域网访问，可以设置：

```powershell
$env:HOST="0.0.0.0"
$env:PORT="5000"
$env:FLASK_DEBUG="false"
python run.py
```

## 6. 数据库位置

数据库文件固定为：

```text
instance/app.db
```

如果想重置数据，停止应用后删除这个文件即可。

## 7. 初始化示例数据

```bash
python seed_data.py
```

初始化后可看到示例：

- 项目
- 模块
- 环境
- 变量
- Prompt 模板
- 测试用例
- 执行记录

## 8. 默认配置

配置文件位于 `config.py`，当前可调配置包括：

- `SECRET_KEY`
- `AI_MODE`
- `DEFAULT_TIMEOUT`

数据库已固定为本地 SQLite，不再使用 `DATABASE_URL` 或 PostgreSQL 连接串。

## 9. 常见问题

### 9.1 页面打不开

- 确认已执行 `pip install -r requirements.txt`
- 确认已执行 `python run.py`
- 确认本地端口 `5000` 未被占用

### 9.2 AI 解析失败

- 确认已创建并启用 Prompt 模板
- 确认输入的是有效接口文档
- 确认当前 `AI_MODE=mock`

### 9.3 执行失败

- 检查环境 `base_url` 是否正确
- 检查变量是否已经配置
- 检查接口是否可访问
- 检查断言规则是否合理

## 10. 后续扩展建议

- 接入 Flask-Migrate
- 增加数据库备份与恢复
- 接入真实 AI 模型服务
- 扩展更多请求方法，如 PUT / DELETE
- 增加定时任务与批量执行
- 补充用户登录和权限控制
- 增加更完整的 JSONPath 语法
