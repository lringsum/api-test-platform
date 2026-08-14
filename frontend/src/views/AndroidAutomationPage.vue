<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { platformApi } from '../services/platform'
import type { AndroidAutomationOverview, AndroidFlowPreset, AndroidRunDetail, Project } from '../types'

type Flow = AndroidAutomationOverview['flows'][number]
type Task = AndroidAutomationOverview['tasks'][number]
type FlowStep = Flow['steps'][number]
type Device = Record<string, unknown>
type Exception = AndroidAutomationOverview['runs'][number] & { retryAdvice?: string }

const data = ref<AndroidAutomationOverview>({ flows: [], tasks: [], runs: [], devices: [], worker: {}, stepTypes: [], selectorTypes: [] })
const projects = ref<Project[]>([])
const presets = ref<AndroidFlowPreset[]>([])
const exceptions = ref<Exception[]>([])
const loading = ref(false)
const editorOpen = ref(false)
const detailOpen = ref(false)
const annotationOpen = ref(false)
const screenshotPreviewOpen = ref(false)
const screenshotPreviewUrl = ref('')
const mode = ref<'flow' | 'task' | 'step'>('flow')
const activeTab = ref('flows')
const selectedDevices = ref<string[]>([])
const selectedExceptions = ref<number[]>([])
const selectedRun = ref<AndroidRunDetail | null>(null)
const detailRefreshing = ref(false)
let detailPollTimer: ReturnType<typeof setTimeout> | null = null
const activeRunStatuses = new Set(['pending', 'running'])
const annotation = ref({ serials: [] as string[], tag: 'watch', note: '' })
const flow = ref({ id: 0, projectId: 0, name: '', code: '', description: '', isDefault: false, status: 'active' })
const task = ref({ id: 0, projectId: 0, name: '', packageKey: '', packageName: '', apkUrl: '', channelTag: '', deviceSerial: '', flowMode: 'basic', flowId: undefined as number | undefined, isActive: true, remark: '' })
const step = ref({ id: 0, flowId: 0, name: '', type: 'wait', selectorType: 'none', selectorValue: '', inputValue: '', waitTimeoutSec: 20, retryTimes: 0, continueOnFailure: false, captureOnSuccess: true, captureOnFailure: true, remark: '' })

const editorTitle = computed(() => {
  if (mode.value === 'flow') return flow.value.id ? '编辑流程' : '新建流程'
  if (mode.value === 'task') return task.value.id ? '编辑任务' : '新建任务'
  return step.value.id ? '编辑流程步骤' : '新增流程步骤'
})
const projectOptions = computed(() => projects.value.map(item => ({ label: item.name, value: item.id })))
const flowOptions = computed(() => data.value.flows.filter(item => item.projectId === task.value.projectId).map(item => ({ label: `${item.name} · ${item.code}`, value: item.id })))
const presetOptions = computed(() => presets.value.map(item => ({ label: `${item.name} (${item.stepCount} 步)`, value: item.key })))
const deviceRowSelection = computed(() => ({ selectedRowKeys: selectedDevices.value, onChange: (keys: Array<string | number>) => { selectedDevices.value = keys.map(String) } }))
const exceptionRowSelection = computed(() => ({ selectedRowKeys: selectedExceptions.value, onChange: (keys: Array<string | number>) => { selectedExceptions.value = keys.map(Number) } }))

async function load() {
  loading.value = true
  try {
    const [overview, projectList, presetList, exceptionList] = await Promise.all([
      platformApi.androidAutomationOverview(), platformApi.projects(), platformApi.androidFlowPresets(), platformApi.androidExceptions(),
    ])
    data.value = overview
    projects.value = projectList
    presets.value = presetList
    exceptions.value = exceptionList as Exception[]
  } catch {
    message.error('Android 自动化数据加载失败')
  } finally {
    loading.value = false
  }
}

