# Float QA Vue 设计系统

## 技术边界

页面使用 Vue 3、Ant Design Vue 和 Tailwind CSS。请求由 Axios 服务层发起，跨页面状态由 Pinia 管理；图表使用 ECharts，代码内容使用 highlight.js。不要在 Vue 视图中引入 Bootstrap、jQuery、Jinja 模板片段或旧的全局脚本。

## 布局

`frontend/src/components/AppShell.vue` 提供唯一的认证后应用壳：侧边导航、页面标题、项目选择器、通知、账号菜单和 `Ctrl/Cmd + K` 全局搜索。页面必须使用该壳层并通过 Vue Router 导航。

详情和编辑操作默认使用右侧抽屉；抽屉宽度应使用统一的加宽规格，避免窄面板导致表单和代码难以阅读。列表筛选状态使用路由查询参数或页面状态保存，确保刷新和后退行为清晰。

## 可访问性与反馈

- 所有异步操作显示加载、成功和失败反馈。
- 空状态使用 Ant Design Vue 的 Empty 组件，并给出可执行的下一步。
- 危险操作必须二次确认。
- 图标按钮提供可读标签或 `aria-label`。

## 验证

设计系统、全局导航或认证页变更后，执行 `npm run build` 以及 `scripts/run_ui_regression.py`。门禁必须覆盖 SPA 直达、历史 URL 映射、认证兼容和对应 API 合同。
