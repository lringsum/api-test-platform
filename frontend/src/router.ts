import { createRouter, createWebHistory } from 'vue-router'
import DashboardPage from './views/DashboardPage.vue'
import ProjectsPage from './views/ProjectsPage.vue'
import ModulesPage from './views/ModulesPage.vue'
import EnvironmentsPage from './views/EnvironmentsPage.vue'
import VariablesPage from './views/VariablesPage.vue'
import ScenariosPage from './views/ScenariosPage.vue'
import TestcasesPage from './views/TestcasesPage.vue'
import ExecutionsPage from './views/ExecutionsPage.vue'
import SecurityPage from './views/SecurityPage.vue'
import WebAutomationPage from './views/WebAutomationPage.vue'
import AndroidAutomationPage from './views/AndroidAutomationPage.vue'
import AuthPage from './views/AuthPage.vue'

export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', name: 'login', component: AuthPage, meta: { title: '登录' } },
    { path: '/forbidden', name: 'forbidden', component: AuthPage, meta: { title: '访问受限' } },
    { path: '/', name: 'dashboard', component: DashboardPage, meta: { title: '仪表盘', description: '查看当前项目测试资源与执行状态' } },
    { path: '/projects', name: 'projects', component: ProjectsPage, meta: { title: '项目资源', description: '统一维护项目、模块与测试资源范围' } },
    { path: '/modules', name: 'modules', component: ModulesPage, meta: { title: '模块管理', description: '按业务边界组织接口用例与测试场景' } },
    { path: '/environments', name: 'environments', component: EnvironmentsPage, meta: { title: '环境配置', description: '管理请求基地址、通用请求头和环境变量' } },
    { path: '/variables', name: 'variables', component: VariablesPage, meta: { title: '变量管理', description: '维护项目级和环境级运行参数' } },
    { path: '/scenarios', name: 'scenarios', component: ScenariosPage, meta: { title: '场景编排', description: '串联用例、变量和覆盖规则形成业务链路' } },
    { path: '/testcases', name: 'testcases', component: TestcasesPage, meta: { title: '用例设计', description: '按模块和接口组织测试用例' } },
    { path: '/executions', name: 'executions', component: ExecutionsPage, meta: { title: '执行中心', description: '查看执行历史、运行状态与质量趋势' } },
    { path: '/security', name: 'security', component: SecurityPage, meta: { title: '权限管理', description: '查看账户、角色、项目成员与审计记录' } },
    { path: '/web-automation', name: 'web-automation', component: WebAutomationPage, meta: { title: 'Web 自动化', description: '管理 Playwright 脚本、定位器与运行队列' } },
    { path: '/android-automation', name: 'android-automation', component: AndroidAutomationPage, meta: { title: 'Android 自动化', description: '编排移动端流程、任务与执行记录' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
