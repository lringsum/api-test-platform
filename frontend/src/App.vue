<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from './components/AppShell.vue'
import { usePlatformStore } from './stores/platform'
const platform = usePlatformStore()
const route = useRoute()
const isAuth = computed(() => route.name === 'login' || route.name === 'forbidden')
onMounted(() => { if (!isAuth.value) void platform.loadOverview() })
</script>

<template><RouterView v-if="isAuth" /><AppShell v-else><RouterView /></AppShell></template>
