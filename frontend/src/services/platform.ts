import { isAxiosError } from 'axios'
import { demoDashboard, demoExecutions, demoProjects, demoTestcases } from './mock'
import { http } from './http'
import type { AndroidAutomationOverview, AndroidFlowPreset, AndroidRunDetail, AuditItem, DashboardData, Environment, Execution, ExecutionDetail, ExecutionReport, ExecutionRunOptions, Module, Project, Scenario, ScenarioExecution, ScenarioStep, SecurityMember, SecurityOptions, SecurityRole, SecurityUser, SessionInfo, TestCase, UiAutomationEnvironment, UiAutomationOverview, UiAutomationReplay, Variable } from '../types'

type ApiEnvelope<T> = { success: boolean; message: string; data: T }
const allowDemoFallback = import.meta.env.VITE_USE_DEMO_DATA === 'true'

async function apiGet<T>(url: string): Promise<T> {
  const response = await http.get<ApiEnvelope<T>, ApiEnvelope<T>>(url)
  if (!response.success) throw new Error(response.message)
  return response.data
}

async function apiPost<T>(url: string, payload: unknown): Promise<T> {
  const response = await http.post<ApiEnvelope<T>, ApiEnvelope<T>>(url, payload)
  if (!response.success) throw new Error(response.message)
  return response.data
}

async function apiPut<T>(url: string, payload: unknown): Promise<T> {
  const response = await http.put<ApiEnvelope<T>, ApiEnvelope<T>>(url, payload)
  if (!response.success) throw new Error(response.message)
  return response.data
}

async function apiPatch<T>(url: string, payload: unknown): Promise<T> {
  const response = await http.patch<ApiEnvelope<T>, ApiEnvelope<T>>(url, payload)
  if (!response.success) throw new Error(response.message)
  return response.data
}

async function apiDelete<T>(url: string): Promise<T> {
  const response = await http.delete<ApiEnvelope<T>, ApiEnvelope<T>>(url)
  if (!response.success) throw new Error(response.message)
  return response.data
}

async function requestWithDemo<T>(request: () => Promise<T>, fallback: T): Promise<T> {
  try { return await request() } catch (error) {
    if (allowDemoFallback && isAxiosError(error)) return fallback
    throw error
  }
}

