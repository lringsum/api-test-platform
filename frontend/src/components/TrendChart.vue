<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])
const props = defineProps<{ dates: string[]; passed: number[]; failed: number[] }>()
const container = ref<HTMLElement>()
let chart: echarts.ECharts | undefined

function draw() {
  if (!container.value) return
  chart ??= echarts.init(container.value)
  chart.setOption({
    grid: { left: 0, right: 10, top: 16, bottom: 0, containLabel: true },
    tooltip: { trigger: 'axis', backgroundColor: '#11204a', borderWidth: 0, textStyle: { color: '#fff' } },
    xAxis: { type: 'category', data: props.dates, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#8ba0bd', fontSize: 11 } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#edf3fb' } }, axisLabel: { color: '#8ba0bd', fontSize: 11 } },
    series: [
      { name: '通过', data: props.passed, type: 'line', smooth: true, symbol: 'none', lineStyle: { width: 3, color: '#1bb66e' }, areaStyle: { color: 'rgba(27,182,110,.10)' } },
      { name: '失败', data: props.failed, type: 'line', smooth: true, symbol: 'none', lineStyle: { width: 3, color: '#f1525d' } },
    ],
  })
}
const resize = () => chart?.resize()
onMounted(async () => { await nextTick(); draw(); window.addEventListener('resize', resize) })
watch(() => [props.dates, props.passed, props.failed], draw, { deep: true })
onBeforeUnmount(() => { window.removeEventListener('resize', resize); chart?.dispose() })
</script>

<template><div ref="container" class="h-[228px] w-full" /></template>
