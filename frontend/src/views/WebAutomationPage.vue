<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { DeleteOutlined, DownloadOutlined, EditOutlined, EyeOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, UploadOutlined } from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import { platformApi } from '../services/platform'
import { usePlatformStore } from '../stores/platform'
import type { Project, UiAutomationEnvironment, UiAutomationLocator, UiAutomationOverview, UiAutomationReplay, UiAutomationRun, UiAutomationScript } from '../types'

hljs.registerLanguage('python', python)
type TabKey = 'scripts' | 'environments' | 'locators' | 'runs'
type DrawerKind = 'script' | 'environment' | 'locator' | 'run'
type BatchKind = 'script' | 'locator'
const ALL_LOCATOR_PAGES = '__all_locator_pages__'
const UNCLASSIFIED_LOCATOR_PAGE = '__unclassified_locator_page__'
const platform = usePlatformStore()
const data = ref<UiAutomationOverview>({ scripts: [], locators: [], environments: [], runs: [] })
const projects = ref<Project[]>([])
const loading = ref(false)
const activeTab = ref<TabKey>('scripts')
const drawer = ref<DrawerKind | null>(null)
const detailOpen = ref(false)
const replayOpen = ref(false)
const replayDrawerOpen = ref(false)
const screenshotPreviewOpen = ref(false)
const screenshotPreviewUrl = ref('')
const versionsOpen = ref(false)
const batchOpen = ref(false)
const batchKind = ref<BatchKind>('script')
const selectedLocatorIds = ref<number[]>([])
const selectedLocatorPage = ref(ALL_LOCATOR_PAGES)
const locatorKeyword = ref('')
const locatorCurrentPage = ref(1)
const detail = ref<Record<string, any> | null>(null)
const replay = ref<UiAutomationReplay | null>(null)
const replayRefreshing = ref(false)
let replayPollTimer: ReturnType<typeof setTimeout> | null = null
const activeRunStatuses = new Set(['queued', 'pending', 'running'])
const versions = ref<Array<{id:number;version:number;summary:string;content:string;createdAt:string|null}>>([])
const versionScript = ref<UiAutomationScript | null>(null)
const versionDiff = ref('')
const batchText = ref('[]')
const scriptForm = ref({ id: 0, projectId: 0, name: '', code: '', description: '', content: '', status: 'draft', tags: '', entryFile: 'tests/test_ui.py', needLogin: true })
const environmentForm = ref({ id: 0, projectId: 0, name: '', baseUrl: '', browserDefault: 'chromium', headlessDefault: true, timeoutMs: 30000, retryTimes: 0, viewportWidth: 1440, viewportHeight: 900, storageStatePath: '', proxyConfigText: '{}', runtimeVariablesText: '{}', status: 'active', description: '' })
const locatorForm = ref({ id: 0, projectId: 0, name: '', code: '', type: 'css', value: '', pageName: '', pageUrlPattern: '', description: '', usageScene: '', status: 'active', stable: true })
const runForm = ref({ projectId: 0, scriptId: 0, environmentId: undefined as number | undefined, browser: 'chromium' })

const projectOptions = computed(() => projects.value.map((item) => ({ label: item.name, value: item.id })))
const runEnvironments = computed(() => data.value.environments.filter((item) => item.projectId === runForm.value.projectId))
const drawerTitle = computed(() => ({ script: scriptForm.value.id ? '编辑脚本' : '新建脚本', environment: environmentForm.value.id ? '编辑运行环境' : '新建运行环境', locator: locatorForm.value.id ? '编辑定位器' : '新建定位器', run: '配置运行' }[drawer.value ?? 'script']))
const highlightedDetailCode = computed(() => detail.value?.script?.content ? hljs.highlight(detail.value.script.content, { language: 'python' }).value : '')
const highlightedDiff = computed(() => versionDiff.value ? hljs.highlight(versionDiff.value, { language: 'python' }).value : '')
const locatorPageGroups = computed(() => {
  const groups = new Map<string, { key: string; label: string; count: number }>()
  data.value.locators.forEach((locator) => {
    const label = locator.pageName?.trim() || '未分类'
    const key = locator.pageName?.trim() || UNCLASSIFIED_LOCATOR_PAGE
    const current = groups.get(key)
    groups.set(key, { key, label, count: (current?.count || 0) + 1 })
  })
  const pageGroups = [...groups.values()].sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, 'zh-CN'))
  return [{ key: ALL_LOCATOR_PAGES, label: '全部', count: data.value.locators.length }, ...pageGroups]
})
const locatorPageOptions = computed(() => locatorPageGroups.value
  .filter((group) => group.key !== ALL_LOCATOR_PAGES && group.key !== UNCLASSIFIED_LOCATOR_PAGE)
  .map((group) => ({ label: `${group.label}（${group.count}）`, value: group.label })))
