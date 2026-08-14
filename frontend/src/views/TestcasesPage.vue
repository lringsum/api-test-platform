<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { CodeOutlined, EditOutlined, PlayCircleOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import CodeBlock from '../components/CodeBlock.vue'
import { usePlatformStore } from '../stores/platform'
import type { TestCase } from '../types'

type CaseForm = {
  projectId: number | undefined
  moduleId: number | undefined
  name: string
  description: string
  source: 'manual'
  enabled: boolean
  caseData: string
}

const platform = usePlatformStore()
const keyword = ref('')
const selected = ref<TestCase>()
const previewOpen = ref(false)
const editorOpen = ref(false)
const submitting = ref(false)
const editingId = ref<number>()
const emptyCaseData = () => JSON.stringify({ name: '', method: 'GET', url: '/api/example', headers: {}, params: {}, body: {}, extract: {}, assertions: [{ type: 'status_code', expected: 200 }], pre_script: { enabled: false, language: 'python', template_id: null, content: '' } }, null, 2)
const form = ref<CaseForm>({ projectId: undefined, moduleId: undefined, name: '', description: '', source: 'manual', enabled: true, caseData: emptyCaseData() })
const filtered = computed(() => platform.testcases.filter((item) => `${item.name} ${item.endpoint} ${item.module} ${item.description}`.toLowerCase().includes(keyword.value.toLowerCase())))
const moduleOptions = computed(() => platform.modules.filter((module) => module.projectId === form.value.projectId))
const columns = [
  { title: '用例名称', dataIndex: 'name', key: 'name' },
  { title: '请求', dataIndex: 'method', key: 'method', width: 90 },
  { title: '接口地址', dataIndex: 'endpoint', key: 'endpoint' },
  { title: '所属模块', dataIndex: 'module', key: 'module', width: 130 },
  { title: '来源', dataIndex: 'source', key: 'source', width: 90 },
  { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 100 },
  { title: '操作', key: 'action', width: 200 },
]
const methodColor = (method: TestCase['method']) => ({ GET: 'blue', POST: 'green', PUT: 'orange', DELETE: 'red' })[method]

onMounted(async () => {
  try {
    await Promise.all([platform.loadTestcases(), platform.loadModules()])
  } catch {
    message.error('用例数据加载失败，请稍后重试。')
  }
})

function preview(item: TestCase) { selected.value = item; previewOpen.value = true }
function resetForm() {
  const projectId = platform.activeProjectId ?? platform.projects[0]?.id
  const moduleId = platform.modules.find((module) => module.projectId === projectId)?.id
  form.value = { projectId, moduleId, name: '', description: '', source: 'manual', enabled: true, caseData: emptyCaseData() }
}
function openCreate() { editingId.value = undefined; resetForm(); editorOpen.value = true }
function selectProject() { form.value.moduleId = moduleOptions.value[0]?.id }
function openEdit(item: TestCase) {
  editingId.value = item.id
  form.value = { projectId: item.projectId, moduleId: item.moduleId, name: item.name, description: item.description, source: item.source, enabled: item.enabled, caseData: JSON.stringify(item.caseData, null, 2) }
  editorOpen.value = true
}
function parseCaseData() {
  try {
    const caseData = JSON.parse(form.value.caseData)
    if (!caseData || Array.isArray(caseData) || typeof caseData !== 'object') throw new Error()
    return caseData as Record<string, unknown>
  } catch {
    message.error('用例 JSON 格式无效。')
    return undefined
  }
}
async function saveCase() {
  const caseData = parseCaseData()
  if (!caseData || !form.value.moduleId) return
  submitting.value = true
  try {
    if (editingId.value) {
      await platform.updateTestcase(editingId.value, { moduleId: form.value.moduleId, name: form.value.name, description: form.value.description, source: form.value.source, enabled: form.value.enabled, caseData })
    } else if (form.value.projectId) {
      await platform.addTestcase({ projectId: form.value.projectId, moduleId: form.value.moduleId, name: form.value.name, description: form.value.description, source: form.value.source, enabled: form.value.enabled, caseData })
    }
    editorOpen.value = false
    message.success(editingId.value ? '用例已更新。' : '用例已创建。')
  } catch {
    message.error('保存失败，请检查模块归属、权限和用例 JSON。')
  } finally {
    submitting.value = false
  }
}
async function removeCase(item: TestCase) {
  try {
    await platform.removeTestcase(item.id)
    message.success('用例已删除。')
  } catch {
    message.error('删除用例失败，请稍后重试。')
  }
}
</script>

<template>
  <section class="qa-panel p-5"><div class="flex flex-col gap-4 md:flex-row"><a-input v-model:value="keyword" class="flex-1" size="large" allow-clear placeholder="搜索用例名称、接口地址或模块"><template #prefix><SearchOutlined class="text-slate-400" /></template></a-input><a-button type="primary" size="large" @click="openCreate"><PlusOutlined />新增用例</a-button></div></section>
  <section class="qa-panel mt-6 overflow-hidden">
    <div class="flex items-center justify-between p-6"><div><h2 class="section-title">接口用例</h2><p class="mb-0 mt-1 text-sm text-slate-400">共 {{ filtered.length }} 条可维护的测试资产。</p></div><a-button><PlayCircleOutlined />批量执行</a-button></div>
    <a-table :data-source="filtered" :columns="columns" :pagination="{ pageSize: 10, showSizeChanger: false }" :scroll="{ x: 1020 }" row-key="id" class="px-3">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'"><b class="text-ink">{{ record.name }}</b><small class="mt-1 block text-xs text-slate-400">CASE-{{ String(record.id).padStart(4, '0') }}</small></template>
        <template v-else-if="column.key === 'method'"><a-tag :color="methodColor(record.method)">{{ record.method }}</a-tag></template>
        <template v-else-if="column.key === 'source'"><a-tag>手工</a-tag></template>
        <template v-else-if="column.key === 'enabled'"><a-badge :status="record.enabled ? 'success' : 'default'" :text="record.enabled ? '启用' : '停用'" /></template>
        <template v-else-if="column.key === 'action'"><a-button type="link" @click="preview(record)"><CodeOutlined />详情</a-button><a-button type="link" @click="openEdit(record)"><EditOutlined />编辑</a-button><a-popconfirm title="确认删除该测试用例吗？" ok-text="删除" cancel-text="取消" @confirm="removeCase(record)"><a-button danger type="link">删除</a-button></a-popconfirm></template>
      </template>
    </a-table>
  </section>
  <a-drawer v-model:open="previewOpen" :title="selected?.name" :width="'min(806px, 94vw)'" :footer-style="{ borderTop: '1px solid #e1ebfa' }"><template v-if="selected"><div class="mb-5 flex flex-wrap gap-2"><a-tag :color="methodColor(selected.method)">{{ selected.method }}</a-tag><a-tag>{{ selected.module }}</a-tag><a-tag :color="selected.enabled ? 'success' : 'default'">{{ selected.enabled ? '启用' : '停用' }}</a-tag></div><p class="mb-2 text-sm font-medium text-ink">请求地址</p><div class="mb-6 rounded-lg bg-slate-50 px-3 py-2 font-mono text-sm text-slate-600">{{ selected.endpoint }}</div><p class="mb-2 text-sm font-medium text-ink">用例 JSON</p><CodeBlock :code="selected.request" /></template></a-drawer>
  <a-drawer v-model:open="editorOpen" :title="editingId ? '编辑用例' : '新增用例'" :width="'min(806px, 94vw)'" :footer-style="{ borderTop: '1px solid #e1ebfa' }">
    <p class="mb-6 text-sm text-slate-500">JSON 会由后端按既有用例校验规则验证，保存后立即纳入项目测试资产。</p>
    <a-form layout="vertical" :model="form" @finish="saveCase">
      <div class="grid gap-x-4 md:grid-cols-2"><a-form-item label="所属项目" name="projectId" :rules="[{ required: true, message: '请选择所属项目' }]"><a-select v-model:value="form.projectId" size="large" :disabled="Boolean(editingId)" @change="selectProject"><a-select-option v-for="project in platform.projects" :key="project.id" :value="project.id">{{ project.name }}</a-select-option></a-select></a-form-item><a-form-item label="所属模块" name="moduleId" :rules="[{ required: true, message: '请选择所属模块' }]"><a-select v-model:value="form.moduleId" size="large"><a-select-option v-for="module in moduleOptions" :key="module.id" :value="module.id">{{ module.name }}</a-select-option></a-select></a-form-item></div>
      <a-form-item label="用例名称" name="name" :rules="[{ required: true, message: '请输入用例名称' }]"><a-input v-model:value="form.name" size="large" placeholder="例如：登录接口返回有效令牌" /></a-form-item>
      <a-form-item label="描述"><a-textarea v-model:value="form.description" :rows="3" placeholder="说明覆盖目标或异常边界" /></a-form-item>
      <div class="grid gap-x-4 md:grid-cols-2"><a-form-item label="来源"><a-input value="手工" size="large" disabled /></a-form-item><a-form-item label="状态"><a-switch v-model:checked="form.enabled" checked-children="启用" un-checked-children="停用" /></a-form-item></div>
      <a-form-item label="用例 JSON" name="caseData" :rules="[{ required: true, message: '请输入用例 JSON' }]"><a-textarea v-model:value="form.caseData" class="font-mono" :auto-size="{ minRows: 14, maxRows: 24 }" /></a-form-item>
      <div class="mt-8 flex justify-end gap-3"><a-button @click="editorOpen = false">取消</a-button><a-button type="primary" :loading="submitting" html-type="submit">保存用例</a-button></div>
    </a-form>
  </a-drawer>
</template>

<style scoped>
.eyebrow { @apply m-0 text-xs font-medium uppercase tracking-[.16em] text-brand; }
.page-heading { @apply m-2 ml-0 text-[30px] font-display font-bold text-ink; }
.section-title { @apply m-0 text-xl font-semibold text-ink; }
</style>
