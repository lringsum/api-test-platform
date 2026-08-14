export type RunStatus = 'passed' | 'failed' | 'running'

export interface Project {
  id: number
  name: string
  status: 'active' | 'inactive'
  modules: number
  environments: number
  updatedAt: string
  description: string
}

export interface Module {
  id: number
  projectId: number
  project: string
  name: string
  description: string
  testcaseCount: number
  scenarioCount: number
  updatedAt: string | null
}

export interface Environment {
  id: number
  projectId: number
  project: string
  name: string
  baseUrl: string
  description: string
  isActive: boolean
  headers: Record<string, string>
  variables: Record<string, string>
  updatedAt: string | null
}

export interface Variable {
  id: number
  projectId: number
  project: string
  environmentId: number | null
  environment: string | null
  name: string
  value: string
  scope: 'project' | 'environment'
  description: string
  updatedAt: string | null
}

export interface Execution {
  id: number
  name: string
  project: string
  executionType: '接口测试' | 'UI 自动化'
  status: RunStatus
  duration: number
  startedAt: string
  passRate: number
  total: number
  passed: number
  failed: number
}

export interface ExecutionDetail extends Execution {
  environment: string | null
  summary: Record<string, unknown>
  details: Array<{ id: number; testcaseId: number | null; testcaseName: string; status: RunStatus; durationMs: number; request: Record<string, unknown>; response: Record<string, unknown>; assertions: Array<Record<string, unknown>>; extracts: Record<string, unknown>; errorMessage: string }>
}

export interface ExecutionRunOptions {
  environments: Array<{ id: number; name: string; baseUrl: string }>
  modules: Array<{ id: number; name: string }>
  testcases: Array<{ id: number; name: string; moduleId: number; module: string; method: string; endpoint: string }>
}

export interface ExecutionReport {
  id: number
  title: string
  executionId: number
  data: { status: RunStatus; total_count: number; passed_count: number; failed_count: number; pass_rate: number; total_duration_ms: number; failed_cases: string[]; failure_details: Array<{ testcase_name: string; error_message: string; failed_assertions: Array<Record<string, unknown>> }>; details: Array<{ testcase_name: string; status: RunStatus; duration_ms: number }> }
}

export interface ScenarioStep {
  id: number
  scenarioId: number
  testcaseId: number | null
  testcaseName: string
  orderNo: number
  name: string
  isEnabled: boolean
  continueOnFailure: boolean
  setupVariables: Record<string, unknown>
  requestOverrides: Record<string, unknown>
  extractOverrides: Record<string, unknown>
  assertionOverrides: Array<Record<string, unknown>>
}

export interface Scenario {
  id: number
  projectId: number
  project: string
  moduleId: number | null
  module: string | null
  name: string
  description: string
  status: 'active' | 'inactive'
  tags: string[]
  stepCount: number
  updatedAt: string | null
  steps?: ScenarioStep[]
}

export interface ScenarioExecution {
  id: number
  scenarioId: number
  scenario: string
  projectId: number | null
  project: string
  environment: string | null
  status: RunStatus
  totalSteps: number
  passedSteps: number
  failedSteps: number
  durationMs: number
  startedAt: string | null
  runtimeVariables: Record<string, unknown>
  details?: Array<{ id: number; stepName: string; testcaseName: string; status: RunStatus; durationMs: number; request: Record<string, unknown>; response: Record<string, unknown>; extracts: Record<string, unknown>; assertions: Array<Record<string, unknown>>; errorMessage: string }>
}

export interface DashboardData {
  stats: { label: string; value: number; hint: string; tone: string }[]
  executions: Execution[]
  trend: { dates: string[]; passed: number[]; failed: number[] }
}

export interface SessionInfo {
  user: { id: number; username: string; displayName: string; isSuperuser: boolean }
  permissions: string[]
  projects: Project[]
  activeProjectId: number | null
}

export interface TestCase {
  id: number
  projectId: number
  project: string
  moduleId: number
  name: string
  description: string
  method: 'GET' | 'POST' | 'PUT' | 'DELETE'
  endpoint: string
  module: string
  source: 'manual'
  enabled: boolean
  caseData: Record<string, unknown>
  request: string
  updatedAt: string | null
}

