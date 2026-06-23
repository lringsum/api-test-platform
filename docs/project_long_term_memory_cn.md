# 项目长期记忆

这份文档是给当前项目 `D:\work\test_web\api-test-platform` 用的长期上下文。

它综合了两部分信息：

- 旧 `openai` 登录模式下的历史项目对话
- 当前仓库代码里已经落地的真实实现

目标不是写成介绍材料，而是让后续继续开发时，能尽快进入正确语境。

## 1. 这个项目到底是什么

这是一个以 Flask 为后端的测试平台，核心不是单一的“接口测试工具”，而是两条能力线并行：

- API 测试设计、保存、执行、报告
- UI 自动化脚本管理、定位器管理、执行、回放

从历史对话看，真正高频使用场景是：

- 读取 ShowDoc / YYDocs 接口文档
- 自动生成测试用例
- 把用例配置进测试后台
- 选择项目和模块后执行
- 再补异常场景、边界场景和回归验证

## 2. 项目里的高频业务语境

历史会话里反复出现的业务上下文：

- 项目：`天机`
- 模块：`素材库`、`素材文件夹`、`素材工单`
- 文档来源：`https://yydocs.yyxxgame.com/...`
- 目标动作：
  - 先生成一条正向用例
  - 保存到平台
  - 执行验证
  - 再补异常用例

这说明平台并不是“纯演示型工具”，而是已经被拿来做真实业务接口测试录入与执行。

## 3. 当前代码结构里最重要的真实约束

### 3.1 静态资源真实来源

当前运行时生效的静态资源主要来自 `public/`，不是 `app/static/`。

这个坑在历史改动里反复出现过。改样式或脚本时，要优先确认真实入口是否在：

- `public/css/app.css`
- `public/js/app.js`

### 3.2 当前项目上下文是平台主轴

项目存在“当前项目”会话上下文，而且已经接到安全层。

关键文件：

- [project_context.py](D:/work/test_web/api-test-platform/app/project_context.py)
- [security.py](D:/work/test_web/api-test-platform/app/security.py)

很多页面和接口都不是“全局无条件可见”，而是跟当前 `project_id` 绑定。

### 3.3 数据库当前默认是本地 SQLite

当前项目默认运行形态是本地 SQLite，数据库文件在：

- `instance/app.db`

历史上讨论过 `Vercel + PostgreSQL`，但后续又有一次明确回收，改回本地 SQLite 优先。

结论：

- 现在默认开发语境应当认为它是“本地单机可迭代”平台
- 讨论部署时要特别确认是不是重新打开远端数据库路线

### 3.4 用例执行会写回环境变量

执行链路里，提取值会回写环境变量。

关键文件：

- [execution_service.py](D:/work/test_web/api-test-platform/app/services/execution_service.py)
- [variable_service.py](D:/work/test_web/api-test-platform/app/services/variable_service.py)

这意味着执行并不完全“无状态”：

- 一次登录接口跑完后，可能把 token 写回环境变量
- 后续用例执行结果可能依赖前一次提取结果

所以排查“为什么这次能过、下次不过”时，要想到环境变量副作用。

## 4. 权限体系已经不再是空白

历史对话早期判断过“权限功能还没开始做”，但当前代码已经进入了“基础权限体系已落地”的状态。

现在已经存在：

- 用户：`User`
- 角色：`Role`
- 权限：`Permission`
- 项目成员：`ProjectMember`
- 审计日志：`AuditLog`

关键文件：

- [models.py](D:/work/test_web/api-test-platform/app/models.py)
- [security.py](D:/work/test_web/api-test-platform/app/security.py)
- [security_service.py](D:/work/test_web/api-test-platform/app/services/security_service.py)
- [auth.py](D:/work/test_web/api-test-platform/app/routes/auth.py)
- [admin.py](D:/work/test_web/api-test-platform/app/routes/admin.py)

已经具备的能力：

- 登录 / 退出
- 基于 session 的登录态
- 角色和权限码
- 项目成员访问级别
- 管理后台里的用户、角色、项目成员、审计页

所以以后再聊权限，不要从“0 到 1 设计”开始，而要从“当前实现补齐到可上线级别”开始。

## 5. 历史上最常改的页面和区域

从旧会话看，反复被优化的区域主要有：

- 测试用例列表页
- 测试用例详情/编辑页
- UI 回放详情页
- 脚本版本页
- 项目管理页
- 模块管理页

说明这套后台的主要问题过去集中在：

- 信息密度
- 布局比例
- 操作按钮摆放
- 筛选流转
- “当前项目 / 当前模块 / 当前接口”的上下文一致性

因此后续改后台 UI 时，优先考虑：

- 是否破坏原来的项目上下文链路
- 是否破坏筛选条件传递
- 是否破坏执行入口和跳转入口

## 6. API 自动化这条线的默认工作方式

从历史会话可归纳出一个默认共识：

1. 用户给 ShowDoc / YYDocs 链接
2. 先读接口定义
3. 先生成一条正向用例
4. 放进已有项目、已有模块、已有环境
5. 执行一次验证
6. 再根据反馈补异常场景、边界场景、批量改名或规则收敛

对应代码入口大致在：

- [ai_parser.py](D:/work/test_web/api-test-platform/app/routes/ai_parser.py)
- [testcase.py](D:/work/test_web/api-test-platform/app/routes/testcase.py)
- [execution_service.py](D:/work/test_web/api-test-platform/app/services/execution_service.py)

## 7. 这项目里最值得保护的资源

即使不谈“权限产品设计”，从安全和运维视角看，优先级最高的是：

- 环境
- 变量
- 用例
- 场景
- 执行记录
- UI 自动化脚本

原因：

- 环境和变量容易带真实地址、token、账号
- 用例和场景会直接影响测试结果
- 脚本和定位器会影响 UI 自动化执行稳定性

## 8. 这份长期记忆最想保留下来的默认判断

后续如果没有额外说明，优先沿用下面这些判断：

- 这个平台已经被拿来承接真实业务接口测试，不是纯演示项目
- 历史上最有价值的经验集中在 ShowDoc 自动化链路和后台 UI 收敛
- 做接口自动化时，默认先正向、再异常、再边界
- 做后台页面调整时，要特别注意“当前项目 / 当前模块 / 当前接口”的上下文连续性
- 聊权限时，默认是在现有骨架上补齐，不是完全重做

## 9. 配套文档

这份长期记忆建议和下面两份一起看：

- [api_automation_workflow_rules_cn.md](D:/work/test_web/api-test-platform/docs/api_automation_workflow_rules_cn.md)
- [permission_system_design_draft_cn.md](D:/work/test_web/api-test-platform/docs/permission_system_design_draft_cn.md)
