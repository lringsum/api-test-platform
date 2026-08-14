<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { CheckCircleFilled, CloseCircleFilled, FileTextOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import CodeBlock from '../components/CodeBlock.vue'
import { platformApi } from '../services/platform'
import { usePlatformStore } from '../stores/platform'
import type { Execution, ExecutionDetail, ExecutionReport, ExecutionRunOptions, RunStatus } from '../types'

const platform = usePlatformStore()
const status = ref<'all' | RunStatus>('all')
const type = ref<'all' | Execution['executionType']>('all')
const runOpen = ref(false)
const detailOpen = ref(false)
const reportOpen = ref(false)
const loading = ref(false)
const detail = ref<ExecutionDetail>()
const report = ref<ExecutionReport>()
const listPanelRef = ref<HTMLElement>()
const listHeaderRef = ref<HTMLElement>()
const tableScrollY = ref(240)
let tableResizeObserver: ResizeObserver | undefined
const options = ref<ExecutionRunOptions>({ environments: [], modules: [], testcases: [] })
const runForm = ref({ mode: 'testcase' as 'testcase' | 'module' | 'selection' | 'project', environmentId: undefined as number | undefined, testcaseId: undefined as number | undefined, moduleId: undefined as number | undefined, testcaseIds: [] as number[] })
const filtered = computed(() => platform.executions.filter((item) => (status.value === 'all' || item.status === status.value) && (type.value === 'all' || item.executionType === type.value)))
const summary = computed(() => ({ total: platform.executions.length, passed: platform.executions.filter((item) => item.status === 'passed').length, failed: platform.executions.filter((item) => item.status === 'failed').length, rate: platform.executions.length ? Math.round((platform.executions.filter((item) => item.status === 'passed').length / platform.executions.length) * 100) : 0 }))
const selectedTestcases = computed(() => options.value.testcases.filter((item) => runForm.value.testcaseIds.includes(item.id)))
const columns = [{ title: '执行批次', dataIndex: 'name', key: 'name' }, { title: '项目', dataIndex: 'project', key: 'project', width: 130 }, { title: '类型', dataIndex: 'executionType', key: 'executionType', width: 120 }, { title: '状态', dataIndex: 'status', key: 'status', width: 110 }, { title: '通过率', dataIndex: 'passRate', key: 'passRate', width: 110 }, { title: '开始时间', dataIndex: 'startedAt', key: 'startedAt', width: 190 }, { title: '操作', key: 'action', width: 160 }]
function label(value: RunStatus) { return value === 'passed' ? '成功' : value === 'failed' ? '失败' : '执行中' }
function time(value: string) { return dayjs(value).format('MM-DD HH:mm:ss') }
function updateTableScrollHeight() {
  const panelHeight = listPanelRef.value?.clientHeight || 0
  const headerHeight = listHeaderRef.value?.clientHeight || 0
  tableScrollY.value = Math.max(160, panelHeight - headerHeight - 58)
}
onMounted(() => {
  void platform.loadOverview()
  void nextTick(() => {
    updateTableScrollHeight()
    tableResizeObserver = new ResizeObserver(updateTableScrollHeight)
    if (listPanelRef.value) tableResizeObserver.observe(listPanelRef.value)
    window.addEventListener('resize', updateTableScrollHeight)
  })
})
onBeforeUnmount(() => {
  tableResizeObserver?.disconnect()
  window.removeEventListener('resize', updateTableScrollHeight)
})
async function openRun() { if (!platform.activeProjectId) { message.warning('请先在顶部选择一个项目。'); return } loading.value = true; try { options.value = await platformApi.executionOptions(); runForm.value = { mode: 'testcase', environmentId: options.value.environments[0]?.id, testcaseId: options.value.testcases[0]?.id, moduleId: options.value.modules[0]?.id, testcaseIds: [] }; runOpen.value = true } catch { message.error('执行配置加载失败，请检查执行权限。') } finally { loading.value = false } }
async function submitRun() { if (!runForm.value.environmentId) { message.warning('请选择执行环境。'); return } const payload = { mode: runForm.value.mode, environmentId: runForm.value.environmentId, testcaseId: runForm.value.testcaseId, moduleId: runForm.value.moduleId, testcaseIds: runForm.value.testcaseIds, projectId: platform.activeProjectId }; if ((payload.mode === 'testcase' && !payload.testcaseId) || (payload.mode === 'module' && !payload.moduleId) || (payload.mode === 'selection' && !payload.testcaseIds.length)) { message.warning('请补全执行目标。'); return } loading.value = true; try { const execution = await platform.runExecution(payload); runOpen.value = false; message.success(`执行完成：${execution.passed}/${execution.total} 通过。`) } catch { message.error('执行失败，请检查环境、网络和用例配置。') } finally { loading.value = false } }
async function openDetail(item: Execution) { loading.value = true; try { detail.value = await platformApi.executionDetail(item.id); detailOpen.value = true } catch { message.error('执行详情加载失败。') } finally { loading.value = false } }
async function openReport(item: Execution) { loading.value = true; try { report.value = await platformApi.executionReport(item.id); reportOpen.value = true } catch { message.error('报告加载失败。') } finally { loading.value = false } }
</script>

<template>
  <main class="execution-page">
  <section class="grid shrink-0 gap-4 sm:grid-cols-2 xl:grid-cols-4"><article v-for="item in [{ label: '执行总数', value: summary.total, tone: 'blue' }, { label: '成功批次', value: summary.passed, tone: 'green' }, { label: '失败批次', value: summary.failed, tone: 'red' }, { label: '平均通过率', value: `${summary.rate}%`, tone: 'purple' }]" :key="item.label" class="qa-panel p-5"><p class="m-0 text-sm text-slate-500">{{ item.label }}</p><strong :class="`metric-value ${item.tone}`">{{ item.value }}</strong></article></section>
  <section class="qa-panel mt-6 p-5"><div class="grid gap-4 md:grid-cols-[1fr_1fr_auto_auto]"><a-select v-model:value="status" size="large"><a-select-option value="all">全部状态</a-select-option><a-select-option value="passed">成功</a-select-option><a-select-option value="failed">失败</a-select-option><a-select-option value="running">执行中</a-select-option></a-select><a-select v-model:value="type" size="large"><a-select-option value="all">全部类型</a-select-option><a-select-option value="接口测试">接口测试</a-select-option><a-select-option value="UI 自动化">UI 自动化</a-select-option></a-select><a-button size="large" @click="status = 'all'; type = 'all'"><ReloadOutlined />重置</a-button><a-button type="primary" size="large" :loading="loading" @click="openRun"><PlayCircleOutlined />立即执行</a-button></div></section>
  <section ref="listPanelRef" class="execution-list-panel qa-panel mt-6 overflow-hidden"><div ref="listHeaderRef" class="shrink-0 p-6"><h2 class="section-title">执行记录</h2><p class="mb-0 mt-1 text-sm text-slate-400">{{ filtered.length }} 个匹配的执行批次，按时间倒序排列。</p></div><a-table :data-source="filtered" :columns="columns" :pagination="{ pageSize: 8, showSizeChanger: false }" :scroll="{ x: 940, y: tableScrollY }" row-key="id" class="execution-table px-3"><template #bodyCell="{ column, record }"><template v-if="column.key === 'name'"><b class="text-ink">{{ record.name }}</b><small class="mt-1 block text-xs text-slate-400">RUN-{{ record.id }} · {{ record.total }} 条用例</small></template><template v-else-if="column.key === 'status'"><span :class="`status-pill ${record.status}`"><CheckCircleFilled v-if="record.status === 'passed'" /><CloseCircleFilled v-else-if="record.status === 'failed'" />{{ label(record.status) }}</span></template><template v-else-if="column.key === 'passRate'"><span class="font-medium" :class="record.passRate >= 90 ? 'text-emerald-600' : 'text-red-500'">{{ record.passRate }}%</span></template><template v-else-if="column.key === 'startedAt'">{{ time(record.startedAt) }}</template><template v-else-if="column.key === 'action'"><a-button type="link" @click="openDetail(record)">详情</a-button><a-button type="link" @click="openReport(record)"><FileTextOutlined />报告</a-button></template></template></a-table></section>
  </main>
  <a-drawer v-model:open="runOpen" title="执行配置" :width="'min(806px, 94vw)'" :footer-style="{ borderTop: '1px solid #e1ebfa' }"><p class="mb-6 text-sm text-slate-500">当前项目：{{ platform.activeProject?.name }}。真实执行会沿用既有变量注入、提取值回写和报告生成逻辑。</p><a-form layout="vertical" :model="runForm" @finish="submitRun"><a-form-item label="执行范围"><a-radio-group v-model:value="runForm.mode"><a-radio value="testcase">单用例</a-radio><a-radio value="module">模块</a-radio><a-radio value="selection">选中用例</a-radio><a-radio value="project">整个项目</a-radio></a-radio-group></a-form-item><a-form-item label="执行环境" name="environmentId" :rules="[{ required: true, message: '请选择执行环境' }]"><a-select v-model:value="runForm.environmentId" size="large"><a-select-option v-for="environment in options.environments" :key="environment.id" :value="environment.id">{{ environment.name }} · {{ environment.baseUrl }}</a-select-option></a-select></a-form-item><a-form-item v-if="runForm.mode === 'testcase'" label="测试用例"><a-select v-model:value="runForm.testcaseId" size="large"><a-select-option v-for="testcase in options.testcases" :key="testcase.id" :value="testcase.id">{{ testcase.module }} · {{ testcase.method }} {{ testcase.name }}</a-select-option></a-select></a-form-item><a-form-item v-if="runForm.mode === 'module'" label="模块"><a-select v-model:value="runForm.moduleId" size="large"><a-select-option v-for="module in options.modules" :key="module.id" :value="module.id">{{ module.name }}</a-select-option></a-select></a-form-item><a-form-item v-if="runForm.mode === 'selection'" label="测试用例"><a-select v-model:value="runForm.testcaseIds" mode="multiple" size="large" placeholder="选择一个或多个用例"><a-select-option v-for="testcase in options.testcases" :key="testcase.id" :value="testcase.id">{{ testcase.module }} · {{ testcase.name }}</a-select-option></a-select><p class="mb-0 mt-2 text-xs text-slate-400">已选择 {{ selectedTestcases.length }} 条用例。</p></a-form-item><div class="mt-8 flex justify-end gap-3"><a-button @click="runOpen = false">取消</a-button><a-button type="primary" :loading="loading" html-type="submit">开始执行</a-button></div></a-form></a-drawer>
  <a-drawer v-model:open="detailOpen" :title="`执行详情 · #${detail?.id ?? ''}`" :width="'min(806px, 94vw)'" :footer-style="{ borderTop: '1px solid #e1ebfa' }"><template v-if="detail"><div class="mb-5 grid grid-cols-3 gap-3"><div class="summary-card"><small>状态</small><b>{{ label(detail.status) }}</b></div><div class="summary-card"><small>通过率</small><b>{{ detail.passRate }}%</b></div><div class="summary-card"><small>执行环境</small><b>{{ detail.environment || '-' }}</b></div></div><a-collapse><a-collapse-panel v-for="item in detail.details" :key="item.id" :header="`${item.testcaseName} · ${item.status}`"><p v-if="item.errorMessage" class="mb-3 text-red-500">{{ item.errorMessage }}</p><p class="mb-2 font-medium text-ink">请求快照</p><CodeBlock :code="JSON.stringify(item.request, null, 2)" /><p class="mb-2 mt-5 font-medium text-ink">响应快照</p><CodeBlock :code="JSON.stringify(item.response, null, 2)" /></a-collapse-panel></a-collapse></template></a-drawer>
  <a-drawer v-model:open="reportOpen" :title="report?.title" :width="'min(806px, 94vw)'" :footer-style="{ borderTop: '1px solid #e1ebfa' }"><template v-if="report"><div class="mb-6 grid grid-cols-3 gap-3"><div class="summary-card"><small>总用例</small><b>{{ report.data.total_count }}</b></div><div class="summary-card"><small>通过</small><b class="text-emerald-600">{{ report.data.passed_count }}</b></div><div class="summary-card"><small>失败</small><b class="text-red-500">{{ report.data.failed_count }}</b></div></div><a-empty v-if="!report.data.failure_details.length" description="本次执行没有失败用例" /><a-list v-else bordered :data-source="report.data.failure_details"><template #renderItem="{ item }"><a-list-item><a-list-item-meta :title="item.testcase_name" :description="item.error_message || '断言未通过'" /></a-list-item></template></a-list></template></a-drawer>
</template>

<style scoped>.eyebrow { @apply m-0 text-xs font-medium uppercase tracking-[.16em] text-brand; }.page-heading { @apply m-2 ml-0 text-[30px] font-display font-bold text-ink; }.section-title { @apply m-0 text-xl font-semibold text-ink; }.metric-value { @apply mt-3 block text-[32px] leading-none; }.metric-value.blue { @apply text-brand; }.metric-value.green { @apply text-emerald-500; }.metric-value.red { @apply text-red-500; }.metric-value.purple { @apply text-violet-500; }.status-pill { @apply inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs; }.status-pill.passed { @apply bg-emerald-50 text-emerald-600; }.status-pill.failed { @apply bg-red-50 text-red-500; }.status-pill.running { @apply bg-amber-50 text-amber-600; }.summary-card { @apply rounded-xl border border-line bg-slate-50 p-4; }.summary-card small { @apply block text-xs text-slate-400; }.summary-card b { @apply mt-2 block text-base text-ink; }.execution-page { @apply flex h-full min-h-0 flex-col; }.execution-list-panel { @apply flex min-h-0 flex-1 flex-col; }.execution-table { @apply min-h-0 flex-1; }.execution-list-panel :deep(.execution-table) { max-height: none; overflow: hidden; }.execution-list-panel :deep(.ant-table-body) { overscroll-behavior: contain; }</style>