export const platformApi = {
  login: (payload: { username: string; password: string }) => apiPost<SessionInfo>('/session/login', payload),
  session: () => apiGet<SessionInfo>('/session'),
  setActiveProject: (projectId: number | null) => apiPut<{ activeProjectId: number | null }>('/context/project', { projectId }),
  logout: () => apiPost('/session/logout', {}),
  dashboard: () => requestWithDemo(() => apiGet<DashboardData>('/dashboard'), demoDashboard),
  projects: () => requestWithDemo(() => apiGet<Project[]>('/projects'), demoProjects),
  createProject: (payload: Pick<Project, 'name' | 'description' | 'status'>) => apiPost<Project>('/projects', payload),
  updateProject: (projectId: number, payload: Pick<Project, 'name' | 'description' | 'status'>) => apiPatch<Project>(`/projects/${projectId}`, payload),
  deleteProject: (projectId: number) => apiDelete(`/projects/${projectId}`),
  modules: () => apiGet<Module[]>('/modules'),
  createModule: (payload: Pick<Module, 'projectId' | 'name' | 'description'>) => apiPost<Module>('/modules', payload),
  updateModule: (moduleId: number, payload: Pick<Module, 'name' | 'description'>) => apiPatch<Module>(`/modules/${moduleId}`, payload),
  deleteModule: (moduleId: number) => apiDelete(`/modules/${moduleId}`),
  environments: () => apiGet<Environment[]>('/environments'),
  createEnvironment: (payload: Omit<Environment, 'id' | 'project' | 'updatedAt'>) => apiPost<Environment>('/environments', payload),
  updateEnvironment: (environmentId: number, payload: Omit<Environment, 'id' | 'projectId' | 'project' | 'updatedAt'>) => apiPatch<Environment>(`/environments/${environmentId}`, payload),
  deleteEnvironment: (environmentId: number) => apiDelete(`/environments/${environmentId}`),
  variables: () => apiGet<Variable[]>('/variables'),
  createVariable: (payload: Omit<Variable, 'id' | 'project' | 'environment' | 'updatedAt'>) => apiPost<Variable>('/variables', payload),
  updateVariable: (variableId: number, payload: Omit<Variable, 'id' | 'projectId' | 'project' | 'environment' | 'updatedAt'>) => apiPatch<Variable>(`/variables/${variableId}`, payload),
  deleteVariable: (variableId: number) => apiDelete(`/variables/${variableId}`),
  scenarios: () => apiGet<Scenario[]>('/scenarios'),
  scenario: (scenarioId: number) => apiGet<Scenario>(`/scenarios/${scenarioId}`),
  createScenario: (payload: Omit<Scenario, 'id' | 'project' | 'module' | 'stepCount' | 'updatedAt' | 'steps'>) => apiPost<Scenario>('/scenarios', payload),
  updateScenario: (scenarioId: number, payload: Omit<Scenario, 'id' | 'projectId' | 'project' | 'module' | 'stepCount' | 'updatedAt' | 'steps'>) => apiPatch<Scenario>(`/scenarios/${scenarioId}`, payload),
  deleteScenario: (scenarioId: number) => apiDelete(`/scenarios/${scenarioId}`),
  createScenarioStep: (scenarioId: number, payload: Omit<ScenarioStep, 'id' | 'scenarioId' | 'testcaseName' | 'orderNo'>) => apiPost<ScenarioStep>(`/scenarios/${scenarioId}/steps`, payload),
  updateScenarioStep: (stepId: number, payload: Omit<ScenarioStep, 'id' | 'scenarioId' | 'testcaseName' | 'orderNo'>) => apiPatch<ScenarioStep>(`/scenario-steps/${stepId}`, payload),
  deleteScenarioStep: (stepId: number) => apiDelete(`/scenario-steps/${stepId}`),
  moveScenarioStep: (stepId: number, direction: 'up' | 'down') => apiPost<Scenario>(`/scenario-steps/${stepId}/move`, { direction }),
  scenarioExecutions: () => apiGet<ScenarioExecution[]>('/scenario-executions'),
  scenarioExecution: (executionId: number) => apiGet<ScenarioExecution>(`/scenario-executions/${executionId}`),
  runScenario: (payload: { scenarioId: number; environmentId: number; persistExtracted: boolean; runtimeInjections: Record<string, unknown> }) => apiPost<ScenarioExecution>('/scenario-runs', payload),
  securityOptions: () => apiGet<SecurityOptions>('/security/options'), securityUsers: () => apiGet<SecurityUser[]>('/security/users'), securityRoles: () => apiGet<SecurityRole[]>('/security/roles'), securityMembers: (projectId?: number) => apiGet<SecurityMember[]>(`/security/project-members${projectId ? `?project_id=${projectId}` : ''}`), securityAudit: (page = 1, projectId?: number) => apiGet<{ items: AuditItem[]; page: number; pages: number; total: number }>(`/security/audit?page=${page}${projectId ? `&project_id=${projectId}` : ''}`),
  createSecurityUser: (payload: { username: string; displayName: string; email: string; password: string; isActive: boolean; isSuperuser: boolean; roleCodes: string[] }) => apiPost<SecurityUser>('/security/users', payload), updateSecurityUser: (id: number, payload: { username: string; displayName: string; email: string; password: string; isActive: boolean; isSuperuser: boolean; roleCodes: string[] }) => apiPatch<SecurityUser>(`/security/users/${id}`, payload), deleteSecurityUser: (id: number) => apiDelete(`/security/users/${id}`),
  uiAutomationOverview: () => apiGet<UiAutomationOverview>('/ui-automation/overview'),
  androidAutomationOverview: () => apiGet<AndroidAutomationOverview>('/android-automation/overview'), androidExceptions: () => apiGet<Array<Record<string, unknown>>>('/android-automation/exceptions'), androidFlowPresets: () => apiGet<AndroidFlowPreset[]>('/android-automation/flow-presets'), startAndroidWorker: () => apiPost('/android-automation/worker/start', {}), updateAndroidDevice: (serial:string, payload:Record<string,unknown>) => apiPatch(`/android-automation/devices/${encodeURIComponent(serial)}`, payload), batchAndroidDevices: (payload:Record<string,unknown>) => apiPost('/android-automation/devices/batch', payload), createAndroidFlow: (payload: Record<string, unknown>) => apiPost('/android-automation/flows', payload), updateAndroidFlow: (id: number, payload: Record<string, unknown>) => apiPatch(`/android-automation/flows/${id}`, payload), deleteAndroidFlow: (id: number) => apiDelete(`/android-automation/flows/${id}`), applyAndroidFlowPreset: (flowId:number, presetKey:string, replaceExisting=true) => apiPost(`/android-automation/flows/${flowId}/presets/${encodeURIComponent(presetKey)}`, { replaceExisting }), createAndroidFlowStep: (flowId: number, payload: Record<string, unknown>) => apiPost(`/android-automation/flows/${flowId}/steps`, payload), updateAndroidFlowStep: (id: number, payload: Record<string, unknown>) => apiPatch(`/android-automation/flow-steps/${id}`, payload), deleteAndroidFlowStep: (id: number) => apiDelete(`/android-automation/flow-steps/${id}`), createAndroidTask: (payload: Record<string, unknown>) => apiPost('/android-automation/tasks', payload), updateAndroidTask: (id: number, payload: Record<string, unknown>) => apiPatch(`/android-automation/tasks/${id}`, payload), deleteAndroidTask: (id: number) => apiDelete(`/android-automation/tasks/${id}`), queueAndroidRun: (taskId: number) => apiPost(`/android-automation/tasks/${taskId}/runs`, {}), retryAndroidRun: (runId: number) => apiPost(`/android-automation/runs/${runId}/retry`, {}), androidRunDetail: (runId:number) => apiGet<AndroidRunDetail>(`/android-automation/runs/${runId}/detail`), stopAndroidRun: (runId:number) => apiPost(`/android-automation/runs/${runId}/stop`, {}), retryAndroidExceptions: (runIds:number[]) => apiPost<{created:unknown[];errors:unknown[]}>('/android-automation/exceptions/retry-batch', { runIds }),
  createUiScript: (payload: Record<string, unknown>) => apiPost('/ui-automation/scripts', payload), updateUiScript: (id: number, payload: Record<string, unknown>) => apiPatch(`/ui-automation/scripts/${id}`, payload), deleteUiScript: (id: number) => apiDelete(`/ui-automation/scripts/${id}`), uiScriptVersions: (id:number) => apiGet<Array<{id:number;version:number;summary:string;content:string;createdAt:string|null}>>(`/ui-automation/scripts/${id}/versions`), compareUiScriptVersions: (id:number, from:number, to:number) => apiGet<{from:Record<string,unknown>;to:Record<string,unknown>;diff:string}>(`/ui-automation/scripts/${id}/versions/compare?from=${from}&to=${to}`), restoreUiScriptVersion: (id:number, versionId:number) => apiPost(`/ui-automation/scripts/${id}/versions/${versionId}/restore`, { changeSummary: 'SPA restore' }), uiScriptDetail: (id:number) => apiGet<Record<string, unknown>>(`/ui-automation/scripts/${id}/detail`), importUiScripts: (payload:Record<string,unknown>) => apiPost<{created:unknown[];errors:unknown[]}>('/ui-automation/scripts/import', payload), exportUiScripts: () => apiGet<{items:unknown[]}>('/ui-automation/scripts/export'), queueUiRun: (payload: Record<string, unknown>) => apiPost('/ui-automation/runs', payload), uiReplay: (runId:number) => apiGet<UiAutomationReplay>(`/ui-automation/runs/${runId}/replay`), uiAutomationEnvironments: () => apiGet<UiAutomationEnvironment[]>('/ui-automation/environments'), createUiAutomationEnvironment: (payload:Record<string,unknown>) => apiPost<UiAutomationEnvironment>('/ui-automation/environments', payload), updateUiAutomationEnvironment: (id:number,payload:Record<string,unknown>) => apiPatch<UiAutomationEnvironment>(`/ui-automation/environments/${id}`, payload), deleteUiAutomationEnvironment: (id:number) => apiDelete(`/ui-automation/environments/${id}`), createUiLocator: (payload: Record<string, unknown>) => apiPost('/ui-automation/locators', payload), updateUiLocator: (id: number, payload: Record<string, unknown>) => apiPatch(`/ui-automation/locators/${id}`, payload), deleteUiLocator: (id: number) => apiDelete(`/ui-automation/locators/${id}`), importUiLocators: (payload:Record<string,unknown>) => apiPost<Record<string,unknown>>('/ui-automation/locators/import', payload), exportUiLocators: () => apiGet<{items:unknown[]}>('/ui-automation/locators/export'), batchUiLocators: (payload:Record<string,unknown>) => apiPost<Record<string,unknown>>('/ui-automation/locators/batch', payload),
  createSecurityRole: (payload: Omit<SecurityRole, 'id' | 'updatedAt'>) => apiPost<SecurityRole>('/security/roles', payload), updateSecurityRole: (id: number, payload: Omit<SecurityRole, 'id' | 'updatedAt'>) => apiPatch<SecurityRole>(`/security/roles/${id}`, payload), deleteSecurityRole: (id: number) => apiDelete(`/security/roles/${id}`), saveSecurityMember: (payload: { projectId: number; userId: number; accessLevel: string; remark: string }) => apiPost<SecurityMember>('/security/project-members', payload), deleteSecurityMember: (projectId: number, userId: number) => apiDelete(`/security/project-members/${projectId}/${userId}`),
  executions: () => requestWithDemo(() => apiGet<Execution[]>('/executions'), demoExecutions),
  executionOptions: () => apiGet<ExecutionRunOptions>('/execution-options'),
  executionDetail: (executionId: number) => apiGet<ExecutionDetail>(`/executions/${executionId}/detail`),
  executionReport: (executionId: number) => apiGet<ExecutionReport>(`/executions/${executionId}/report`),
  runExecution: (payload: { mode: 'testcase' | 'module' | 'selection' | 'project'; environmentId: number; testcaseId?: number; moduleId?: number; testcaseIds?: number[]; projectId?: number }) => apiPost<Execution>('/execution-runs', payload),
  testcases: () => requestWithDemo(() => apiGet<TestCase[]>('/testcases'), demoTestcases),
  createTestcase: (payload: Omit<TestCase, 'id' | 'project' | 'module' | 'method' | 'endpoint' | 'request' | 'updatedAt'>) => apiPost<TestCase>('/testcases', payload),
  updateTestcase: (testcaseId: number, payload: Pick<TestCase, 'moduleId' | 'name' | 'description' | 'source' | 'enabled' | 'caseData'>) => apiPatch<TestCase>(`/testcases/${testcaseId}`, payload),
  deleteTestcase: (testcaseId: number) => apiDelete(`/testcases/${testcaseId}`),
}
