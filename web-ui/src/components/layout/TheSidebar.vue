<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { 
  LayoutDashboard, 
  ListTodo, 
  Users, 
  Layers, 
  Terminal, 
  Settings2,
  Sparkles
} from 'lucide-vue-next'
import { useWebSocket } from '@/composables/useWebSocket'
import { useI18n } from 'vue-i18n'

const emit = defineEmits<{
  (event: 'navigate'): void
}>()
const { isConnected } = useWebSocket()
const { t } = useI18n()

const navItems = computed(() => [
  { to: '/dashboard', label: t('sidebar.dashboard'), icon: LayoutDashboard },
  { to: '/tasks', label: t('sidebar.tasks'), icon: ListTodo },
  { to: '/accounts', label: t('sidebar.accounts'), icon: Users },
  { to: '/results', label: t('sidebar.results'), icon: Layers },
  { to: '/logs', label: t('sidebar.logs'), icon: Terminal },
  { to: '/settings', label: t('sidebar.settings'), icon: Settings2 },
])

const connectionLabel = computed(() => (
  isConnected.value ? t('sidebar.backendConnected') : t('sidebar.backendConnecting')
))
const connectionTone = computed(() =>
  isConnected.value
    ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]'
    : 'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.45)]'
)
</script>

<template>
  <nav class="flex h-full flex-col">
    <div class="mb-3 px-3 text-[10px] font-extrabold uppercase tracking-[0.2em] text-slate-400">
      Workspace
    </div>
    <div class="space-y-1.5">
      <RouterLink
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        v-slot="{ isActive }"
        class="block"
        @click="emit('navigate')"
      >
        <div
          class="group flex items-center gap-3 rounded-xl px-3 py-2.5 transition-all duration-200"
          :class="isActive ? 'bg-primary text-white shadow-[0_10px_24px_-12px_rgba(18,95,224,0.8)]' : 'text-slate-600 hover:bg-blue-50/80 hover:text-blue-700'"
        >
        <span
          class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors"
          :class="isActive ? 'bg-white/15' : 'bg-slate-100 text-slate-400 group-hover:bg-white group-hover:text-primary'"
        >
          <component :is="item.icon" class="h-[18px] w-[18px]" />
        </span>
        <span class="flex-grow text-sm font-bold">{{ item.label }}</span>
        <span v-if="isActive" class="h-1.5 w-1.5 rounded-full bg-white/90"></span>
        </div>
      </RouterLink>
    </div>

    <div class="mt-auto pt-8">
      <div class="overflow-hidden rounded-2xl border border-blue-100 bg-gradient-to-br from-blue-50 to-indigo-50/70 p-4">
        <div class="mb-4 flex items-center gap-2 text-blue-700">
          <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-white shadow-sm">
            <Sparkles class="h-4 w-4" />
          </span>
          <div>
            <p class="text-[10px] font-black tracking-[0.12em]">MAKER COSMOS</p>
            <p class="mt-0.5 text-[9px] font-bold tracking-[0.2em] text-blue-400">AI CONSOLE</p>
          </div>
        </div>
        <div class="border-t border-blue-100/80 pt-3">
          <p class="mb-2 text-[10px] font-bold text-slate-400">{{ t('sidebar.systemStatus') }}</p>
          <div class="flex items-center gap-2">
            <span class="h-2 w-2 rounded-full" :class="connectionTone"></span>
            <span class="text-xs font-bold text-slate-600">{{ connectionLabel }}</span>
          </div>
        </div>
      </div>
    </div>
  </nav>
</template>
