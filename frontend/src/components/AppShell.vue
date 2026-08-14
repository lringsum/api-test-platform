<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePlatformStore } from '../stores/platform'
import { platformApi } from '../services/platform'
import { ApiOutlined, ApartmentOutlined, BarChartOutlined, BellOutlined, CloudServerOutlined, DashboardOutlined, FolderOpenOutlined, KeyOutlined, MobileOutlined, RobotOutlined, SafetyCertificateOutlined, ShareAltOutlined, SearchOutlined, SettingOutlined, UserOutlined } from '@ant-design/icons-vue'

const route = useRoute()
const router = useRouter()
const platform = usePlatformStore()
const searchOpen = ref(false)
const query = ref('')
const activeKey = computed(() => route.name?.toString())
const pageTitle = computed(() => String(route.meta.title ?? 'Float QA'))
const pageDescription = computed(() => String(route.meta.description ?? '质量工程台'))
const overviewDestination = { name: 'dashboard', label: '总览', icon: DashboardOutlined }
const navigationGroups = [
  {
    key: 'api-testing', label: '接口测试', icon: ApiOutlined,
    items: [
      { name: 'projects', label: '项目资源', icon: FolderOpenOutlined },
      { name: 'modules', label: '模块管理', icon: ApartmentOutlined },
      { name: 'environments', label: '环境配置', icon: CloudServerOutlined },
      { name: 'variables', label: '变量管理', icon: KeyOutlined },
      { name: 'testcases', label: '用例设计', icon: ApiOutlined },
      { name: 'scenarios', label: '场景编排', icon: ShareAltOutlined },
    ],
  },
  {
    key: 'automation', label: 'UI 自动化', icon: RobotOutlined,
    items: [
      { name: 'web-automation', label: 'Web 自动化', icon: RobotOutlined },
      { name: 'android-automation', label: 'Android 自动化', icon: MobileOutlined },
    ],
  },
  {
    key: 'execution', label: '执行中心', icon: BarChartOutlined,
    items: [{ name: 'executions', label: '全部执行与报告', icon: BarChartOutlined }],
  },
  {
    key: 'security', label: '权限管理', icon: SafetyCertificateOutlined,
    items: [{ name: 'security', label: '用户、角色与审计', icon: SafetyCertificateOutlined }],
  },
]
const destinations = [overviewDestination, ...navigationGroups.flatMap((group) => group.items)]
const openKeys = ref<string[]>(['api-testing'])
const activeGroupKey = computed(() => navigationGroups.find((group) => group.items.some((item) => item.name === activeKey.value))?.key)
const searchResults = computed(() => destinations.filter((item) => item.label.includes(query.value.trim())))
function jump(name: string) { router.push({ name }); searchOpen.value = false; query.value = '' }
function handleMenu({ key }: { key: string }) { jump(key) }
function handleOpenChange(keys: string[]) { openKeys.value = keys }
async function changeProject(value: number | 'all') { await platform.selectProject(value === 'all' ? null : value) }
async function signOut() { await platformApi.logout(); window.location.assign('/login') }

watch(activeGroupKey, (groupKey) => {
  if (groupKey && !openKeys.value.includes(groupKey)) openKeys.value = [...openKeys.value, groupKey]
}, { immediate: true })

function handleKeyboardSearch(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    searchOpen.value = true
  }
}

onMounted(() => window.addEventListener('keydown', handleKeyboardSearch))
onBeforeUnmount(() => window.removeEventListener('keydown', handleKeyboardSearch))
</script>