export interface SecurityRole { id: number; code: string; name: string; description: string; isSystem: boolean; sortOrder: number; permissionCodes: string[]; updatedAt: string | null }
export interface SecurityPermission { id: number; code: string; name: string; category: string; groupName: string; description: string; sortOrder: number }
export interface SecurityUser { id: number; username: string; displayName: string; email: string; isActive: boolean; isSuperuser: boolean; roles: Array<{ code: string; name: string }>; lastLoginAt: string | null; updatedAt: string | null }
export interface SecurityMember { id: number; projectId: number; project: string; userId: number; username: string; displayName: string; accessLevel: string; remark: string; updatedAt: string | null }
export interface AuditItem { id: number; username: string; action: string; resourceType: string; resourceId: number | null; projectId: number | null; ipAddress: string; detail: Record<string, unknown>; createdAt: string | null }
export interface SecurityOptions { roles: SecurityRole[]; permissions: SecurityPermission[]; memberCandidates: Array<{ id: number; username: string; displayName: string }>; projects: Project[]; accessLevels: string[] }
export interface UiAutomationEnvironment { id:number; projectId:number; project:string; name:string; baseUrl:string; browserDefault:string; headlessDefault:boolean; timeoutMs:number; retryTimes:number; viewportWidth:number; viewportHeight:number; storageStatePath:string; proxyConfig:Record<string, unknown>; runtimeVariables:Record<string, unknown>; status:string; description:string; updatedAt:string|null }
export interface UiAutomationScript { id:number; projectId:number; project:string; name:string; code:string; description:string; status:string; tags:string[]; version:number; content:string; dependencies?:Array<{type:string;role:string;script_id:number;script_code:string}>; updatedAt:string|null; language?:string; framework?:string; entryFile?:string }
export interface UiAutomationLocator { id:number; projectId:number; project:string; pageName:string; code:string; name:string; type:string; value:string; status:string; stable:boolean; updatedAt:string|null }
export interface UiAutomationRun { id:number; projectId:number; project:string; scriptId:number; script:string; environment:string|null; status:string; browser:string; startedAt:string|null; durationMs:number; error:string }
export interface UiAutomationArtifact { id:number; type:string; fileName:string; fileSize:number; mimeType:string; createdAt:string|null; previewUrl:string; downloadUrl:string }
export interface UiAutomationFailureAnalysis { has_failure:boolean; category:string; category_label:string; summary:string; root_cause:string; suggestion:string; step_index:number|null; step_title:string; step_type:string; locator:string; match_count:number|null; error_message:string }
export interface UiAutomationReplay { run: UiAutomationRun & { summary:Record<string, unknown>; errorStage:string }; artifacts:UiAutomationArtifact[]; steps:Array<{ id:number; index:number; type:string; title:string; locator:string; status:string; durationMs:number; error:string; rawLog:Array<Record<string, unknown>>; screenshotUrl:string; failureAnalysis:UiAutomationFailureAnalysis|null }>; failureAnalysis:UiAutomationFailureAnalysis }
export interface UiAutomationOverview { scripts: UiAutomationScript[]; locators: UiAutomationLocator[]; environments: UiAutomationEnvironment[]; runs: UiAutomationRun[] }
export interface AndroidAutomationOverview { flows: Array<{ id:number; projectId:number; project:string; name:string; code:string; description:string; isDefault:boolean; status:string; steps:Array<{ id:number; stepNo:number; name:string; type:string; selectorType:string; selectorValue:string; inputValue:string; waitTimeoutSec:number; retryTimes:number; continueOnFailure:boolean; captureOnSuccess:boolean; captureOnFailure:boolean; remark:string }>; updatedAt:string|null }>; tasks: Array<{ id:number; projectId:number; project:string; name:string; packageKey:string; packageName:string; apkUrl:string; channelTag:string; deviceSerial:string; flowMode:string; flowId:number|null; isActive:boolean; remark:string; updatedAt:string|null }>; runs: Array<{ id:number; projectId:number; project:string; taskId:number; task:string; executionNo:string; status:string; stage:string; deviceSerial:string; deviceName:string; errorType:string; error:string; durationMs:number; startedAt:string|null; finishedAt:string|null }>; devices:Array<Record<string, unknown>>; worker:Record<string, unknown>; stepTypes:string[]; selectorTypes:string[] }
export interface AndroidFlowPreset { key:string; name:string; summary:string; stepCount:number }
export type AndroidRunDetail = AndroidAutomationOverview['runs'][number] & { packageName:string; launchableActivity:string; downloadStatus:string; aaptStatus:string; installStatus:string; launchStatus:string; crashStatus:string; currentFocus:string; pid:string; flowSnapshot:Record<string, unknown>; screenshotUrl:string; logUrl:string; steps:Array<{ id:number; stepNo:number; name:string; type:string; selectorType:string; selectorValue:string; status:string; error:string; durationMs:number; startedAt:string|null; finishedAt:string|null; screenshotUrl:string; artifacts:Array<{id:number;type:string;fileName:string;fileSize:number;previewUrl:string}> }> }
