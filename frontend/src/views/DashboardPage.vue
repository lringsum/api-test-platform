<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ApiOutlined, AppstoreOutlined, CheckCircleFilled, CloseCircleFilled, FileTextOutlined, FolderOpenOutlined, PlayCircleFilled, RocketOutlined } from '@ant-design/icons-vue'
import TrendChart from '../components/TrendChart.vue'
import { usePlatformStore } from '../stores/platform'
import type { RunStatus } from '../types'

const router = useRouter()
const platform = usePlatformStore()
const dashboard = computed(() => platform.dashboard)
const statIcons = [FolderOpenOutlined, FileTextOutlined, AppstoreOutlined, PlayCircleFilled]
const quickLinks = [
  { title: '项目资源', detail: '查看与管理项目及相关资源', icon: FolderOpenOutlined, route: 'projects', tone: 'blue' },
  { title: '用例设计', detail: '创建、维护和管理测试用例', icon: FileTextOutlined, route: 'testcases', tone: 'green' },
  { title: '自动化工作台', detail: '创建与维护自动化测试', icon: ApiOutlined, route: 'testcases', tone: 'purple' },
  { title: '执行中心', detail: '执行测试并跟踪执行结果', icon: PlayCircleFilled, route: 'executions', tone: 'blue' },
]
function statusLabel(status: RunStatus) { return status === 'passed' ? '通过' : status === 'failed' ? '失败' : '执行中' }
function duration(seconds: number) { return seconds ? `${Math.floor(seconds / 60)}分 ${seconds % 60}秒` : '进行中' }
const columns = [
  { title: '执行名称', dataIndex: 'name', key: 'name', width: 280 }, { title: '类型', dataIndex: 'executionType', key: 'executionType', width: 140 }, { title: '状态', dataIndex: 'status', key: 'status', width: 140 }, { title: '耗时', dataIndex: 'duration', key: 'duration', width: 150 }, { title: '开始时间', dataIndex: 'startedAt', key: 'startedAt', width: 210 }, { title: '操作', key: 'action', width: 100 },
]
</script>

