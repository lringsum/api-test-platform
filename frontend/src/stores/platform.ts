import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { platformApi } from '../services/platform'
import type { DashboardData, Environment, Execution, Module, Project, Scenario, ScenarioExecution, SessionInfo, TestCase, Variable } from '../types'

export const usePlatformStore = defineStore('platform', () => {
  const dashboard = ref<DashboardData | null>(null)
  const projects = ref<Project[]>([])
  const executions = ref<Execution[]>([])
  const testcases = ref<TestCase[]>([])
  const modules = ref<Module[]>([])
  const environments = ref<Environment[]>([])
  const variables = ref<Variable[]>([])
  const scenarios = ref<Scenario[]>([])
  const scenarioExecutions = ref<ScenarioExecution[]>([])
  const session = ref<SessionInfo | null>(null)
  const loading = ref(false)
  const activeProjectId = ref<number | undefined>()
  const activeProject = computed(() => projects.value.find((project) => project.id === activeProjectId.value))

  async function loadOverview() {
    loading.value = true
    try {
      const [sessionResult, dashboardResult, projectsResult, executionsResult] = await Promise.all([platformApi.session(), platformApi.dashboard(), platformApi.projects(), platformApi.executions()])
      session.value = sessionResult
      activeProjectId.value = sessionResult.activeProjectId ?? undefined
      dashboard.value = dashboardResult
      projects.value = projectsResult
      executions.value = executionsResult
    } finally { loading.value = false }
  }
  async function loadTestcases() { testcases.value = await platformApi.testcases() }
  async function loadModules() { modules.value = await platformApi.modules() }
  async function loadEnvironments() { environments.value = await platformApi.environments() }
  async function loadVariables() { variables.value = await platformApi.variables() }
  async function loadScenarios() { scenarios.value = await platformApi.scenarios() }
  async function loadScenarioExecutions() { scenarioExecutions.value = await platformApi.scenarioExecutions() }
  async function addProject(project: Pick<Project, 'name' | 'description' | 'status'>) {
    const created = await platformApi.createProject(project)
    projects.value.unshift(created)
  }
  async function updateProject(projectId: number, payload: Pick<Project, 'name' | 'description' | 'status'>) {
    const updated = await platformApi.updateProject(projectId, payload)
    const index = projects.value.findIndex((project) => project.id === projectId)
    if (index >= 0) projects.value.splice(index, 1, updated)
  }
  async function removeProject(projectId: number) {
    await platformApi.deleteProject(projectId)
    projects.value = projects.value.filter((project) => project.id !== projectId)
  }
  async function addModule(payload: Pick<Module, 'projectId' | 'name' | 'description'>) {
    modules.value.unshift(await platformApi.createModule(payload))
  }
  async function updateModule(moduleId: number, payload: Pick<Module, 'name' | 'description'>) {
    const updated = await platformApi.updateModule(moduleId, payload)
    const index = modules.value.findIndex((module) => module.id === moduleId)
    if (index >= 0) modules.value.splice(index, 1, updated)
  }
  async function removeModule(moduleId: number) {
    await platformApi.deleteModule(moduleId)
    modules.value = modules.value.filter((module) => module.id !== moduleId)
  }
  async function addEnvironment(payload: Omit<Environment, 'id' | 'project' | 'updatedAt'>) { environments.value.unshift(await platformApi.createEnvironment(payload)) }
  async function updateEnvironment(environmentId: number, payload: Omit<Environment, 'id' | 'projectId' | 'project' | 'updatedAt'>) {
    const updated = await platformApi.updateEnvironment(environmentId, payload)
    const index = environments.value.findIndex((environment) => environment.id === environmentId)
    if (index >= 0) environments.value.splice(index, 1, updated)
  }
  async function removeEnvironment(environmentId: number) { await platformApi.deleteEnvironment(environmentId); environments.value = environments.value.filter((environment) => environment.id !== environmentId) }
  async function addVariable(payload: Omit<Variable, 'id' | 'project' | 'environment' | 'updatedAt'>) { variables.value.unshift(await platformApi.createVariable(payload)) }
  async function updateVariable(variableId: number, payload: Omit<Variable, 'id' | 'projectId' | 'project' | 'environment' | 'updatedAt'>) {
    const updated = await platformApi.updateVariable(variableId, payload)
    const index = variables.value.findIndex((variable) => variable.id === variableId)
    if (index >= 0) variables.value.splice(index, 1, updated)
  }
  async function removeVariable(variableId: number) { await platformApi.deleteVariable(variableId); variables.value = variables.value.filter((variable) => variable.id !== variableId) }
  async function addScenario(payload: Omit<Scenario, 'id' | 'project' | 'module' | 'stepCount' | 'updatedAt' | 'steps'>) { scenarios.value.unshift(await platformApi.createScenario(payload)) }
  async function updateScenario(scenarioId: number, payload: Omit<Scenario, 'id' | 'projectId' | 'project' | 'module' | 'stepCount' | 'updatedAt' | 'steps'>) {
    const updated = await platformApi.updateScenario(scenarioId, payload)
    const index = scenarios.value.findIndex((scenario) => scenario.id === scenarioId)
    if (index >= 0) scenarios.value.splice(index, 1, updated)
    return updated
  }
  async function removeScenario(scenarioId: number) { await platformApi.deleteScenario(scenarioId); scenarios.value = scenarios.value.filter((scenario) => scenario.id !== scenarioId) }
  async function runScenario(payload: { scenarioId: number; environmentId: number; persistExtracted: boolean; runtimeInjections: Record<string, unknown> }) { const execution = await platformApi.runScenario(payload); scenarioExecutions.value.unshift(execution); return execution }
  async function addTestcase(payload: Omit<TestCase, 'id' | 'project' | 'module' | 'method' | 'endpoint' | 'request' | 'updatedAt'>) {
    testcases.value.unshift(await platformApi.createTestcase(payload))
  }
  async function updateTestcase(testcaseId: number, payload: Pick<TestCase, 'moduleId' | 'name' | 'description' | 'source' | 'enabled' | 'caseData'>) {
    const updated = await platformApi.updateTestcase(testcaseId, payload)
    const index = testcases.value.findIndex((testcase) => testcase.id === testcaseId)
    if (index >= 0) testcases.value.splice(index, 1, updated)
  }
  async function removeTestcase(testcaseId: number) {
    await platformApi.deleteTestcase(testcaseId)
    testcases.value = testcases.value.filter((testcase) => testcase.id !== testcaseId)
  }
  async function runExecution(payload: { mode: 'testcase' | 'module' | 'selection' | 'project'; environmentId: number; testcaseId?: number; moduleId?: number; testcaseIds?: number[]; projectId?: number }) {
    const execution = await platformApi.runExecution(payload)
    executions.value.unshift(execution)
    return execution
  }
  async function selectProject(projectId: number | null) {
    const result = await platformApi.setActiveProject(projectId)
    activeProjectId.value = result.activeProjectId ?? undefined
    await loadOverview()
  }
  return { dashboard, projects, modules, environments, variables, scenarios, scenarioExecutions, executions, testcases, session, loading, activeProjectId, activeProject, loadOverview, loadTestcases, loadModules, loadEnvironments, loadVariables, loadScenarios, loadScenarioExecutions, addProject, updateProject, removeProject, addModule, updateModule, removeModule, addEnvironment, updateEnvironment, removeEnvironment, addVariable, updateVariable, removeVariable, addScenario, updateScenario, removeScenario, addTestcase, updateTestcase, removeTestcase, runScenario, runExecution, selectProject }
})
