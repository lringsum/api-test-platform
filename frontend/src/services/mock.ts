import type { DashboardData, Execution, Project, TestCase } from '../types'

export const demoProjects: Project[] = [
  { id: 1, name: '会员增长', status: 'active', modules: 12, environments: 3, updatedAt: '2026-08-10 09:42', description: '会员旅程与交易链路的接口自动化验证。' },
  { id: 2, name: '投放平台', status: 'active', modules: 8, environments: 2, updatedAt: '2026-08-09 16:18', description: '广告投放与预算策略测试资产。' },
]

export const demoExecutions: Execution[] = [
  { id: 218, name: '用户登录接口回归', project: '会员增长', executionType: '接口测试', status: 'passed', duration: 138, startedAt: '2026-08-10 10:32:15', passRate: 100, total: 24, passed: 24, failed: 0 },
  { id: 217, name: '订单流程接口测试', project: '会员增长', executionType: '接口测试', status: 'failed', duration: 107, startedAt: '2026-08-10 09:15:42', passRate: 88, total: 25, passed: 22, failed: 3 },
]

export const demoDashboard: DashboardData = {
  stats: [
    { label: '项目', value: 12, hint: '当前团队管理的项目总数', tone: 'blue' },
    { label: '用例', value: 1258, hint: '当前项目的用例总数', tone: 'green' },
    { label: '场景', value: 320, hint: '当前项目的场景总数', tone: 'purple' },
    { label: '最近执行', value: 28, hint: '近 7 天执行的总次数', tone: 'red' },
  ],
  executions: demoExecutions,
  trend: { dates: ['08-04', '08-05', '08-06', '08-07', '08-08', '08-09', '08-10'], passed: [26, 34, 29, 40, 36, 30, 42], failed: [2, 4, 1, 3, 2, 5, 1] },
}

const demoCaseData = { method: 'POST', url: '/api/v1/auth/login', headers: {}, params: {}, body: { username: 'qa_user' }, extract: {}, assertions: [{ type: 'status_code', expected: 200 }], pre_script: { enabled: false, language: 'python', template_id: null, content: '' } }
export const demoTestcases: TestCase[] = [
  { id: 1, projectId: 1, project: '会员增长', moduleId: 1, name: '用户名密码登录', description: '验证登录接口成功路径。', method: 'POST', endpoint: '/api/v1/auth/login', module: '认证中心', source: 'manual', enabled: true, caseData: demoCaseData, request: JSON.stringify(demoCaseData, null, 2), updatedAt: '2026-08-10 09:42' },
  { id: 2, projectId: 1, project: '会员增长', moduleId: 1, name: '账号锁定后禁止登录', description: '验证锁定账号的异常响应。', method: 'POST', endpoint: '/api/v1/auth/login', module: '认证中心', source: 'manual', enabled: true, caseData: demoCaseData, request: JSON.stringify(demoCaseData, null, 2), updatedAt: '2026-08-10 09:42' },
]