<template>
  <a-layout class="h-screen overflow-hidden bg-canvas">
    <a-layout-sider class="!fixed !inset-y-0 !left-0 !z-20 !h-screen !overflow-hidden !bg-white !shadow-[1px_0_0_#e1ebfa]" :width="272" breakpoint="lg" collapsed-width="0">
      <div class="flex h-full flex-col px-5 py-8">
        <RouterLink to="/" class="mb-11 flex items-center gap-3 px-5 text-[26px] font-semibold tracking-[-1px] text-ink">
          <span class="grid size-7 place-items-center rounded-[5px] bg-brand text-sm text-white"><BellOutlined /></span> Float QA
        </RouterLink>
        <nav aria-label="主导航" class="min-h-0 flex-1 overflow-y-auto pr-1">
          <a-menu :selected-keys="[activeKey]" :open-keys="openKeys" mode="inline" class="!border-0 !bg-transparent !text-[15px]" @click="handleMenu" @open-change="handleOpenChange">
            <a-menu-item :key="overviewDestination.name" class="!mb-2 !h-11 !rounded-xl !leading-[44px]"><DashboardOutlined class="text-lg" /><span>{{ overviewDestination.label }}</span></a-menu-item>
            <a-sub-menu v-for="group in navigationGroups" :key="group.key" class="!mb-1">
              <template #title><component :is="group.icon" class="text-lg" /><span class="font-medium">{{ group.label }}</span></template>
              <a-menu-item v-for="item in group.items" :key="item.name" class="!my-1 !h-10 !rounded-lg !leading-10">
                <component :is="item.icon" class="text-base" /><span>{{ item.label }}</span>
              </a-menu-item>
            </a-sub-menu>
          </a-menu>
        </nav>
        <div class="mt-auto rounded-xl border border-line bg-white p-4 shadow-sm">
          <div class="flex items-center gap-3">
            <a-avatar :size="42" class="!bg-[#edf4ff] !text-brand"><UserOutlined /></a-avatar>
            <div class="min-w-0 flex-1"><p class="m-0 truncate font-medium text-ink">{{ platform.session?.user.displayName ?? '—' }}</p><span class="text-xs text-slate-400">{{ platform.session?.user.isSuperuser ? '管理员' : '平台用户' }}</span></div>
            <SettingOutlined class="text-slate-500" />
          </div>
        </div>
      </div>
    </a-layout-sider>
    <a-layout class="ml-0 h-screen overflow-hidden lg:ml-[272px]">
      <a-layout-header class="!z-10 !flex !h-[102px] !shrink-0 !items-center !justify-between !border-b !border-line !bg-white/95 !px-5 !backdrop-blur md:!px-10">
        <div><h1 class="m-0 font-display text-[30px] font-bold tracking-tight text-ink md:text-[34px]">{{ pageTitle }}</h1><p class="mt-1 mb-0 hidden text-sm text-slate-500 md:block">{{ pageDescription }}</p></div>
        <div class="flex items-center gap-3"><a-select class="!hidden !w-[180px] lg:!block" :value="platform.activeProjectId ?? 'all'" @change="changeProject"><a-select-option value="all">全部项目</a-select-option><a-select-option v-for="project in platform.projects" :key="project.id" :value="project.id">{{ project.name }}</a-select-option></a-select><a-button class="!hidden !h-11 !w-[294px] !rounded-xl !border-line !text-left !text-slate-500 md:!block" @click="searchOpen = true"><SearchOutlined class="mr-2" />全局搜索…</a-button><a-badge dot><a-avatar class="!bg-[#edf4ff] !text-brand"><BellOutlined /></a-avatar></a-badge><a-dropdown><a class="hidden text-slate-600 sm:block">{{ platform.session?.user.displayName ?? '已登录' }}</a><template #overlay><a-menu><a-menu-item>账号设置</a-menu-item><a-menu-item @click="signOut">退出登录</a-menu-item></a-menu></template></a-dropdown></div>
      </a-layout-header>
      <a-layout-content class="app-workspace !min-h-0 !flex-1 !overflow-hidden !p-5 md:!p-6 lg:!p-8"><slot /></a-layout-content>
    </a-layout>
  </a-layout>
  <a-modal v-model:open="searchOpen" :footer="null" title="搜索页面与功能" width="520px"><a-input v-model:value="query" autofocus size="large" placeholder="例如：用例、执行、项目"><template #prefix><SearchOutlined /></template></a-input><div v-if="searchResults.length" class="mt-4 space-y-1"><button v-for="item in searchResults" :key="item.name" class="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left hover:bg-blue-50" @click="jump(item.name)"><component :is="item.icon" class="text-brand" />{{ item.label }}</button></div><a-empty v-else class="py-8" description="未找到匹配的页面" /></a-modal>
</template>