<template>
  <a-spin :spinning="platform.loading">
    <section class="qa-panel overflow-hidden">
      <div class="grid divide-y divide-line md:grid-cols-2 md:divide-x md:divide-y-0 xl:grid-cols-4">
        <article v-for="(stat, index) in dashboard?.stats" :key="stat.label" class="flex items-center gap-5 px-7 py-8">
          <span :class="`stat-orb stat-${stat.tone}`"><component :is="statIcons[index]" /></span>
          <div><strong class="block text-[36px] leading-10 tracking-tight text-slate-950">{{ stat.value.toLocaleString() }}</strong><span class="mt-2 block text-lg font-medium text-ink">{{ stat.label }}</span><small class="mt-2 block text-xs text-slate-400">{{ stat.hint }}</small></div>
        </article>
      </div>
    </section>
    <section class="mt-6 grid gap-6 xl:grid-cols-[1.55fr_1fr]">
      <article class="qa-panel p-6"><div class="mb-3 flex items-start justify-between"><div><p class="eyebrow">运行质量</p><h2 class="section-title">近 7 日执行趋势</h2></div><span class="rounded-full bg-emerald-50 px-3 py-1 text-xs text-emerald-600"><CheckCircleFilled class="mr-1" />稳定运行</span></div><TrendChart v-if="dashboard" :dates="dashboard.trend.dates" :passed="dashboard.trend.passed" :failed="dashboard.trend.failed" /></article>
      <article class="qa-panel p-6"><p class="eyebrow">本周概览</p><h2 class="section-title">自动化运行健康度</h2><div class="mt-6 space-y-5"><div class="health-row"><span>整体通过率</span><strong>94.6%</strong><a-progress :percent="94.6" :show-info="false" stroke-color="#1bb66e" /></div><div class="health-row"><span>活跃执行天数</span><strong>7 / 7</strong><a-progress :percent="100" :show-info="false" stroke-color="#1769f0" /></div><div class="rounded-xl bg-[#f7faff] p-4 text-sm text-slate-500"><RocketOutlined class="mr-2 text-brand" />已为团队节省 <b class="text-ink">14.8 小时</b> 手工回归时间</div></div></article>
    </section>
    <section class="qa-panel mt-6 overflow-hidden"><div class="flex items-center justify-between px-6 pb-4 pt-6"><h2 class="section-title">最近执行</h2><a-button type="link" @click="router.push({ name: 'executions' })">查看全部</a-button></div><a-table :columns="columns" :data-source="dashboard?.executions" :pagination="false" :scroll="{ x: 950 }" row-key="id" class="px-3"><template #bodyCell="{ column, record }"><template v-if="column.key === 'executionType'"><span :class="record.executionType === '接口测试' ? 'type-api' : 'type-ui'">{{ record.executionType }}</span></template><template v-else-if="column.key === 'status'"><span :class="`status-pill ${record.status}`"><CheckCircleFilled v-if="record.status === 'passed'" /><CloseCircleFilled v-else-if="record.status === 'failed'" /><span v-else class="size-2 animate-pulse rounded-full bg-amber-500" />{{ statusLabel(record.status) }}</span></template><template v-else-if="column.key === 'duration'">{{ duration(record.duration) }}</template><template v-else-if="column.key === 'action'"><a-button type="link" @click="router.push({ name: 'executions' })">查看详情</a-button></template></template></a-table></section>
    <section class="qa-panel mt-6 p-6"><h2 class="section-title mb-5">常用入口</h2><div class="grid gap-4 md:grid-cols-2 2xl:grid-cols-4"><button v-for="link in quickLinks" :key="link.title" class="quick-card text-left" @click="router.push({ name: link.route })"><span :class="`quick-icon ${link.tone}`"><component :is="link.icon" /></span><span class="min-w-0 flex-1"><b class="block text-base text-ink">{{ link.title }}</b><small class="mt-1 block text-xs text-slate-400">{{ link.detail }}</small></span><span class="text-xl text-slate-400">›</span></button></div></section>
  </a-spin>
</template>

<style scoped>
.stat-orb { @apply grid size-[72px] shrink-0 place-items-center rounded-full text-[32px]; }.stat-blue { @apply bg-blue-50 text-[#1769f0]; }.stat-green { @apply bg-emerald-50 text-emerald-500; }.stat-purple { @apply bg-violet-50 text-violet-500; }.stat-red { @apply bg-red-50 text-red-500; }.eyebrow { @apply m-0 text-xs font-medium uppercase tracking-[.16em] text-brand; }.section-title { @apply m-0 text-xl font-semibold text-ink; }.health-row { @apply grid grid-cols-[1fr_auto] gap-x-4 text-sm text-slate-500; }.health-row strong { @apply text-ink; }.health-row :deep(.ant-progress) { @apply col-span-2 mt-2; }.type-api, .type-ui { @apply rounded-md px-2.5 py-1 text-xs; }.type-api { @apply bg-blue-50 text-brand; }.type-ui { @apply bg-violet-50 text-violet-600; }.status-pill { @apply inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs; }.status-pill.passed { @apply bg-emerald-50 text-emerald-600; }.status-pill.failed { @apply bg-red-50 text-red-500; }.status-pill.running { @apply bg-amber-50 text-amber-600; }.quick-card { @apply flex items-center gap-4 rounded-xl border border-line bg-white p-3 transition duration-200 hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-panel; }.quick-icon { @apply grid size-14 place-items-center rounded-xl text-[27px]; }.quick-icon.blue { @apply bg-blue-50 text-brand; }.quick-icon.green { @apply bg-emerald-50 text-emerald-500; }.quick-icon.purple { @apply bg-violet-50 text-violet-500; }
</style>
