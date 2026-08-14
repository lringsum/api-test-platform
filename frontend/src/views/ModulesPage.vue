<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ApartmentOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { usePlatformStore } from '../stores/platform'
import type { Module } from '../types'

const platform = usePlatformStore()
const keyword = ref('')
const createOpen = ref(false)
const editOpen = ref(false)
const submitting = ref(false)
const editingId = ref<number>()
const form = ref({ projectId: undefined as number | undefined, name: '', description: '' })
const editForm = ref({ name: '', description: '' })
const columns = [
  { title: '模块名称', dataIndex: 'name', key: 'name' },
  { title: '所属项目', dataIndex: 'project', key: 'project', width: 180 },
  { title: '测试用例', dataIndex: 'testcaseCount', key: 'testcaseCount', width: 110 },
  { title: '测试场景', dataIndex: 'scenarioCount', key: 'scenarioCount', width: 110 },
  { title: '最近更新', dataIndex: 'updatedAt', key: 'updatedAt', width: 180 },
  { title: '操作', key: 'action', width: 130 },
]
const list = computed(() => platform.modules.filter((item) => `${item.name}${item.project}${item.description}`.toLowerCase().includes(keyword.value.toLowerCase())))

onMounted(async () => {
  try {
    await platform.loadModules()
  } catch {
    message.error('模块数据加载失败，请稍后重试。')
  }
})

function openCreate() {
  form.value = { projectId: platform.activeProjectId ?? platform.projects[0]?.id, name: '', description: '' }
  createOpen.value = true
}

function openEdit(record: Module) {
  editingId.value = record.id
  editForm.value = { name: record.name, description: record.description }
  editOpen.value = true
}

async function createModule() {
  const projectId = form.value.projectId
  if (!projectId) {
    message.warning('请先选择所属项目。')
    return
  }
  submitting.value = true
  try {
    await platform.addModule({ projectId, name: form.value.name, description: form.value.description })
    createOpen.value = false
    message.success('模块已创建。')
  } catch {
    message.error('创建模块失败，请检查权限或输入内容。')
  } finally {
    submitting.value = false
  }
}

async function saveModule() {
  if (!editingId.value) return
  submitting.value = true
  try {
    await platform.updateModule(editingId.value, editForm.value)
    editOpen.value = false
    message.success('模块已更新。')
  } catch {
    message.error('保存模块失败，请稍后重试。')
  } finally {
    submitting.value = false
  }
}

async function removeModule(record: Module) {
  try {
    await platform.removeModule(record.id)
    message.success('模块已删除。')
  } catch {
    message.error('删除模块失败，请确认模块下没有受保护资源。')
  }
}
</script>

<template>
  <section class="qa-panel p-5">
    <div class="flex flex-col gap-4 md:flex-row"><a-input v-model:value="keyword" class="flex-1" size="large" placeholder="搜索模块、项目或描述"><template #prefix><SearchOutlined class="text-slate-400" /></template></a-input><a-button type="primary" size="large" @click="openCreate"><PlusOutlined />新建模块</a-button></div>
  </section>

  <section class="qa-panel mt-6 overflow-hidden">
    <div class="flex items-center justify-between p-6">
      <div>
        <h2 class="section-title">模块资源</h2>
        <p class="mb-0 mt-1 text-sm text-slate-400">共 {{ list.length }} 个模块，当前数据会随项目上下文切换。</p>
      </div>
      <span class="rounded-lg bg-blue-50 px-3 py-1.5 text-xs text-brand"><ApartmentOutlined class="mr-1" />资源边界</span>
    </div>
    <a-table :data-source="list" :columns="columns" :pagination="{ pageSize: 8, showSizeChanger: false }" :scroll="{ x: 900 }" row-key="id" class="px-3">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <div class="flex items-center gap-3">
            <span class="grid size-10 place-items-center rounded-xl bg-blue-50 text-lg text-brand"><ApartmentOutlined /></span>
            <div><b class="text-ink">{{ record.name }}</b><small class="mt-1 block text-xs text-slate-400">MODULE-{{ String(record.id).padStart(3, '0') }}</small></div>
          </div>
        </template>
        <template v-else-if="column.key === 'updatedAt'">{{ record.updatedAt ? new Date(record.updatedAt).toLocaleString() : '-' }}</template>
        <template v-else-if="column.key === 'action'">
          <a-button type="link" @click="openEdit(record)">编辑</a-button>
          <a-popconfirm title="确认删除该模块吗？关联资源会遵循后端删除规则。" ok-text="删除" cancel-text="取消" @confirm="removeModule(record)">
            <a-button danger type="link">删除</a-button>
          </a-popconfirm>
        </template>
      </template>
    </a-table>
  </section>

  <a-drawer v-model:open="createOpen" title="新建模块" :width="'min(806px, 94vw)'" :footer-style="{ borderTop: '1px solid #e1ebfa' }">
    <p class="mb-6 text-sm text-slate-500">模块会成为本项目内用例与场景的归属边界。</p>
    <a-form layout="vertical" :model="form" @finish="createModule">
      <a-form-item label="所属项目" name="projectId" :rules="[{ required: true, message: '请选择所属项目' }]">
        <a-select v-model:value="form.projectId" size="large" placeholder="选择项目"><a-select-option v-for="project in platform.projects" :key="project.id" :value="project.id">{{ project.name }}</a-select-option></a-select>
      </a-form-item>
      <a-form-item label="模块名称" name="name" :rules="[{ required: true, message: '请输入模块名称' }]"><a-input v-model:value="form.name" size="large" placeholder="例如：用户中心" /></a-form-item>
      <a-form-item label="模块描述"><a-textarea v-model:value="form.description" :rows="5" placeholder="说明模块负责的业务范围与关键测试目标" /></a-form-item>
      <div class="mt-8 flex justify-end gap-3"><a-button @click="createOpen = false">取消</a-button><a-button type="primary" :loading="submitting" html-type="submit">创建模块</a-button></div>
    </a-form>
  </a-drawer>

  <a-drawer v-model:open="editOpen" title="编辑模块" :width="'min(806px, 94vw)'" :footer-style="{ borderTop: '1px solid #e1ebfa' }">
    <p class="mb-6 text-sm text-slate-500">更新模块的基础信息，不改变其已归属的项目。</p>
    <a-form layout="vertical" :model="editForm" @finish="saveModule">
      <a-form-item label="模块名称" name="name" :rules="[{ required: true, message: '请输入模块名称' }]"><a-input v-model:value="editForm.name" size="large" /></a-form-item>
      <a-form-item label="模块描述"><a-textarea v-model:value="editForm.description" :rows="5" /></a-form-item>
      <div class="mt-8 flex justify-end gap-3"><a-button @click="editOpen = false">取消</a-button><a-button type="primary" :loading="submitting" html-type="submit">保存修改</a-button></div>
    </a-form>
  </a-drawer>
</template>

<style scoped>
.eyebrow { @apply m-0 text-xs font-medium uppercase tracking-[.16em] text-brand; }
.page-heading { @apply m-2 ml-0 text-[30px] font-display font-bold text-ink; }
.section-title { @apply m-0 text-xl font-semibold text-ink; }
</style>
