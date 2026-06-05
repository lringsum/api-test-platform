# 第一阶段：整体架构设计

## 1. 平台目标

构建一个本地可运行的 Flask 接口自动化测试 Web 平台，覆盖以下闭环：

接口文档 -> AI 解析 -> 生成用例 -> 保存 -> 执行 -> 查看结果 -> 生成报告

平台必须具备以下核心能力：

- 项目管理
- 模块管理
- 环境管理
- 变量管理
- 接口用例管理
- AI 接口解析
- Prompt 模板管理
- 接口执行
- 断言验证
- 执行结果与测试报告

## 2. 技术架构

### 后端

- Flask
- SQLAlchemy
- SQLite
- requests

### 前端

- Flask + Jinja2
- Bootstrap 5 CDN

### 设计原则

- 页面、路由、服务、执行引擎分层清晰
- 用例采用统一 JSON 结构
- 执行过程全链路可追踪
- 默认支持 SQLite，后续可平滑切换 MySQL
- 优先保证本地可运行和页面可用

## 3. 分层设计

### 3.1 表现层

负责后台管理页面渲染，使用 Jinja2 模板和 Bootstrap 5 组件实现：

- 左侧导航栏
- 顶部标题栏
- 表格、表单、卡片布局
- 执行结果与报告展示

### 3.2 路由层

使用 Flask Blueprint 按模块拆分：

- `dashboard`
- `project`
- `module`
- `environment`
- `variable`
- `testcase`
- `ai_parser`
- `execution`
- `report`
- `prompt_template`

### 3.3 服务层

封装业务逻辑与数据校验，避免路由中堆积业务代码：

- 项目服务
- 模块服务
- 环境服务
- 变量服务
- 用例服务
- AI 服务
- 执行服务
- 报告服务
- Prompt 服务

### 3.4 工具层

负责底层通用能力：

- 变量替换
- URL 构建
- 断言引擎
- 变量提取
- JSON 处理
- AI mock 解析

### 3.5 数据层

使用 SQLAlchemy 管理模型与持久化，核心实体包括：

- `Project`
- `Module`
- `Environment`
- `Variable`
- `TestCase`
- `PromptTemplate`
- `Execution`
- `ExecutionDetail`
- `Report`

## 4. 核心业务链路

### 4.1 用例管理链路

项目 -> 模块 -> 用例 -> 保存 -> 编辑 -> 执行

### 4.2 AI 生成链路

接口文档 -> Prompt 模板 -> AI 解析 -> JSON 校验 -> 保存为用例

### 4.3 执行链路

环境配置 -> 变量合并 -> base_url 拼接 -> 变量替换 -> requests 调用 -> 断言执行 -> 变量提取 -> 保存执行结果

### 4.4 报告链路

执行批次 -> 执行明细 -> 统计汇总 -> 失败摘要 -> 报告展示

## 5. 页面规划

平台至少包含以下页面：

- Dashboard
- 项目管理页
- 模块管理页
- 环境管理页
- 变量管理页
- 用例列表页
- 用例编辑页
- AI 解析页
- 执行页面
- 执行历史页
- 执行详情页
- Prompt 模板管理页
- 报告详情页

## 6. 目录结构

```text
api-test-platform/
├── app/
│   ├── models.py
│   ├── routes/
│   ├── services/
│   ├── templates/
│   ├── static/
│   └── utils/
├── docs/
├── config.py
├── run.py
├── requirements.txt
└── README.md
```

## 7. 阶段实施映射

后续代码实现严格按以下顺序推进：

1. 整体架构设计
2. 数据库模型
3. 后端服务层
4. 后端路由
5. 前端页面
6. 接口执行引擎
7. AI 解析模块
8. 测试报告
9. 边界值测试设计
10. README 和运行说明

## 8. 本阶段交付内容

本阶段仅创建项目骨架和架构文档，不实现业务逻辑代码。

已创建目录：

- `app/routes`
- `app/services`
- `app/templates`
- `app/static`
- `app/utils`
- `docs`
- `instance`

后续阶段将在该骨架上逐步补全可运行项目。
