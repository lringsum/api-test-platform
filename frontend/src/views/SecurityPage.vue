<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { platformApi } from '../services/platform'
import { usePlatformStore } from '../stores/platform'
import type { AuditItem, SecurityMember, SecurityOptions, SecurityRole, SecurityUser } from '../types'

type SecurityTab = 'users' | 'roles' | 'members' | 'audit'
type DrawerKind = 'user' | 'role' | 'member' | null

const platform = usePlatformStore()
const options = ref<SecurityOptions | null>(null)
const users = ref<SecurityUser[]>([])
const roles = ref<SecurityRole[]>([])
const members = ref<SecurityMember[]>([])
const audits = ref<AuditItem[]>([])
const tab = ref<SecurityTab>('users')
const busy = ref(false)
const drawer = ref<DrawerKind>(null)
const userId = ref<number | null>(null)
const roleId = ref<number | null>(null)
const auditProject = ref<number | undefined>()

const userForm = ref({ username: '', displayName: '', email: '', password: '', isActive: true, isSuperuser: false, roleCodes: [] as string[] })
const roleForm = ref({ code: '', name: '', description: '', isSystem: false, sortOrder: 0, permissionCodes: [] as string[] })
const memberForm = ref({ projectId: undefined as number | undefined, userId: undefined as number | undefined, accessLevel: 'viewer', remark: '' })

const can = (permission: string) => Boolean(platform.session?.user.isSuperuser || platform.session?.permissions.includes(permission))
const visibleTabs = computed(() => [
  can('user:manage') && { key: 'users' as const, label: '用户' },
  can('role:manage') && { key: 'roles' as const, label: '角色与权限' },
  can('project_member:manage') && { key: 'members' as const, label: '项目成员' },
  can('audit:view') && { key: 'audit' as const, label: '审计日志' },
].filter(Boolean) as Array<{ key: SecurityTab; label: string }>)
const groups = computed(() => {
  const result: Record<string, SecurityOptions['permissions']> = {}
  for (const item of options.value?.permissions ?? []) (result[item.groupName] ??= []).push(item)
  return result
})
const roleOptions = computed(() => (roles.value.length ? roles.value : options.value?.roles ?? []).map((item) => ({ label: item.name, value: item.code })))
const memberUserOptions = computed(() => users.value.length ? users.value.map((item) => ({ id: item.id, username: item.username, displayName: item.displayName })) : options.value?.memberCandidates ?? [])
const title = computed(() => drawer.value === 'user' ? '用户编辑' : drawer.value === 'role' ? '角色编辑' : '成员授权')
const actionLabel = computed(() => tab.value === 'users' ? '新建用户' : tab.value === 'roles' ? '新建角色' : '授权成员')
const canCreateCurrent = computed(() => tab.value !== 'audit')

async function loadAudit() {
  if (can('audit:view')) audits.value = (await platformApi.securityAudit(1, auditProject.value)).items
}

async function load() {
  busy.value = true
  try {
    const needsOptions = visibleTabs.value.length > 0
    const [optionResult, userResult, roleResult, memberResult] = await Promise.all([
      needsOptions ? platformApi.securityOptions() : Promise.resolve(null),
      can('user:manage') ? platformApi.securityUsers() : Promise.resolve([]),
      can('role:manage') ? platformApi.securityRoles() : Promise.resolve([]),
      can('project_member:manage') ? platformApi.securityMembers() : Promise.resolve([]),
    ])
    options.value = optionResult
    users.value = userResult
    roles.value = roleResult
    members.value = memberResult
    await loadAudit()
    if (!visibleTabs.value.some((item) => item.key === tab.value)) tab.value = visibleTabs.value[0]?.key ?? 'users'
  } catch {
    message.error('权限数据加载失败')
  } finally {
    busy.value = false
  }
}

function editUser(item?: SecurityUser) {
  userId.value = item?.id ?? null
  userForm.value = item
    ? { username: item.username, displayName: item.displayName, email: item.email, password: '', isActive: item.isActive, isSuperuser: item.isSuperuser, roleCodes: item.roles.map((role) => role.code) }
    : { username: '', displayName: '', email: '', password: '', isActive: true, isSuperuser: false, roleCodes: [] }
  drawer.value = 'user'
}
async function saveUser() {
  if (!userId.value && !userForm.value.password) return message.warning('新用户必须设置密码')
  try {
    if (userId.value) await platformApi.updateSecurityUser(userId.value, userForm.value)
    else await platformApi.createSecurityUser(userForm.value)
    drawer.value = null
    await load()
    message.success('用户已保存')
  } catch {
    message.error('用户保存失败')
  }
}
function removeUser(item: SecurityUser) {
  if (item.isSuperuser) return message.warning('超级管理员不可删除')
  Modal.confirm({
    title: `删除 ${item.username}？`,
    content: '该操作不可恢复。',
    okType: 'danger',
    onOk: async () => {
      try {
        await platformApi.deleteSecurityUser(item.id)
        await load()
        message.success('用户已删除')
      } catch {
        message.error('删除失败')
      }
    },
  })
}