const filteredLocators = computed(() => {
  const keyword = locatorKeyword.value.trim().toLocaleLowerCase()
  return data.value.locators.filter((locator) => {
    const pageKey = locator.pageName?.trim() || UNCLASSIFIED_LOCATOR_PAGE
    if (selectedLocatorPage.value !== ALL_LOCATOR_PAGES && pageKey !== selectedLocatorPage.value) return false
    if (!keyword) return true
    return [locator.name, locator.code, locator.value, locator.pageName, locator.project]
      .some((value) => String(value || '').toLocaleLowerCase().includes(keyword))
  })
})

async function load() {
  loading.value = true
  try {
    const [overview, projectList] = await Promise.all([platformApi.uiAutomationOverview(), platformApi.projects()])
    data.value = overview; projects.value = projectList
    if (!locatorPageGroups.value.some((group) => group.key === selectedLocatorPage.value)) selectedLocatorPage.value = ALL_LOCATOR_PAGES
    clearLocatorSelection()
  } catch { message.error('Web 自动化数据加载失败') } finally { loading.value = false }
}
function defaultProjectId() { return platform.activeProjectId || projects.value[0]?.id || data.value.scripts[0]?.projectId || 0 }
function clearLocatorSelection() { selectedLocatorIds.value = []; locatorCurrentPage.value = 1 }
function selectLocatorPage(pageKey: string) { selectedLocatorPage.value = pageKey; clearLocatorSelection() }
function displayLocatorPage(locator: UiAutomationLocator) { return locator.pageName?.trim() || '未分类' }
function showLocatorTotal(total: number) { return `共 ${total} 条` }
function handleLocatorTableChange(pagination: { current?: number }) { locatorCurrentPage.value = pagination.current || 1 }
function parseJson(value: string, label: string) { try { const parsed = JSON.parse(value || '{}'); if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error(); return parsed } catch { throw new Error(`${label}必须是 JSON 对象`) } }
function openScript(item?: UiAutomationScript) { scriptForm.value = item ? { id: item.id, projectId: item.projectId, name: item.name, code: item.code, description: item.description, content: item.content, status: item.status, tags: item.tags.join(', '), entryFile: item.entryFile || 'tests/test_ui.py', needLogin: Boolean(item.dependencies?.some((dependency) => dependency.role === 'login_precondition')) } : { id: 0, projectId: defaultProjectId(), name: '', code: '', description: '', content: '', status: 'draft', tags: '', entryFile: 'tests/test_ui.py', needLogin: true }; drawer.value = 'script' }
function openEnvironment(item?: UiAutomationEnvironment) { environmentForm.value = item ? { id: item.id, projectId: item.projectId, name: item.name, baseUrl: item.baseUrl, browserDefault: item.browserDefault, headlessDefault: item.headlessDefault, timeoutMs: item.timeoutMs, retryTimes: item.retryTimes, viewportWidth: item.viewportWidth, viewportHeight: item.viewportHeight, storageStatePath: item.storageStatePath, proxyConfigText: JSON.stringify(item.proxyConfig, null, 2), runtimeVariablesText: JSON.stringify(item.runtimeVariables, null, 2), status: item.status, description: item.description } : { id: 0, projectId: defaultProjectId(), name: '', baseUrl: '', browserDefault: 'chromium', headlessDefault: true, timeoutMs: 30000, retryTimes: 0, viewportWidth: 1440, viewportHeight: 900, storageStatePath: '', proxyConfigText: '{}', runtimeVariablesText: '{}', status: 'active', description: '' }; drawer.value = 'environment' }
function openLocator(item?: UiAutomationLocator) { const activePageName = selectedLocatorPage.value !== ALL_LOCATOR_PAGES && selectedLocatorPage.value !== UNCLASSIFIED_LOCATOR_PAGE ? selectedLocatorPage.value : ''; locatorForm.value = item ? { id: item.id, projectId: item.projectId, name: item.name, code: item.code, type: item.type, value: item.value, pageName: item.pageName, pageUrlPattern: '', description: '', usageScene: '', status: item.status, stable: item.stable } : { id: 0, projectId: defaultProjectId(), name: '', code: '', type: 'css', value: '', pageName: activePageName, pageUrlPattern: '', description: '', usageScene: '', status: 'active', stable: true }; drawer.value = 'locator' }
function openRun(item: UiAutomationScript) { runForm.value = { projectId: item.projectId, scriptId: item.id, environmentId: data.value.environments.find((env) => env.projectId === item.projectId)?.id, browser: 'chromium' }; drawer.value = 'run' }
async function saveScript() { try { const payload = { ...scriptForm.value, language: 'python', framework: 'playwright', tags: scriptForm.value.tags.split(',').map((item) => item.trim()).filter(Boolean), changeSummary: 'SPA edit' }; scriptForm.value.id ? await platformApi.updateUiScript(scriptForm.value.id, payload) : await platformApi.createUiScript(payload); drawer.value = null; await load(); message.success('脚本已保存') } catch { message.error('脚本保存失败') } }
async function saveEnvironment() { try { const payload = { ...environmentForm.value, proxyConfig: parseJson(environmentForm.value.proxyConfigText, '代理配置'), runtimeVariables: parseJson(environmentForm.value.runtimeVariablesText, '运行变量') }; environmentForm.value.id ? await platformApi.updateUiAutomationEnvironment(environmentForm.value.id, payload) : await platformApi.createUiAutomationEnvironment(payload); drawer.value = null; await load(); message.success('环境已保存') } catch (error) { message.error(error instanceof Error ? error.message : '环境保存失败') } }
async function saveLocator() { try { locatorForm.value.id ? await platformApi.updateUiLocator(locatorForm.value.id, locatorForm.value) : await platformApi.createUiLocator(locatorForm.value); drawer.value = null; await load(); message.success('定位器已保存') } catch { message.error('定位器保存失败') } }
async function queueRun() { try { await platformApi.queueUiRun({ ...runForm.value, runMode: 'manual' }); drawer.value = null; activeTab.value = 'runs'; await load(); message.success('已加入运行队列') } catch { message.error('入队失败，请确认脚本、环境和权限') } }
async function showDetail(item: UiAutomationScript) { try { detail.value = await platformApi.uiScriptDetail(item.id); detailOpen.value = true } catch { message.error('脚本详情加载失败') } }
function stopReplayPolling() {
  if (replayPollTimer) clearTimeout(replayPollTimer)
  replayPollTimer = null
}
function scheduleReplayPolling(runId: number) {
  stopReplayPolling()
  if (!replayDrawerOpen.value || document.hidden || !activeRunStatuses.has(replay.value?.run.status || '')) return
  replayPollTimer = setTimeout(() => void refreshReplay(runId), 1000)
}
async function refreshReplay(runId: number) {
  if (!replayDrawerOpen.value || replayRefreshing.value) return
  replayRefreshing.value = true
  try {
    replay.value = await platformApi.uiReplay(runId)
  } catch {
    replayPollTimer = setTimeout(() => void refreshReplay(runId), 3000)
    return
  } finally {
    replayRefreshing.value = false
  }
  scheduleReplayPolling(runId)
}
async function showReplay(item: UiAutomationRun) {
  try {
    replay.value = await platformApi.uiReplay(item.id)
    replayOpen.value = false
    replayDrawerOpen.value = true
    scheduleReplayPolling(item.id)
  } catch { message.error('回放数据加载失败') }
}
function handleVisibilityChange() {
  if (!document.hidden && replayDrawerOpen.value && replay.value) void refreshReplay(replay.value.run.id)
  else stopReplayPolling()
}
function openArtifactPreview(url: string) { screenshotPreviewUrl.value = url; screenshotPreviewOpen.value = true }
async function showVersions(item: UiAutomationScript) { try { versionScript.value = item; versions.value = await platformApi.uiScriptVersions(item.id); versionDiff.value = ''; versionsOpen.value = true } catch { message.error('版本历史加载失败') } }
async function compareVersions() { if (!versionScript.value || versions.value.length < 2) return; try { versionDiff.value = (await platformApi.compareUiScriptVersions(versionScript.value.id, versions.value[1].id, versions.value[0].id)).diff || '两个版本内容一致' } catch { message.error('版本比较失败') } }
async function restoreVersion(versionId: number) { if (!versionScript.value) return; try { await platformApi.restoreUiScriptVersion(versionScript.value.id, versionId); await showVersions(versionScript.value); await load(); message.success('已创建恢复版本') } catch { message.error('恢复失败') } }
function confirmDelete(kind: 'script' | 'environment' | 'locator', item: { id:number }) { Modal.confirm({ title: '确认删除？', content: '该操作不可恢复。', okType: 'danger', onOk: async () => { try { if (kind === 'script') await platformApi.deleteUiScript(item.id); if (kind === 'environment') await platformApi.deleteUiAutomationEnvironment(item.id); if (kind === 'locator') await platformApi.deleteUiLocator(item.id); await load(); message.success('已删除') } catch { message.error('删除失败') } } }) }
async function runLocatorBatch(action: string) { if (!selectedLocatorIds.value.length) return message.warning('请先选择定位器'); try { await platformApi.batchUiLocators({ ids: selectedLocatorIds.value, action }); selectedLocatorIds.value = []; await load(); message.success('批量操作完成') } catch { message.error('批量操作失败') } }
function downloadJson(name: string, value: unknown) { const href = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' })); const link = document.createElement('a'); link.href = href; link.download = name; link.click(); URL.revokeObjectURL(href) }
async function exportItems(kind: BatchKind) { try { const payload = kind === 'script' ? await platformApi.exportUiScripts() : await platformApi.exportUiLocators(); downloadJson(`ui-${kind}-${Date.now()}.json`, payload); message.success('导出已开始') } catch { message.error('导出失败') } }
function openBatch(kind: BatchKind) { batchKind.value = kind; batchText.value = '[]'; batchOpen.value = true }
async function importItems() { try { const parsed = JSON.parse(batchText.value); const items = Array.isArray(parsed) ? parsed : parsed.items; if (!Array.isArray(items) || !items.length) throw new Error('请输入非空 JSON 数组'); const projectId = defaultProjectId(); if (batchKind.value === 'script') await platformApi.importUiScripts({ projectId, items }); else await platformApi.importUiLocators({ projectId, items }); batchOpen.value = false; await load(); message.success('批量导入完成') } catch (error) { message.error(error instanceof Error ? error.message : '导入失败') } }
watch(replayDrawerOpen, (open) => {
  if (!open) stopReplayPolling()
  else if (replay.value) scheduleReplayPolling(replay.value.run.id)
})
watch(locatorKeyword, clearLocatorSelection)
watch(() => platform.activeProjectId, () => {
  selectedLocatorPage.value = ALL_LOCATOR_PAGES
  locatorKeyword.value = ''
  clearLocatorSelection()
  void load()
})
onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)
  void load()
})
onBeforeUnmount(() => {
  stopReplayPolling()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>

<template>
  <section class="qa-panel overflow-hidden"><a-tabs v-model:active-key="activeTab" class="automation-tabs px-5 pt-1">
    <a-tab-pane key="scripts" tab="脚本"><div class="automation-toolbar"><a-space wrap><a-button @click="openBatch('script')"><UploadOutlined />批量导入</a-button><a-button @click="exportItems('script')"><DownloadOutlined />导出</a-button></a-space><a-space wrap><a-button @click="load"><ReloadOutlined />刷新</a-button><a-button type="primary" @click="openScript"><PlusOutlined />新建脚本</a-button></a-space></div><a-table :data-source="data.scripts" :loading="loading" row-key="id"><a-table-column title="脚本" key="name"><template #default="{ record }"><b>{{ record.name }}</b><small class="ml-2 text-slate-400">{{ record.code }} · v{{ record.version }}</small><a-tag v-if="record.dependencies?.some((dependency:any)=>dependency.role==='login_precondition')" class="ml-2" color="blue">前置登录</a-tag></template></a-table-column><a-table-column title="项目" data-index="project"/><a-table-column title="状态" data-index="status"/><a-table-column title="操作"><template #default="{ record }"><a-space :size="0"><a-button type="link" @click="showDetail(record)"><EyeOutlined />详情</a-button><a-button type="link" @click="openScript(record)"><EditOutlined />编辑</a-button><a-button type="link" @click="showVersions(record)">版本</a-button><a-button type="link" @click="openRun(record)">运行</a-button><a-button type="link" danger @click="confirmDelete('script', record)"><DeleteOutlined /></a-button></a-space></template></a-table-column></a-table></a-tab-pane>
    <a-tab-pane key="environments" tab="运行环境"><div class="automation-toolbar justify-end"><a-button @click="load"><ReloadOutlined />刷新</a-button><a-button type="primary" @click="openEnvironment"><PlusOutlined />新建环境</a-button></div><a-table :data-source="data.environments" :loading="loading" row-key="id"><a-table-column title="环境" key="name"><template #default="{record}"><b>{{record.name}}</b><div class="text-xs text-slate-400">{{record.baseUrl}}</div></template></a-table-column><a-table-column title="默认浏览器" data-index="browserDefault"/><a-table-column title="超时" key="timeout"><template #default="{record}">{{record.timeoutMs}} ms</template></a-table-column><a-table-column title="状态" data-index="status"/><a-table-column title="操作"><template #default="{record}"><a-button type="link" @click="openEnvironment(record)">编辑</a-button><a-button type="link" danger @click="confirmDelete('environment',record)">删除</a-button></template></a-table-column></a-table></a-tab-pane>
    <a-tab-pane key="locators" tab="定位器">
      <div class="automation-toolbar justify-between">
        <a-space wrap><a-button @click="openBatch('locator')"><UploadOutlined />批量导入</a-button><a-button @click="exportItems('locator')"><DownloadOutlined />导出</a-button><a-dropdown><a-button>批量操作</a-button><template #overlay><a-menu><a-menu-item @click="runLocatorBatch('activate')">启用</a-menu-item><a-menu-item @click="runLocatorBatch('deprecate')">废弃</a-menu-item><a-menu-item @click="runLocatorBatch('stable')">设为稳定</a-menu-item><a-menu-item @click="runLocatorBatch('unstable')">设为不稳定</a-menu-item><a-menu-item danger @click="runLocatorBatch('delete')">删除</a-menu-item></a-menu></template></a-dropdown></a-space>
        <a-space wrap><a-button @click="load"><ReloadOutlined />刷新</a-button><a-button type="primary" @click="openLocator"><PlusOutlined />新建定位器</a-button></a-space>
      </div>
      <div class="locator-filter-panel">
        <div class="locator-filter-heading">
          <div><div class="text-sm font-semibold text-ink">页面功能</div><div class="mt-1 text-xs text-slate-400">点击功能名称，只查看该页面关联的定位器</div></div>
          <a-input v-model:value="locatorKeyword" allow-clear class="locator-search" placeholder="搜索名称、编码或定位值"><template #prefix><SearchOutlined class="text-slate-400" /></template></a-input>
        </div>
        <div class="locator-page-groups" role="list" aria-label="定位器页面功能筛选">
          <button v-for="group in locatorPageGroups" :key="group.key" type="button" class="locator-page-chip" :class="{ 'locator-page-chip-active': selectedLocatorPage === group.key }" :aria-pressed="selectedLocatorPage === group.key" @click="selectLocatorPage(group.key)">
            <span>{{ group.label }}</span><span class="locator-page-count">{{ group.count }}</span>
          </button>
        </div>
        <div class="locator-filter-summary">当前显示 {{ filteredLocators.length }} / {{ data.locators.length }} 条<span v-if="selectedLocatorIds.length">，已选 {{ selectedLocatorIds.length }} 条</span></div>
      </div>
      <a-table :data-source="filteredLocators" :loading="loading" row-key="id" :scroll="{ x: 1080 }" :pagination="{ current: locatorCurrentPage, pageSize: 10, showSizeChanger: false, showTotal: showLocatorTotal }" :row-selection="{ selectedRowKeys: selectedLocatorIds, onChange: (keys: number[]) => selectedLocatorIds = keys }" @change="handleLocatorTableChange">
        <a-table-column title="定位器" key="name" :width="310"><template #default="{record}"><b>{{record.name}}</b><small class="mt-1 block truncate text-slate-400">{{record.code}}</small></template></a-table-column>
        <a-table-column title="页面功能" key="pageName" :width="130"><template #default="{record}"><a-tag color="blue">{{displayLocatorPage(record)}}</a-tag></template></a-table-column>
        <a-table-column title="类型" data-index="type" :width="90"/>
        <a-table-column title="定位值" data-index="value" ellipsis/>
        <a-table-column title="稳定" key="stable" :width="100"><template #default="{record}"><a-tag :color="record.stable?'green':'orange'">{{record.stable?'稳定':'待观察'}}</a-tag></template></a-table-column>
        <a-table-column title="操作" :width="140"><template #default="{record}"><a-button type="link" @click="openLocator(record)">编辑</a-button><a-button type="link" danger @click="confirmDelete('locator',record)">删除</a-button></template></a-table-column>
      </a-table>
    </a-tab-pane>
    <a-tab-pane key="runs" tab="执行与回放">
      <div class="automation-toolbar justify-end"><a-button @click="load"><ReloadOutlined />刷新</a-button></div>
      <a-table :data-source="data.runs" :loading="loading" row-key="id" :scroll="{ x: 980 }">
        <a-table-column title="执行编号" key="execution" :width="180">
          <template #default="{ record }"><div><b class="text-ink">WEB-{{ record.id }}</b><small class="mt-1 block text-xs text-slate-400">{{ record.project }}</small></div></template>
        </a-table-column>
        <a-table-column title="任务" key="script" :width="250">
          <template #default="{ record }"><b class="text-ink">{{ record.script }}</b><small class="mt-1 block text-xs text-slate-400">脚本执行记录</small></template>
        </a-table-column>
        <a-table-column title="环境" data-index="environment" :width="190"><template #default="{ record }">{{ record.environment || '-' }}</template></a-table-column>
        <a-table-column title="浏览器" data-index="browser" :width="120" />
        <a-table-column title="状态" key="status" :width="110"><template #default="{ record }"><a-tag :color="record.status === 'passed' ? 'success' : record.status === 'failed' ? 'error' : 'processing'">{{ record.status }}</a-tag></template></a-table-column>
        <a-table-column title="开始时间" key="startedAt" :width="190"><template #default="{ record }">{{ record.startedAt ? new Date(record.startedAt).toLocaleString() : '-' }}</template></a-table-column>
        <a-table-column title="操作" key="action" :width="120" fixed="right"><template #default="{ record }"><a-button type="link" @click="showReplay(record)"><EyeOutlined />查看详情</a-button></template></a-table-column>
      </a-table>
    </a-tab-pane>
  </a-tabs></section>
  <a-drawer :open="Boolean(drawer)" :title="drawerTitle" :width="'min(806px,94vw)'" @close="drawer = null"><a-form layout="vertical"><template v-if="drawer==='script'"><a-form-item label="所属项目" required><a-select v-model:value="scriptForm.projectId" :options="projectOptions" :disabled="!!scriptForm.id"/></a-form-item><a-form-item label="名称" required><a-input v-model:value="scriptForm.name"/></a-form-item><a-form-item label="编码" required><a-input v-model:value="scriptForm.code"/></a-form-item><a-form-item label="入口文件"><a-input v-model:value="scriptForm.entryFile"/></a-form-item><a-form-item label="标签"><a-input v-model:value="scriptForm.tags" placeholder="smoke, login"/></a-form-item><a-form-item label="前置用户登录"><a-switch v-model:checked="scriptForm.needLogin"/><span class="ml-3 text-xs text-slate-500">默认复用项目已有登录脚本；登录脚本本身或公开页面可关闭</span></a-form-item><a-form-item label="说明"><a-textarea v-model:value="scriptForm.description" :rows="2"/></a-form-item><a-form-item label="Playwright 脚本" required><a-textarea v-model:value="scriptForm.content" :rows="16" class="font-mono"/></a-form-item><a-form-item label="状态"><a-select v-model:value="scriptForm.status" :options="[{label:'草稿',value:'draft'},{label:'启用',value:'active'},{label:'停用',value:'disabled'}]"/></a-form-item><a-button type="primary" @click="saveScript">保存脚本</a-button></template><template v-else-if="drawer==='environment'"><a-form-item label="所属项目" required><a-select v-model:value="environmentForm.projectId" :options="projectOptions" :disabled="!!environmentForm.id"/></a-form-item><a-form-item label="环境名" required><a-input v-model:value="environmentForm.name"/></a-form-item><a-form-item label="基础地址" required><a-input v-model:value="environmentForm.baseUrl"/></a-form-item><a-space><a-form-item label="浏览器"><a-select v-model:value="environmentForm.browserDefault" :options="['chromium','firefox','webkit'].map(value=>({label:value,value}))" class="w-36"/></a-form-item><a-form-item label="无头"><a-switch v-model:checked="environmentForm.headlessDefault"/></a-form-item><a-form-item label="超时 ms"><a-input-number v-model:value="environmentForm.timeoutMs" :min="1000"/></a-form-item></a-space><a-space><a-form-item label="宽"><a-input-number v-model:value="environmentForm.viewportWidth"/></a-form-item><a-form-item label="高"><a-input-number v-model:value="environmentForm.viewportHeight"/></a-form-item><a-form-item label="重试"><a-input-number v-model:value="environmentForm.retryTimes" :min="0"/></a-form-item></a-space><a-form-item label="运行变量 JSON"><a-textarea v-model:value="environmentForm.runtimeVariablesText" :rows="5" class="font-mono"/></a-form-item><a-form-item label="代理配置 JSON"><a-textarea v-model:value="environmentForm.proxyConfigText" :rows="3" class="font-mono"/></a-form-item><a-form-item label="说明"><a-textarea v-model:value="environmentForm.description"/></a-form-item><a-button type="primary" @click="saveEnvironment">保存环境</a-button></template><template v-else-if="drawer==='locator'"><a-form-item label="所属项目" required><a-select v-model:value="locatorForm.projectId" :options="projectOptions" :disabled="!!locatorForm.id"/></a-form-item><a-form-item label="名称" required><a-input v-model:value="locatorForm.name"/></a-form-item><a-form-item label="编码" required><a-input v-model:value="locatorForm.code"/></a-form-item><a-form-item label="定位方式"><a-select v-model:value="locatorForm.type" :options="['role','label','placeholder','text','testid','css','xpath','custom'].map(value=>({label:value,value}))"/></a-form-item><a-form-item label="定位值" required><a-textarea v-model:value="locatorForm.value" :rows="3"/></a-form-item><a-form-item label="页面功能" extra="用于定位器列表的功能分组与筛选"><a-auto-complete v-model:value="locatorForm.pageName" :options="locatorPageOptions" placeholder="例如：素材工单"/></a-form-item><a-space><a-form-item label="状态"><a-select v-model:value="locatorForm.status" :options="[{label:'启用',value:'active'},{label:'废弃',value:'deprecated'}]" class="w-36"/></a-form-item><a-form-item label="稳定"><a-switch v-model:checked="locatorForm.stable"/></a-form-item></a-space><a-button type="primary" @click="saveLocator">保存定位器</a-button></template><template v-else><a-form-item label="项目"><a-select v-model:value="runForm.projectId" :options="projectOptions" disabled/></a-form-item><a-form-item label="环境"><a-select v-model:value="runForm.environmentId" :options="runEnvironments.map(item=>({label:item.name,value:item.id}))" allow-clear/></a-form-item><a-form-item label="浏览器"><a-select v-model:value="runForm.browser" :options="['chromium','firefox','webkit'].map(value=>({label:value,value}))"/></a-form-item><a-button type="primary" @click="queueRun">加入队列</a-button></template></a-form></a-drawer>
  <a-modal v-model:open="detailOpen" title="脚本详情" :width="'min(1000px,94vw)'" :footer="null"><div v-if="detail" class="space-y-4"><div class="grid grid-cols-2 gap-3 text-sm"><div><b>{{detail.script.name}}</b><p class="text-slate-500">{{detail.script.description}}</p></div><div>入口：{{detail.script.entryFile}}<br/>版本：{{detail.versions?.length || 0}}</div></div><pre class="code-panel" v-html="highlightedDetailCode"/><a-table :data-source="detail.recentRuns" row-key="id" size="small"><a-table-column title="运行" data-index="id"/><a-table-column title="状态" data-index="status"/><a-table-column title="环境" data-index="environment"/></a-table></div></a-modal>
  <a-modal v-model:open="versionsOpen" :title="`${versionScript?.name || ''} · 版本历史`" :width="'min(980px,94vw)'" :footer="null"><a-button class="mb-3" :disabled="versions.length<2" @click="compareVersions">比较最近两个版本</a-button><a-table :data-source="versions" row-key="id" size="small"><a-table-column title="版本" data-index="version"/><a-table-column title="说明" data-index="summary"/><a-table-column title="时间" data-index="createdAt"/><a-table-column title="操作"><template #default="{record}"><a-button type="link" @click="restoreVersion(record.id)">恢复为新版本</a-button></template></a-table-column></a-table><pre v-if="versionDiff" class="code-panel mt-4" v-html="highlightedDiff"/></a-modal>
  <a-modal v-model:open="batchOpen" :title="`批量导入${batchKind==='script'?'脚本':'定位器'}`" :width="'min(806px,94vw)'" @ok="importItems"><p class="text-slate-500">粘贴 JSON 数组；导出文件也可直接粘贴。</p><a-textarea v-model:value="batchText" :rows="18" class="font-mono"/></a-modal>
  <a-drawer v-model:open="replayDrawerOpen" title="执行详情与产物" :width="'min(860px,94vw)'" root-class-name="execution-detail-drawer" :body-style="{ padding: '24px', overflow: 'hidden' }">
    <template v-if="replay">
      <div class="execution-detail-content">
      <div class="detail-hero mb-5">
        <div><p class="mb-1 text-xs tracking-wider text-slate-400">WEB-{{ replay.run.id }}</p><h3 class="m-0 text-lg font-semibold text-ink">{{ replay.run.script }}</h3></div>
        <a-space><span v-if="activeRunStatuses.has(replay.run.status)" class="text-xs text-slate-400">实时更新中</span><a-tag :color="replay.run.status === 'passed' ? 'success' : replay.run.status === 'failed' ? 'error' : 'processing'">{{ replay.run.status }}</a-tag></a-space>
      </div>
      <a-descriptions bordered :column="2" size="small" class="mb-5">
        <a-descriptions-item label="阶段">{{ replay.run.status }}</a-descriptions-item>
        <a-descriptions-item label="浏览器">{{ replay.run.browser || '-' }}</a-descriptions-item>
        <a-descriptions-item label="运行环境">{{ replay.run.environment || '-' }}</a-descriptions-item>
        <a-descriptions-item label="耗时">{{ replay.run.durationMs || 0 }} ms</a-descriptions-item>
        <a-descriptions-item label="开始时间" :span="2">{{ replay.run.startedAt ? new Date(replay.run.startedAt).toLocaleString() : '-' }}</a-descriptions-item>
      </a-descriptions>
      <template v-if="replay.failureAnalysis?.has_failure">
        <a-alert class="mb-3" :message="replay.failureAnalysis.summary" :description="replay.failureAnalysis.root_cause" type="error" show-icon />
        <a-descriptions bordered :column="2" size="small" class="mb-5">
          <a-descriptions-item label="问题类型"><a-tag color="error">{{ replay.failureAnalysis.category_label }}</a-tag></a-descriptions-item>
          <a-descriptions-item label="失败步骤">{{ replay.failureAnalysis.step_index ? `#${replay.failureAnalysis.step_index} ` : '' }}{{ replay.failureAnalysis.step_title || '-' }}</a-descriptions-item>
          <a-descriptions-item label="元素定位">{{ replay.failureAnalysis.locator || '-' }}</a-descriptions-item>
          <a-descriptions-item label="命中数量">{{ replay.failureAnalysis.match_count ?? '-' }}</a-descriptions-item>
          <a-descriptions-item label="处理建议" :span="2">{{ replay.failureAnalysis.suggestion }}</a-descriptions-item>
        </a-descriptions>
      </template>
      <a-alert v-else-if="replay.run.error" class="mb-5" :message="replay.run.error" type="error" show-icon />
      <div class="execution-detail-steps-panel">
        <div class="mb-3 flex items-center justify-between"><h4 class="m-0 text-base font-semibold text-ink">步骤产物</h4><span v-if="activeRunStatuses.has(replay.run.status)" class="text-xs text-slate-400">已记录 {{ replay.steps.length }} 步</span></div>
        <a-table :data-source="replay.steps" row-key="id" size="small" :pagination="false" class="execution-detail-steps" :scroll="{ x: 720, y: '100%' }">
          <a-table-column title="#" data-index="index" :width="54" />
          <a-table-column title="步骤" data-index="title" :width="230" />
          <a-table-column title="状态" key="status" :width="96"><template #default="{ record }"><a-badge v-if="record.status === 'running'" status="processing" text="执行中" /><a-tag v-else :color="record.status === 'passed' ? 'success' : record.status === 'failed' ? 'error' : 'default'">{{ record.status }}</a-tag></template></a-table-column>
          <a-table-column title="失败原因" key="failure" :width="150"><template #default="{ record }"><a-tooltip v-if="record.failureAnalysis" :title="record.failureAnalysis.root_cause"><a-tag color="error">{{ record.failureAnalysis.category_label }}</a-tag></a-tooltip><span v-else class="text-slate-400">—</span></template></a-table-column>
          <a-table-column title="耗时" key="duration" :width="96"><template #default="{ record }">{{ record.durationMs }} ms</template></a-table-column>
          <a-table-column title="截图" key="screenshot" :width="90"><template #default="{ record }"><a-button v-if="record.screenshotUrl" type="link" class="!px-0" @click="openArtifactPreview(record.screenshotUrl)">截图</a-button><span v-else class="text-slate-400">—</span></template></a-table-column>
        </a-table>
      </div>
      </div>
    </template>
  </a-drawer>
  <a-modal v-model:open="screenshotPreviewOpen" title="执行截图" :footer="null" :mask-closable="true" centered :width="'min(1080px,92vw)'" @cancel="screenshotPreviewUrl = ''"><div class="screenshot-preview"><img v-if="screenshotPreviewUrl" :src="screenshotPreviewUrl" alt="执行截图预览" /></div></a-modal>
</template>
<style scoped>
.eyebrow { @apply m-0 text-xs tracking-[.16em] text-brand; }
.page-heading { @apply m-2 ml-0 text-[30px] font-display font-bold text-ink; }
.automation-tabs :deep(.ant-tabs-nav) { margin-bottom: 12px; }
.automation-toolbar { @apply mb-3 flex flex-wrap items-center justify-between gap-3; }
.locator-filter-panel { @apply mb-4 rounded-xl border border-line bg-slate-50/70 p-4; }
.locator-filter-heading { @apply flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between; }
.locator-search { @apply w-full sm:!w-[310px]; }
.locator-page-groups { @apply mt-4 flex flex-wrap gap-2; }
.locator-page-chip { @apply inline-flex h-8 items-center gap-2 rounded-lg border border-line bg-white px-3 text-sm text-slate-600 transition-colors hover:border-brand hover:text-brand; }
.locator-page-chip-active { @apply border-brand bg-blue-50 font-medium text-brand shadow-sm; }
.locator-page-count { @apply rounded-full bg-slate-100 px-1.5 text-[11px] leading-5 text-slate-500; }
.locator-page-chip-active .locator-page-count { @apply bg-white text-brand; }
.locator-filter-summary { @apply mt-3 text-xs text-slate-400; }
.code-panel { @apply max-h-[480px] overflow-auto rounded-xl bg-slate-950 p-4 text-xs leading-6 text-slate-100; }
.artifact-image { @apply h-40 w-full rounded-lg object-cover; }
.detail-hero { @apply flex items-start justify-between rounded-xl border border-line bg-slate-50 px-4 py-4; }
.screenshot-preview { @apply flex max-h-[72vh] min-h-[240px] items-center justify-center overflow-auto rounded-xl bg-slate-950 p-3; }
.screenshot-preview img { @apply max-h-[68vh] max-w-full rounded-lg object-contain; }
:global(.execution-detail-drawer .ant-drawer-content-wrapper) { height: 100vh !important; }
:global(.execution-detail-drawer .ant-drawer-content) { display: flex; height: 100%; min-height: 0; flex-direction: column; }
:global(.execution-detail-drawer .ant-drawer-body) { display: flex; min-height: 0; flex: 1 1 auto; flex-direction: column; overflow: hidden !important; }
.execution-detail-content { display: flex; min-height: 0; height: 100%; flex: 1 1 auto; flex-direction: column; }
.execution-detail-steps-panel { display: flex; min-height: 0; flex: 1 1 auto; flex-direction: column; margin-bottom: 0 !important; overflow: hidden; padding-bottom: 16px; }
:global(.execution-detail-drawer .execution-detail-steps) { min-height: 0; flex: 1 1 auto; }
:global(.execution-detail-drawer .execution-detail-steps .ant-spin-nested-loading),
:global(.execution-detail-drawer .execution-detail-steps .ant-spin-container),
:global(.execution-detail-drawer .execution-detail-steps .ant-table),
:global(.execution-detail-drawer .execution-detail-steps .ant-table-container) { display: flex; min-height: 0; height: 100%; flex-direction: column; }
:global(.execution-detail-drawer .execution-detail-steps .ant-table-body) { height: 0 !important; min-height: 0; max-height: none !important; flex: 1 1 auto; box-sizing: border-box; overflow-y: auto !important; padding-bottom: 16px; overscroll-behavior: contain; }
</style>
