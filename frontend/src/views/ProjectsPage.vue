<script setup lang="ts">
import { computed, ref } from 'vue'
import { FolderOpenOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { usePlatformStore } from '../stores/platform'
import type { Project } from '../types'

const platform = usePlatformStore()
const keyword = ref('')
const status = ref<'all' | 'active' | 'inactive'>('all')
const createOpen = ref(false)
const creating = ref(false)
const editOpen = ref(false)
const editingId = ref<number>()
const form = ref({ name: '', description: '' })
const editForm = ref({ name: '', description: '', status: 'active' as Project['status'] })
const list = computed(() => platform.projects.filter((project) => (status.value === 'all' || project.status === status.value) && `${project.name}${project.description}`.toLowerCase().includes(keyword.value.toLowerCase())))
const columns = [{ title: '项目名称', dataIndex: 'name', key: 'name' }, { title: '描述', dataIndex: 'description', key: 'description' }, { title: '状态', dataIndex: 'status', key: 'status', width: 120 }, { title: '模块', dataIndex: 'modules', key: 'modules', width: 90 }, { title: '环境', dataIndex: 'environments', key: 'environments', width: 90 }, { title: '最近更新时间', dataIndex: 'updatedAt', key: 'updatedAt', width: 180 }, { title: '操作', key: 'action', width: 120 }]
async function createProject() {
  creating.value = true
  try {
    await platform.addProject({ name: form.value.name, description: form.value.description, status: 'active' })
    createOpen.value = false
    form.value = { name: '', description: '' }
  } finally { creating.value = false }
}
function openEdit(project: Project) {
  editingId.value = project.id
  editForm.value = { name: project.name, description: project.description, status: project.status }
  editOpen.value = true
}
async function saveProject() {
  if (!editingId.value) return
  creating.value = true
  try {
    await platform.updateProject(editingId.value, editForm.value)
    editOpen.value = false
  } finally { creating.value = false }
}
async function removeProject(project: Project) { await platform.removeProject(project.id) }
</script>

<template>
  <section class="qa-panel p-5"><div class="grid gap-4 md:grid-cols-[1fr_180px_auto_auto]"><a-input v-model:value="keyword" size="large" placeholder="搜索项目名称或描述"><template #prefix><SearchOutlined class="text-slate-400" /></template></a-input><a-select v-model:value="status" size="large"><a-select-option value="all">全部状态</a-select-option><a-select-option value="active">启用中</a-select-option><a-select-option value="inactive">已停用</a-select-option></a-select><a-button size="large" @click="keyword = ''; status = 'all'">重置</a-button><a-button type="primary" size="large" @click="createOpen = true"><PlusOutlined />新建项目</a-button></div></section>
  <section class="qa-panel mt-6 overflow-hidden"><div class="flex items-center justify-between p-6"><div><h2 class="section-title">项目资源</h2><p class="mb-0 mt-1 text-sm text-slate-400">共 {{ list.length }} 个项目，按最近更新时间排序</p></div><span class="rounded-lg bg-blue-50 px-3 py-1.5 text-xs text-brand"><FolderOpenOutlined class="mr-1" />资源清单</span></div><a-table :data-source="list" :columns="columns" :pagination="{ pageSize: 8, showSizeChanger: false }" :scroll="{ x: 980 }" row-key="id" class="px-3"><template #bodyCell="{ column, record }"><template v-if="column.key === 'name'"><div class="flex items-center gap-3"><span class="grid size-10 place-items-center rounded-xl bg-blue-50 text-lg text-brand"><FolderOpenOutlined /></span><div><b class="text-ink">{{ record.name }}</b><small class="mt-1 block text-xs text-slate-400">PROJECT-{{ String(record.id).padStart(3, '0') }}</small></div></div></template><template v-else-if="column.key === 'status'"><a-tag :color="record.status === 'active' ? 'success' : 'default'">{{ record.status === 'active' ? '启用中' : '已停用' }}</a-tag></template><template v-else-if="column.key === 'action'"><a-button type="link" @click="openEdit(record)">编辑</a-button><a-popconfirm title="确认删除该项目及其关联资源吗？" ok-text="删除" cancel-text="取消" @confirm="removeProject(record)"><a-button danger type="link">删除</a-button></a-popconfirm></template></template></a-table></section>
  <a-drawer v-model:open="createOpen" title="新建项目" :width="'min(806px, 94vw)'" :footer-style="{ borderTop: '1px solid #e1ebfa' }"><p class="mb-6 text-sm text-slate-500">创建新的测试项目与基础配置。</p><a-form layout="vertical" :model="form" @finish="createProject"><a-form-item label="项目名称" name="name" :rules="[{ required: true, message: '请输入项目名称' }]"><a-input v-model:value="form.name" placeholder="例如：会员增长平台" size="large" /></a-form-item><a-form-item label="项目描述"><a-textarea v-model:value="form.description" :rows="5" placeholder="说明项目目标、业务范围或维修信息" /></a-form-item><div class="mt-8 flex justify-end gap-3"><a-button @click="createOpen = false">取消</a-button><a-button type="primary" :loading="creating" html-type="submit">创建项目</a-button></div></a-form></a-drawer>
  <a-drawer v-model:open="editOpen" title="编辑项目" :width="'min(806px, 94vw)'" :footer-style="{ borderTop: '1px solid #e1ebfa' }"><p class="mb-6 text-sm text-slate-500">更新项目基础信息和启用状态。</p><a-form layout="vertical" :model="editForm" @finish="saveProject"><a-form-item label="项目名称" name="name" :rules="[{ required: true, message: '请输入项目名称' }]"><a-input v-model:value="editForm.name" size="large" /></a-form-item><a-form-item label="项目描述"><a-textarea v-model:value="editForm.description" :rows="5" /></a-form-item><a-form-item label="项目状态"><a-select v-model:value="editForm.status" size="large"><a-select-option value="active">启用中</a-select-option><a-select-option value="inactive">已停用</a-select-option></a-select></a-form-item><div class="mt-8 flex justify-end gap-3"><a-button @click="editOpen = false">取消</a-button><a-button type="primary" :loading="creating" html-type="submit">保存修改</a-button></div></a-form></a-drawer>
</template>

<style scoped>.eyebrow { @apply m-0 text-xs font-medium uppercase tracking-[.16em] text-brand; }.page-heading { @apply m-2 ml-0 text-[30px] font-display font-bold text-ink; }.section-title { @apply m-0 text-xl font-semibold text-ink; }</style>