function editRole(item?: SecurityRole) {
  roleId.value = item?.id ?? null
  roleForm.value = item
    ? { code: item.code, name: item.name, description: item.description, isSystem: item.isSystem, sortOrder: item.sortOrder, permissionCodes: [...item.permissionCodes] }
    : { code: '', name: '', description: '', isSystem: false, sortOrder: 0, permissionCodes: [] }
  drawer.value = 'role'
}
async function saveRole() {
  try {
    if (roleId.value) await platformApi.updateSecurityRole(roleId.value, roleForm.value)
    else await platformApi.createSecurityRole(roleForm.value)
    drawer.value = null
    await load()
    message.success('角色已保存')
  } catch {
    message.error('角色保存失败')
  }
}

function editMember(item?: SecurityMember) {
  memberForm.value = item
    ? { projectId: item.projectId, userId: item.userId, accessLevel: item.accessLevel, remark: item.remark }
    : { projectId: undefined, userId: undefined, accessLevel: 'viewer', remark: '' }
  drawer.value = 'member'
}
async function saveMember() {
  const { projectId, userId, accessLevel, remark } = memberForm.value
  if (!projectId || !userId) return message.warning('请选择项目和用户')
  try {
    await platformApi.saveSecurityMember({ projectId, userId, accessLevel, remark })
    drawer.value = null
    await load()
    message.success('成员权限已保存')
  } catch {
    message.error('成员设置失败')
  }
}
function removeMember(item: SecurityMember) {
  Modal.confirm({
    title: `移除 ${item.username}？`,
    onOk: async () => {
      try {
        await platformApi.deleteSecurityMember(item.projectId, item.userId)
        await load()
        message.success('成员已移除')
      } catch {
        message.error('移除失败')
      }
    },
  })
}

function startCreate() {
  if (tab.value === 'users') editUser()
  else if (tab.value === 'roles') editRole()
  else if (tab.value === 'members') editMember()
}

onMounted(async () => {
  if (!platform.session) await platform.loadOverview()
  await load()
})
</script>

