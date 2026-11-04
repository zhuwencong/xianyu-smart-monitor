<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import AboutFooter from '@/components/layout/AboutFooter.vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import ManagementDrawer from '@/components/layout/ManagementDrawer.vue'
import { useWorkbench } from '@/composables/useWorkbench'
import { useWebSocket } from '@/composables/useWebSocket'

const { t } = useI18n()
const { refreshSummary } = useWorkbench()
const { on } = useWebSocket()
let summaryTimer: ReturnType<typeof setInterval> | null = null

on('results_updated', () => refreshSummary())
on('tasks_updated', () => refreshSummary())
on('task_status_changed', () => refreshSummary())
onMounted(() => {
  refreshSummary()
  summaryTimer = setInterval(refreshSummary, 60_000)
})

onBeforeUnmount(() => {
  if (summaryTimer) clearInterval(summaryTimer)
})
</script>

<template>
  <div class="relative min-h-screen w-full bg-[#F4F7FC] selection:bg-[#2360E6]/15">
    <a
      href="#main-content"
      class="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[130] focus:rounded-lg focus:bg-[#2360E6] focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
    >
      {{ t('common.skipToContent') }}
    </a>

    <div aria-hidden="true" class="pointer-events-none fixed inset-0 overflow-hidden">
      <div class="absolute -left-48 -top-44 h-[560px] w-[560px] rounded-full bg-[#D7E7FF]/45 blur-[120px]"></div>
      <div class="absolute -right-40 top-[16%] h-[480px] w-[480px] rounded-full bg-[#DCEEFF]/50 blur-[130px]"></div>
      <div class="absolute bottom-[-180px] left-[28%] h-[420px] w-[680px] rounded-full bg-[#E8F1FF]/40 blur-[120px]"></div>
    </div>

    <AppHeader />

    <main id="main-content" tabindex="-1" class="relative z-10 focus:outline-none">
      <div class="mx-auto w-full max-w-[1600px] px-5 py-5 sm:px-7 sm:py-6 lg:px-10 lg:py-7">
        <RouterView v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </RouterView>
      </div>
    </main>

    <AboutFooter />

    <ManagementDrawer />
  </div>
</template>

<style scoped>
.page-enter-active,
.page-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.page-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
@media (prefers-reduced-motion: reduce) {
  .page-enter-active,
  .page-leave-active {
    transition: none;
  }
}
</style>
