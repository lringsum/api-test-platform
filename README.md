# Flask 接口自动化测试 Web 平台

一个基于 Flask + SQLAlchemy + SQLite + Jinja2 + Bootstrap 5 的接口自动化测试平台，支持接口文档 AI 解析、用例管理、环境管理、变量替换、接口执行、断言验证、执行报告等完整流程。

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
├── app/
├── docs/
├── config.py
├── run.py
├── seed_data.py
├── requirements.txt
└── README.md
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

如需让内网同事访问，可直接使用默认配置启动，服务会监听 `0.0.0.0:5000`。
同网段同事通过你的电脑局域网 IP 访问，例如：

- `http://你的内网IP:5000/`

也可以通过环境变量自定义监听地址和端口：

```powershell
$env:HOST="0.0.0.0"
$env:PORT="5000"
$env:FLASK_DEBUG="false"
python run.py
```

查看本机内网 IP：

```powershell
ipconfig
```

如果同事无法访问，请额外检查：

- Windows 防火墙是否放行 `5000` 端口
- 你和同事是否在同一内网/VPN
- 访问地址是否使用了你的局域网 IP，而不是 `127.0.0.1`

首次启动会自动创建数据库表。

## 6. 初始化示例数据

```bash
python seed_data.py
```

初始化完成后，你可以在页面中看到：

- 示例项目
- 示例模块
- 示例环境
- 示例变量
- 示例 Prompt 模板
- 示例登录用例
- 示例用户查询用例

## 7. 平台核心流程

### 7.1 手工创建流程

1. 创建项目
2. 创建模块
3. 创建环境
4. 创建变量
5. 手工新增测试用例
6. 进入执行页面发起执行
7. 查看执行历史、执行详情和测试报告

### 7.2 AI 生成流程

1. 进入 AI 解析页面
2. 输入接口文档
3. 选择 Prompt 模板
4. 生成标准 JSON 用例
5. 校验解析结果
6. 保存为正式用例
7. 进入执行页面执行

## 8. 标准用例 JSON 结构

```json
{
  "name": "登录成功",
  "method": "POST",
  "url": "/api/login",
  "headers": {},
  "params": {},
  "body": {},
  "extract": {
    "token": "data.token"
  },
  "assertions": [
    {
      "type": "status_code",
      "expected": 200
    },
    {
      "type": "json_path",
      "path": "code",
      "expected": 0
    }
  ]
}
```

## 9. 支持能力

### 9.1 执行引擎

- 拼接 `base_url`
- 替换变量 `${token}`
- 支持 `GET/POST`
- 使用 `requests` 发送请求
- 记录请求和响应
- 执行断言
- 提取变量
- 保存执行结果

### 9.2 断言支持

- `status_code`
- `json_path`
- `contains`
- `response_time`

### 9.3 AI 模块

- 输入接口文档
- 使用 Prompt 模板
- 输出标准 JSON 用例
- 支持 mock 模式
- JSON 校验
- 一键保存为用例

## 10. 默认配置

配置文件位于 `config.py`。

可配置项包括：

- `SECRET_KEY`
- `SQLALCHEMY_DATABASE_URI`
- `AI_MODE`
- `DEFAULT_TIMEOUT`

默认数据库：

```python
sqlite:///instance/app.db
```

## 11. 后续扩展建议

- 接入 Flask-Migrate
- 支持 MySQL
- 接入真实 AI 模型服务
- 支持更多请求方法，如 PUT、DELETE
- 支持定时任务与批量计划执行
- 支持用户登录和权限控制
- 支持更完整的 JSONPath 语法

## 12. 常见问题

### 12.1 页面打不开

请确认：

- 已执行 `pip install -r requirements.txt`
- 已执行 `python run.py`
- 本地端口 `5000` 未被占用
- 如为内网访问，已放行 Windows 防火墙入站规则

### 12.2 AI 解析失败

请确认：

- 已创建并启用 Prompt 模板
- 输入了有效接口文档
- 当前 `AI_MODE=mock`

### 12.3 执行失败

请检查：

- 环境 `base_url` 是否正确
- 变量是否已配置
- 请求接口是否可访问
- 断言是否合理

## 13. 相关文档

- [整体架构设计](file:///d:/work/test_web/api-test-platform/docs/01_architecture.md)
- [边界值测试设计](file:///d:/work/test_web/api-test-platform/docs/09_boundary_test_design.md)

## 14. License

本项目用于学习、演示和本地测试平台搭建。