<template>
  <section class="qa-panel overflow-hidden">
    <div v-if="canCreateCurrent" class="flex justify-end px-5 pt-5"><a-button type="primary" @click="startCreate"><PlusOutlined />{{ actionLabel }}</a-button></div>
    <a-tabs v-model:active-key="tab" class="px-5 pt-3">
      <a-tab-pane v-if="can('user:manage')" key="users" tab="用户">
        <a-table :data-source="users" :loading="busy" row-key="id">
          <a-table-column title="账户" key="username"><template #default="{ record }"><b>{{ record.displayName || record.username }}</b><span class="ml-2 text-slate-400">@{{ record.username }}</span></template></a-table-column>
          <a-table-column title="邮箱" data-index="email" />
          <a-table-column title="角色" key="roles"><template #default="{ record }"><a-tag v-for="item in record.roles" :key="item.code">{{ item.name }}</a-tag></template></a-table-column>
          <a-table-column title="状态" key="isActive"><template #default="{ record }"><a-tag :color="record.isActive ? 'green' : 'default'">{{ record.isActive ? '启用' : '停用' }}</a-tag></template></a-table-column>
          <a-table-column title="操作"><template #default="{ record }"><a-button type="link" @click="editUser(record)"><EditOutlined />编辑</a-button><a-button danger type="link" :disabled="record.isSuperuser" @click="removeUser(record)"><DeleteOutlined />删除</a-button></template></a-table-column>
        </a-table>
      </a-tab-pane>
      <a-tab-pane v-if="can('role:manage')" key="roles" tab="角色与权限">
        <a-table :data-source="roles" :loading="busy" row-key="id">
          <a-table-column title="角色" key="name"><template #default="{ record }"><b>{{ record.name }}</b><span class="ml-2 text-slate-400">{{ record.code }}</span></template></a-table-column>
          <a-table-column title="权限" key="permissionCodes"><template #default="{ record }">{{ record.permissionCodes.length }} 项</template></a-table-column>
          <a-table-column title="操作"><template #default="{ record }"><a-button type="link" @click="editRole(record)"><EditOutlined />编辑</a-button></template></a-table-column>
        </a-table>
      </a-tab-pane>
      <a-tab-pane v-if="can('project_member:manage')" key="members" tab="项目成员">
        <a-table :data-source="members" :loading="busy" row-key="id">
          <a-table-column title="项目" data-index="project" /><a-table-column title="成员" data-index="username" /><a-table-column title="级别" data-index="accessLevel" />
          <a-table-column title="操作"><template #default="{ record }"><a-button type="link" @click="editMember(record)"><EditOutlined /></a-button><a-button type="link" danger @click="removeMember(record)"><DeleteOutlined /></a-button></template></a-table-column>
        </a-table>
      </a-tab-pane>
      <a-tab-pane v-if="can('audit:view')" key="audit" tab="审计日志">
        <a-select v-model:value="auditProject" allow-clear class="mb-4 w-56" placeholder="全部项目" @change="loadAudit"><a-select-option v-for="project in options?.projects" :key="project.id" :value="project.id">{{ project.name }}</a-select-option></a-select>
        <a-table :data-source="audits" :loading="busy" row-key="id"><a-table-column title="时间" data-index="createdAt" /><a-table-column title="用户" data-index="username" /><a-table-column title="动作" data-index="action" /><a-table-column title="资源" data-index="resourceType" /></a-table>
      </a-tab-pane>
    </a-tabs>
    <a-empty v-if="!visibleTabs.length && !busy" description="当前账号未获权限管理授权" class="py-12" />
  </section>
  <a-drawer :open="Boolean(drawer)" :width="'min(806px,94vw)'" :title="title" @close="drawer = null">
    <a-form v-if="drawer === 'user'" layout="vertical">
      <a-form-item label="用户名" required><a-input v-model:value="userForm.username" /></a-form-item><a-form-item label="显示名"><a-input v-model:value="userForm.displayName" /></a-form-item><a-form-item label="邮箱"><a-input v-model:value="userForm.email" /></a-form-item>
      <a-form-item :label="userId ? '新密码（留空不变）' : '密码'" :required="!userId"><a-input-password v-model:value="userForm.password" /></a-form-item><a-form-item label="角色"><a-select v-model:value="userForm.roleCodes" mode="multiple" :options="roleOptions" /></a-form-item>
      <a-space><a-form-item label="启用"><a-switch v-model:checked="userForm.isActive" /></a-form-item><a-form-item label="超级管理员"><a-switch v-model:checked="userForm.isSuperuser" /></a-form-item></a-space><a-button type="primary" @click="saveUser">保存用户</a-button>
    </a-form>
    <a-form v-else-if="drawer === 'role'" layout="vertical">
      <a-form-item label="编码"><a-input v-model:value="roleForm.code" /></a-form-item><a-form-item label="名称"><a-input v-model:value="roleForm.name" /></a-form-item><a-form-item label="说明"><a-textarea v-model:value="roleForm.description" /></a-form-item>
      <a-form-item label="权限"><a-checkbox-group v-model:value="roleForm.permissionCodes"><div v-for="(items, name) in groups" :key="name" class="mb-3"><b>{{ name }}</b><div><a-checkbox v-for="item in items" :key="item.code" :value="item.code">{{ item.name }}</a-checkbox></div></div></a-checkbox-group></a-form-item><a-button type="primary" @click="saveRole">保存角色</a-button>
    </a-form>
    <a-form v-else-if="drawer === 'member'" layout="vertical">
      <a-form-item label="项目"><a-select v-model:value="memberForm.projectId"><a-select-option v-for="project in options?.projects" :key="project.id" :value="project.id">{{ project.name }}</a-select-option></a-select></a-form-item><a-form-item label="用户"><a-select v-model:value="memberForm.userId"><a-select-option v-for="user in memberUserOptions" :key="user.id" :value="user.id">{{ user.displayName || user.username }}</a-select-option></a-select></a-form-item><a-form-item label="级别"><a-select v-model:value="memberForm.accessLevel"><a-select-option v-for="level in options?.accessLevels" :key="level" :value="level">{{ level }}</a-select-option></a-select></a-form-item><a-form-item label="备注"><a-textarea v-model:value="memberForm.remark" /></a-form-item><a-button type="primary" @click="saveMember">保存授权</a-button>
    </a-form>
  </a-drawer>
</template>

<style scoped>
.eyebrow { @apply m-0 text-xs tracking-[.16em] text-brand; }
.page-heading { @apply m-2 ml-0 text-[30px] font-display font-bold text-ink; }
</style>
