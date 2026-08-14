<script setup lang="ts">
import { computed } from 'vue'
import hljs from 'highlight.js/lib/core'
import json from 'highlight.js/lib/languages/json'
import javascript from 'highlight.js/lib/languages/javascript'

hljs.registerLanguage('json', json)
hljs.registerLanguage('javascript', javascript)

const props = withDefaults(defineProps<{ code: string; language?: string }>(), { language: 'json' })
const highlighted = computed(() => hljs.highlight(props.code, { language: props.language, ignoreIllegals: true }).value)
</script>

<template>
  <pre class="overflow-x-auto rounded-xl border border-slate-200 bg-[#f8fbff] p-4 text-[12px] leading-6 text-slate-700"><code v-html="highlighted" /></pre>
</template>