function defaultProject() { return projects.value[0]?.id || 0 }
function editFlow(item?: Flow) {
  mode.value = 'flow'
  flow.value = item ? { id: item.id, projectId: item.projectId, name: item.name, code: item.code, description: item.description, isDefault: item.isDefault, status: item.status } : { id: 0, projectId: defaultProject(), name: '', code: '', description: '', isDefault: false, status: 'active' }
  editorOpen.value = true
}
function editTask(item?: Task) {
  mode.value = 'task'
  task.value = item ? { id: item.id, projectId: item.projectId, name: item.name, packageKey: item.packageKey, packageName: item.packageName, apkUrl: item.apkUrl, channelTag: item.channelTag, deviceSerial: item.deviceSerial, flowMode: item.flowMode, flowId: item.flowId || undefined, isActive: item.isActive, remark: item.remark } : { id: 0, projectId: defaultProject(), name: '', packageKey: '', packageName: '', apkUrl: '', channelTag: '', deviceSerial: '', flowMode: 'basic', flowId: undefined, isActive: true, remark: '' }
  editorOpen.value = true
}
function editStep(parent: Flow, item?: FlowStep) {
  mode.value = 'step'
  step.value = item ? { id: item.id, flowId: parent.id, name: item.name, type: item.type, selectorType: item.selectorType, selectorValue: item.selectorValue, inputValue: item.inputValue, waitTimeoutSec: item.waitTimeoutSec, retryTimes: item.retryTimes, continueOnFailure: item.continueOnFailure, captureOnSuccess: item.captureOnSuccess, captureOnFailure: item.captureOnFailure, remark: item.remark } : { id: 0, flowId: parent.id, name: '', type: data.value.stepTypes[0] || 'wait', selectorType: 'none', selectorValue: '', inputValue: '', waitTimeoutSec: 20, retryTimes: 0, continueOnFailure: false, captureOnSuccess: true, captureOnFailure: true, remark: '' }
  editorOpen.value = true
}
async function save() {
  try {
    if (mode.value === 'flow') flow.value.id ? await platformApi.updateAndroidFlow(flow.value.id, flow.value) : await platformApi.createAndroidFlow(flow.value)
    else if (mode.value === 'task') task.value.id ? await platformApi.updateAndroidTask(task.value.id, task.value) : await platformApi.createAndroidTask(task.value)
    else if (step.value.id) await platformApi.updateAndroidFlowStep(step.value.id, step.value)
    else await platformApi.createAndroidFlowStep(step.value.flowId, step.value)
    message.success('已保存')
    editorOpen.value = false
    await load()
  } catch {
    message.error('保存失败，请检查必填项及权限')
  }
}
async function run(item: Task) { try { await platformApi.queueAndroidRun(item.id); message.success('任务已进入队列'); await load() } catch { message.error('入队失败') } }
async function startWorker() { try { await platformApi.startAndroidWorker(); message.success('Worker 启动请求已提交'); await load() } catch { message.error('Worker 启动失败') } }
async function applyPreset(item: Flow, presetKey: string) {
  try { await platformApi.applyAndroidFlowPreset(item.id, presetKey, true); message.success('预设步骤已写入流程'); await load() } catch { message.error('应用预设失败') }
}
function remove(kind: 'flow' | 'task' | 'step', id: number) {
  Modal.confirm({ title: '确认删除', content: '该操作不可恢复。', okType: 'danger', onOk: async () => {
    try {
      if (kind === 'flow') await platformApi.deleteAndroidFlow(id)
      else if (kind === 'task') await platformApi.deleteAndroidTask(id)
      else await platformApi.deleteAndroidFlowStep(id)
      message.success('已删除'); await load()
    } catch { message.error('删除失败') }
  } })
}
function stopDetailPolling() {
  if (detailPollTimer) clearTimeout(detailPollTimer)
  detailPollTimer = null
}
function scheduleDetailPolling(runId: number) {
  stopDetailPolling()
  if (!detailOpen.value || document.hidden || !activeRunStatuses.has(selectedRun.value?.status || '')) return
  detailPollTimer = setTimeout(() => void refreshRunDetail(runId), 1000)
}
async function refreshRunDetail(runId: number) {
  if (!detailOpen.value || detailRefreshing.value) return
  detailRefreshing.value = true
  try {
    selectedRun.value = await platformApi.androidRunDetail(runId)
  } catch {
    detailPollTimer = setTimeout(() => void refreshRunDetail(runId), 3000)
    return
  } finally {
    detailRefreshing.value = false
  }
  scheduleDetailPolling(runId)
}
async function openRun(record: AndroidAutomationOverview['runs'][number]) {
  try {
    selectedRun.value = await platformApi.androidRunDetail(record.id)
    detailOpen.value = true
    scheduleDetailPolling(record.id)
  } catch { message.error('执行详情加载失败') }
}
async function retryRun(runId: number) { try { await platformApi.retryAndroidRun(runId); message.success('已重新入队'); await load() } catch { message.error('重试失败') } }
async function stopRun(runId: number) {
  Modal.confirm({ title: '停止执行', content: '将立即终止当前执行并记录为手动停止。', okType: 'danger', onOk: async () => {
    try { await platformApi.stopAndroidRun(runId); message.success('执行已停止'); detailOpen.value = false; await load() } catch { message.error('停止失败，仅排队中或执行中的记录可停止') }
  } })
}
async function retrySelectedExceptions() {
  if (!selectedExceptions.value.length) return message.warning('请先选择异常记录')
  try { const result = await platformApi.retryAndroidExceptions(selectedExceptions.value); message.success(`已重新入队 ${(result.created || []).length} 条记录`); selectedExceptions.value = []; await load() } catch { message.error('批量重试失败') }
}
async function batchDevice(action: 'enable' | 'disable' | 'set-default') {
  if (!selectedDevices.value.length) return message.warning('请先选择设备')
  try { await platformApi.batchAndroidDevices({ serials: selectedDevices.value, action }); message.success('设备配置已更新'); await load() } catch { message.error('设备批量操作失败') }
}
function editAnnotation(record?: Device) {
  const serials = record ? [String(record.serial || '')] : selectedDevices.value
  if (!serials.length) return message.warning('请先选择设备')
  annotation.value = { serials, tag: record ? String(record.annotation_tag || 'watch') : 'watch', note: record ? String(record.annotation_note || '') : '' }
  annotationOpen.value = true
}
async function saveAnnotation() {
  try { await platformApi.batchAndroidDevices({ serials: annotation.value.serials, action: 'annotate', annotationTag: annotation.value.tag, annotationNote: annotation.value.note }); message.success('设备标注已保存'); annotationOpen.value = false; await load() } catch { message.error('设备标注保存失败') }
}
function statusColor(status: unknown) { return status === 'passed' || status === 'idle' ? 'success' : status === 'failed' || status === 'disabled' ? 'error' : status === 'running' || status === 'busy' ? 'processing' : 'default' }
function canStop(status: string) { return status === 'pending' || status === 'running' }
function stepStatusLabel(status: string) { return ({ pending: '待执行', running: '执行中', passed: '通过', failed: '失败', stopped: '已停止', skipped: '已跳过' } as Record<string, string>)[status] || status }
function stepStatusColor(status: string) { return status === 'passed' ? 'success' : status === 'failed' || status === 'stopped' ? 'error' : status === 'running' ? 'processing' : 'default' }
const selectedRunProgress = computed(() => {
  const steps = selectedRun.value?.steps || []
  const completed = steps.filter(item => ['passed', 'failed', 'stopped', 'skipped'].includes(item.status)).length
  return { completed, total: steps.length, percent: steps.length ? Math.round((completed / steps.length) * 100) : 0 }
})

function openScreenshotPreview(url: string) {
  screenshotPreviewUrl.value = url
  screenshotPreviewOpen.value = true
}

function handleScreenshotLink(event: MouseEvent) {
  if (!detailOpen.value || !(event.target instanceof Element)) return
  const link = event.target.closest('a')
  if (!link?.href || !link.textContent?.includes('截图')) return
  event.preventDefault()
  openScreenshotPreview(link.href)
}

onMounted(() => {
  document.addEventListener('click', handleScreenshotLink, true)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  void load()
})
watch(detailOpen, (open) => {
  if (!open) stopDetailPolling()
  else if (selectedRun.value) scheduleDetailPolling(selectedRun.value.id)
})
function handleVisibilityChange() {
  if (!document.hidden && detailOpen.value && selectedRun.value) void refreshRunDetail(selectedRun.value.id)
  else stopDetailPolling()
}
onBeforeUnmount(() => {
  stopDetailPolling()
  document.removeEventListener('click', handleScreenshotLink, true)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>

<template>
  <section class="qa-panel overflow-hidden">
    <a-tabs v-model:active-key="activeTab" class="automation-tabs px-5 pt-1">
      <a-tab-pane key="flows" tab="流程编排">
        <div class="automation-toolbar justify-end"><a-button @click="load">刷新</a-button><a-button type="primary" @click="editFlow()">新建流程</a-button></div>
        <a-table :data-source="data.flows" :loading="loading" row-key="id" :pagination="false">
          <a-table-column title="流程" key="name">
            <template #default="{ record }"><div class="font-semibold text-slate-800">{{ record.name }}</div><div class="mt-1 text-xs text-slate-400">{{ record.code }} · {{ record.steps.length }} 步</div></template>
          </a-table-column>
          <a-table-column title="项目" data-index="project" />
          <a-table-column title="状态" key="status"><template #default="{ record }"><a-tag :color="record.status === 'active' ? 'success' : 'default'">{{ record.status === 'active' ? '启用' : '停用' }}</a-tag></template></a-table-column>
          <a-table-column title="预设" key="preset" :width="260"><template #default="{ record }"><a-select class="w-full" :options="presetOptions" placeholder="选择并写入预设" @change="(value: string) => applyPreset(record, value)" /></template></a-table-column>
          <a-table-column title="操作" key="action" :width="210"><template #default="{ record }"><a-button type="link" @click="editStep(record)">加步骤</a-button><a-button type="link" @click="editFlow(record)">编辑</a-button><a-button danger type="link" @click="remove('flow', record.id)">删除</a-button></template></a-table-column>
          <template #expandedRowRender="{ record }"><div class="flow-steps"><div v-if="!record.steps.length" class="py-3 text-sm text-slate-400">暂无步骤，可手工新增或直接应用流程预设。</div><div v-for="item in record.steps" :key="item.id" class="flow-step"><div class="flow-index">{{ item.stepNo }}</div><div class="min-w-0 flex-1"><div class="font-medium text-slate-700">{{ item.name }}</div><div class="mt-1 text-xs text-slate-400">{{ item.type }} · {{ item.selectorType }}{{ item.selectorValue ? ` · ${item.selectorValue}` : '' }}</div></div><a-space><a-button size="small" @click="editStep(record, item)">编辑</a-button><a-button danger size="small" @click="remove('step', item.id)">删除</a-button></a-space></div></div></template>
        </a-table>
      </a-tab-pane>

      <a-tab-pane key="tasks" tab="测试任务">
        <div class="automation-toolbar justify-end"><a-button @click="load">刷新</a-button><a-button type="primary" @click="editTask()">新建任务</a-button></div>
        <a-table :data-source="data.tasks" :loading="loading" row-key="id">
          <a-table-column title="任务" key="name"><template #default="{ record }"><div class="font-semibold">{{ record.name }}</div><div class="mt-1 text-xs text-slate-400">{{ record.packageKey }}</div></template></a-table-column>
          <a-table-column title="项目" data-index="project" /><a-table-column title="绑定设备" data-index="deviceSerial" /><a-table-column title="操作" key="action"><template #default="{ record }"><a-button type="link" @click="editTask(record)">编辑</a-button><a-button type="link" @click="run(record)">执行</a-button><a-button danger type="link" @click="remove('task', record.id)">删除</a-button></template></a-table-column>
        </a-table>
      </a-tab-pane>

      <a-tab-pane key="runs" tab="执行记录">
        <div class="automation-toolbar justify-end"><a-button @click="load">刷新</a-button></div>
        <a-table :data-source="data.runs" :loading="loading" row-key="id">
          <a-table-column title="执行编号" data-index="executionNo" /><a-table-column title="任务" data-index="task" /><a-table-column title="阶段" data-index="stage" /><a-table-column title="状态" key="status"><template #default="{ record }"><a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag></template></a-table-column><a-table-column title="设备" data-index="deviceSerial" /><a-table-column title="操作" key="action"><template #default="{ record }"><a-button type="link" @click="openRun(record)">详情 / 产物</a-button><a-button type="link" @click="retryRun(record.id)">重试</a-button><a-button v-if="canStop(record.status)" danger type="link" @click="stopRun(record.id)">停止</a-button></template></a-table-column>
        </a-table>
      </a-tab-pane>

      <a-tab-pane key="devices" tab="设备与 Worker">
        <div class="worker-banner"><div><span class="worker-dot" :class="data.worker.online ? 'is-online' : ''"></span><b>Worker {{ data.worker.online ? '在线' : '离线' }}</b><span class="ml-3 text-slate-500">{{ data.worker.state || 'unknown' }}</span></div><a-space><a-button @click="load">刷新</a-button><a-button type="primary" @click="startWorker">启动 Worker</a-button></a-space></div>
        <div class="mb-3 flex flex-wrap gap-2"><a-button @click="batchDevice('enable')">批量启用</a-button><a-button @click="batchDevice('disable')">批量禁用</a-button><a-button @click="editAnnotation()">批量标注</a-button><a-button @click="batchDevice('set-default')">设为默认设备</a-button><span class="self-center text-xs text-slate-400">默认设备仅允许选择一台。</span></div>
        <a-table :data-source="data.devices" :loading="loading" row-key="serial" :row-selection="deviceRowSelection" :pagination="false">
          <a-table-column title="设备" key="serial"><template #default="{ record }"><div class="font-medium">{{ record.serial }}</div><div class="mt-1 text-xs text-slate-400">{{ record.brand || '-' }} · {{ record.model || '-' }} · Android {{ record.android_version || '-' }}</div></template></a-table-column>
          <a-table-column title="状态" key="status"><template #default="{ record }"><a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag><a-tag v-if="record.is_default" color="blue">默认</a-tag></template></a-table-column>
          <a-table-column title="标注" key="annotation"><template #default="{ record }"><div>{{ record.annotation_tag || '未标注' }}</div><div class="text-xs text-slate-400">{{ record.annotation_note || '' }}</div></template></a-table-column>
          <a-table-column title="操作" key="action"><template #default="{ record }"><a-button type="link" @click="platformApi.updateAndroidDevice(String(record.serial), { default: true }).then(load)">默认</a-button><a-button type="link" @click="platformApi.updateAndroidDevice(String(record.serial), { disabled: !record.is_disabled }).then(load)">{{ record.is_disabled ? '启用' : '禁用' }}</a-button><a-button type="link" @click="editAnnotation(record)">标注</a-button></template></a-table-column>
        </a-table>
      </a-tab-pane>

      <a-tab-pane key="exceptions" tab="异常中心">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-3"><span class="text-sm text-slate-500">聚合失败执行，保留重试建议并支持批量重新入队。</span><a-space><a-button @click="load">刷新</a-button><a-button type="primary" @click="retrySelectedExceptions">批量重试（{{ selectedExceptions.length }}）</a-button></a-space></div>
        <a-table :data-source="exceptions" :loading="loading" row-key="id" :row-selection="exceptionRowSelection">
          <a-table-column title="执行编号" data-index="executionNo" /><a-table-column title="任务" data-index="task" /><a-table-column title="异常" key="error"><template #default="{ record }"><div class="font-medium text-rose-600">{{ record.errorType || '执行失败' }}</div><div class="mt-1 max-w-xl truncate text-xs text-slate-500">{{ record.error || '-' }}</div></template></a-table-column><a-table-column title="重试建议" data-index="retryAdvice" /><a-table-column title="操作" key="action"><template #default="{ record }"><a-button type="link" @click="openRun(record)">查看</a-button><a-button type="link" @click="retryRun(record.id)">重试</a-button></template></a-table-column>
        </a-table>
      </a-tab-pane>
    </a-tabs>
  </section>

  <a-drawer v-model:open="editorOpen" :title="editorTitle" :width="'min(806px,94vw)'" :destroy-on-close="true">
    <a-form layout="vertical">
      <template v-if="mode === 'flow'"><a-form-item label="项目" required><a-select v-model:value="flow.projectId" :options="projectOptions" :disabled="!!flow.id" /></a-form-item><a-form-item label="流程名称" required><a-input v-model:value="flow.name" /></a-form-item><a-form-item label="流程编码" required><a-input v-model:value="flow.code" /></a-form-item><a-form-item label="说明"><a-textarea v-model:value="flow.description" :rows="3" /></a-form-item><a-space><a-form-item label="默认流程"><a-switch v-model:checked="flow.isDefault" /></a-form-item><a-form-item label="状态"><a-select v-model:value="flow.status" :options="[{ label: '启用', value: 'active' }, { label: '停用', value: 'inactive' }]" class="w-32" /></a-form-item></a-space></template>
      <template v-else-if="mode === 'task'"><a-form-item label="项目" required><a-select v-model:value="task.projectId" :options="projectOptions" :disabled="!!task.id" /></a-form-item><a-form-item label="任务名称" required><a-input v-model:value="task.name" /></a-form-item><a-form-item label="包标识" required><a-input v-model:value="task.packageKey" /></a-form-item><a-form-item label="APK 下载地址" required><a-input v-model:value="task.apkUrl" /></a-form-item><a-form-item label="包名"><a-input v-model:value="task.packageName" /></a-form-item><a-form-item label="流程"><a-select v-model:value="task.flowId" :options="flowOptions" allow-clear /></a-form-item><a-form-item label="设备序列号"><a-input v-model:value="task.deviceSerial" /></a-form-item><a-form-item label="备注"><a-textarea v-model:value="task.remark" :rows="3" /></a-form-item></template>
      <template v-else><a-form-item label="步骤名称" required><a-input v-model:value="step.name" /></a-form-item><div class="grid grid-cols-2 gap-3"><a-form-item label="步骤类型"><a-select v-model:value="step.type" :options="data.stepTypes.map(value => ({ label: value, value }))" /></a-form-item><a-form-item label="选择器"><a-select v-model:value="step.selectorType" :options="data.selectorTypes.map(value => ({ label: value, value }))" /></a-form-item></div><a-form-item label="选择器值"><a-input v-model:value="step.selectorValue" /></a-form-item><a-form-item label="输入值"><a-input v-model:value="step.inputValue" /></a-form-item><div class="grid grid-cols-2 gap-3"><a-form-item label="等待超时（秒）"><a-input-number v-model:value="step.waitTimeoutSec" class="w-full" :min="1" /></a-form-item><a-form-item label="重试次数"><a-input-number v-model:value="step.retryTimes" class="w-full" :min="0" /></a-form-item></div><a-form-item label="备注"><a-textarea v-model:value="step.remark" :rows="3" /></a-form-item><a-space wrap><a-checkbox v-model:checked="step.continueOnFailure">失败后继续</a-checkbox><a-checkbox v-model:checked="step.captureOnSuccess">成功截图</a-checkbox><a-checkbox v-model:checked="step.captureOnFailure">失败截图</a-checkbox></a-space></template>
      <div class="mt-8 flex justify-end"><a-button type="primary" @click="save">保存</a-button></div>
    </a-form>
  </a-drawer>

  <a-drawer v-model:open="detailOpen" title="执行详情与产物" :width="'min(860px,94vw)'" root-class-name="execution-detail-drawer" :body-style="{ padding: '24px', overflow: 'hidden' }"><template v-if="selectedRun"><div class="execution-detail-content"><div class="detail-hero"><div><div class="text-xs tracking-widest text-slate-400">{{ selectedRun.executionNo }}</div><h3>{{ selectedRun.task }}</h3><a-space><a-tag :color="statusColor(selectedRun.status)">{{ selectedRun.status }}</a-tag><span v-if="activeRunStatuses.has(selectedRun.status)" class="text-xs text-slate-400">实时更新中</span></a-space></div><a-space><a-button @click="retryRun(selectedRun.id)">重试</a-button><a-button v-if="canStop(selectedRun.status)" danger @click="stopRun(selectedRun.id)">停止执行</a-button></a-space></div><a-descriptions bordered size="small" :column="2" class="mb-4"><a-descriptions-item label="阶段">{{ selectedRun.stage }}</a-descriptions-item><a-descriptions-item label="设备">{{ selectedRun.deviceSerial || '自动分配' }}</a-descriptions-item><a-descriptions-item label="耗时">{{ selectedRun.durationMs || 0 }} ms</a-descriptions-item><a-descriptions-item label="前台焦点">{{ selectedRun.currentFocus || '-' }}</a-descriptions-item><a-descriptions-item label="下载 / 安装">{{ selectedRun.downloadStatus || '-' }} / {{ selectedRun.installStatus || '-' }}</a-descriptions-item><a-descriptions-item label="启动 / 崩溃">{{ selectedRun.launchStatus || '-' }} / {{ selectedRun.crashStatus || '-' }}</a-descriptions-item></a-descriptions><div v-if="selectedRunProgress.total" class="mb-5 rounded-lg border border-slate-100 bg-slate-50 px-4 py-3"><div class="mb-2 flex justify-between text-xs text-slate-500"><span>步骤进度</span><span>{{ selectedRunProgress.completed }} / {{ selectedRunProgress.total }}</span></div><a-progress :percent="selectedRunProgress.percent" :status="selectedRun.status === 'failed' ? 'exception' : selectedRun.status === 'passed' ? 'success' : 'active'" size="small" /></div><div v-if="selectedRun.error" class="mb-5 rounded-lg border border-rose-100 bg-rose-50 p-3 text-sm text-rose-700">{{ selectedRun.error }}</div><div class="mb-5 flex flex-wrap gap-2"><a v-if="selectedRun.screenshotUrl" :href="selectedRun.screenshotUrl" target="_blank"><a-button>查看最终截图</a-button></a><a v-if="selectedRun.logUrl" :href="selectedRun.logUrl" target="_blank"><a-button>查看执行日志</a-button></a></div><div class="execution-detail-steps-panel"><h4 class="mb-3">步骤产物</h4><a-table :data-source="selectedRun.steps" row-key="id" size="small" :pagination="false" class="execution-detail-steps" :scroll="{ x: 720, y: '100%' }"><a-table-column title="#" data-index="stepNo" :width="55" /><a-table-column title="步骤" data-index="name" /><a-table-column title="状态" key="status"><template #default="{ record }"><a-badge v-if="record.status === 'running'" status="processing" text="执行中" /><a-tag v-else :color="stepStatusColor(record.status)">{{ stepStatusLabel(record.status) }}</a-tag></template></a-table-column><a-table-column title="产物" key="artifacts"><template #default="{ record }"><a v-if="record.screenshotUrl" :href="record.screenshotUrl" target="_blank">截图</a><span v-else class="text-slate-400">-</span></template></a-table-column></a-table></div></div></template></a-drawer>
  <a-modal v-model:open="annotationOpen" title="设备标注" @ok="saveAnnotation"><a-form layout="vertical"><a-form-item label="设备"><a-input :value="annotation.serials.join(', ')" disabled /></a-form-item><a-form-item label="标注"><a-select v-model:value="annotation.tag" :options="[{ label: '稳定', value: 'stable' }, { label: '观察', value: 'watch' }, { label: '避免', value: 'avoid' }]" /></a-form-item><a-form-item label="说明"><a-textarea v-model:value="annotation.note" :rows="3" placeholder="例如：仅用于回放；电量异常时避免调度" /></a-form-item></a-form></a-modal>
  <a-modal v-model:open="screenshotPreviewOpen" :footer="null" :mask-closable="true" centered title="执行截图" width="min(1080px, 92vw)" @cancel="screenshotPreviewUrl = ''">
    <div class="screenshot-preview"><img v-if="screenshotPreviewUrl" :src="screenshotPreviewUrl" alt="执行步骤截图" /></div>
  </a-modal>
</template>

<style scoped>
.eyebrow { @apply m-0 text-xs tracking-[.16em] text-brand; }
.page-heading { @apply m-2 ml-0 text-[30px] font-display font-bold text-ink; }
.automation-tabs :deep(.ant-tabs-nav) { margin-bottom: 12px; }
.automation-toolbar { @apply mb-3 flex flex-wrap items-center gap-3; }
.worker-banner { @apply mb-4 flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-4 py-3; }
.worker-dot { @apply mr-2 inline-block h-2.5 w-2.5 rounded-full bg-slate-300; }.worker-dot.is-online { @apply bg-emerald-500 shadow-[0_0_0_4px_rgba(16,185,129,.12)]; }
.flow-steps { @apply rounded-xl border border-slate-100 bg-slate-50/70 p-3; }.flow-step { @apply flex items-center gap-3 border-b border-slate-100 px-2 py-3 last:border-0; }.flow-index { @apply flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white text-xs font-bold text-brand shadow-sm; }
.detail-hero { @apply mb-5 flex items-start justify-between rounded-xl border border-slate-200 bg-slate-50 p-4; }.detail-hero h3 { @apply mb-2 mt-1 text-lg text-slate-800; }
.screenshot-preview { @apply flex max-h-[72vh] justify-center overflow-auto rounded-lg bg-slate-950 p-3; }.screenshot-preview img { @apply h-auto max-w-full rounded object-contain; }
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
