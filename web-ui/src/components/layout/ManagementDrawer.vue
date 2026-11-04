<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  ChevronRight,
  Database,
  Link2,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-vue-next'
import { useWorkbench } from '@/composables/useWorkbench'
import type { WorkbenchIssue } from '@/api/workbench'

const router = useRouter()
const {
  summary,
  isManagementOpen,
  issues,
  closeManagement,
} = useWorkbench()

const CHANNEL_LABELS: Record<string, string> = {
  pushplus: 'PushPlus',
  ntfy: 'ntfy',
  bark: 'Bark',
  gotify: 'Gotify',
  wecom: '企业微信',
  telegram: 'Telegram',
  webhook: 'Webhook',
}

const accountSummary = computed(() => {
  const data = summary.value
  if (!data) return '正在读取账号状态…'
  const alert = data.account_alert_count || 0
  if (!data.account_count) return '尚未导入闲鱼账号'
  if (alert) return `${data.account_count} 个账号 · ${alert} 个需更新`
  return `${data.account_count} 个账号可用`
})

const notificationSummary = computed(() => {
  const data = summary.value
  if (!data) return '正在读取通知配置…'
  if (!data.notification_configured) return '尚未配置通知渠道'
  const channels = (data.notification_channels || [])
    .map((item) => CHANNEL_LABELS[item] || item)
    .join('、')
  const report = data.daily_report_enabled && data.daily_report_hour !== null
    ? ` · 日报 ${String(data.daily_report_hour).padStart(2, '0')}:05`
    : ''
  return `${channels || '已配置'}${report}`
})

const aiSummary = computed(() => {
  const data = summary.value
  if (!data) return '正在读取 AI 配置…'
  if (!data.ai_configured) return '尚未配置 AI 模型'
  return `已连接${data.ai_model ? ` · ${data.ai_model}` : ''}`
})

function go(path: string) {
  closeManagement()
  router.push(path)
}

function handleIssue(issue: WorkbenchIssue) {
  go(issue.action_route)
}

watch(isManagementOpen, (open) => {
  document.body.style.overflow = open ? 'hidden' : ''
})

watch(() => router.currentRoute.value.fullPath, () => {
  if (isManagementOpen.value) closeManagement()
})

function handleEscape(event: KeyboardEvent) {
  if (event.key === 'Escape' && isManagementOpen.value) closeManagement()
}

onMounted(() => document.addEventListener('keydown', handleEscape))
onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleEscape)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <transition name="drawer">
      <div v-if="isManagementOpen" class="fixed inset-0 z-[110]">
        <button
          type="button"
          class="absolute inset-0 cursor-default bg-[#1B2A44]/10 backdrop-blur-[0.5px]"
          aria-label="关闭管理"
          @click="closeManagement"
        />

        <aside
          class="absolute bottom-0 right-0 top-[109px] flex w-[460px] max-w-[94vw] flex-col border-l border-[#E2E8F3] bg-[#FBFCFE] shadow-[-24px_0_60px_-30px_rgba(15,35,70,0.4)] sm:top-[68px]"
          role="dialog"
          aria-modal="true"
          aria-labelledby="management-title"
        >
          <div class="flex items-start justify-between border-b border-[#EBEFF7] bg-white px-6 py-5">
            <div>
              <h2 id="management-title" class="text-[26px] font-black tracking-tight text-[#102A56]">管理</h2>
              <p class="mt-0.5 text-[12.5px] text-[#7B8AA3]">配置连接与通知</p>
            </div>
            <button
              type="button"
              class="mt-0.5 rounded-lg p-1.5 text-[#7B8AA3] transition-colors hover:bg-[#F2F5FA] hover:text-[#102A56]"
              aria-label="关闭"
              @click="closeManagement"
            >
              <X class="h-5 w-5" />
            </button>
          </div>

          <div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            <section v-if="issues.length" class="rounded-xl border border-[#F3D7A6] bg-[#FFF8EC] p-3.5">
              <div class="flex items-center gap-2 px-0.5">
                <AlertTriangle class="h-4 w-4 text-[#C7780B]" :stroke-width="2.4" />
                <h3 class="text-[13px] font-black tracking-wide text-[#9A5708]">需要处理</h3>
              </div>
              <div class="mt-2 space-y-1">
                <div
                  v-for="issue in issues.slice(0, 4)"
                  :key="issue.id"
                  class="flex items-center gap-3 rounded-lg px-1 py-2"
                >
                  <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-[#E6A23C]"></span>
                  <div class="min-w-0 flex-1">
                    <p class="truncate text-[13px] font-bold text-[#70420C]">{{ issue.title }}</p>
                    <p v-if="issue.detail" class="mt-0.5 line-clamp-1 text-[11.5px] text-[#A7793A]">{{ issue.detail }}</p>
                  </div>
                  <button
                    type="button"
                    class="shrink-0 rounded-md border border-[#E7BE82] bg-white/80 px-2.5 py-1 text-[11px] font-bold text-[#A75B09] transition-colors hover:bg-white"
                    @click="handleIssue(issue)"
                  >
                    {{ issue.action_label }}
                  </button>
                </div>
              </div>
            </section>

            <section v-else class="flex items-center gap-3 rounded-xl border border-[#D7E8DE] bg-[#F2FAF5] px-4 py-3">
              <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-[#E1F4E9] text-[#14815E]">
                <ShieldCheck class="h-4 w-4" />
              </span>
              <div>
                <p class="text-[13px] font-bold text-[#176B50]">当前没有待处理问题</p>
                <p class="text-[11px] text-[#5B8C79]">账号和任务运行正常。</p>
              </div>
            </section>

            <div class="mt-3 space-y-2.5">
              <button
                type="button"
                class="group flex w-full items-center gap-3.5 rounded-xl border border-[#E5EAF4] bg-white px-4 py-3.5 text-left transition-all hover:border-[#BFD2F2] hover:shadow-[0_10px_24px_-22px_rgba(35,96,230,0.5)]"
                @click="go('/accounts')"
              >
                <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#EEF4FF] text-[#2360E6]">
                  <Link2 class="h-[19px] w-[19px]" />
                </span>
                <span class="min-w-0 flex-1">
                  <span class="flex items-center gap-2">
                    <span class="text-[15px] font-black text-[#1A2F52]">账号连接</span>
                    <span v-if="summary?.account_alert_count" class="rounded bg-[#FFF3DB] px-1.5 py-0.5 text-[10px] font-bold text-[#A75B09]">
                      {{ summary.account_alert_count }} 需更新
                    </span>
                  </span>
                  <span class="mt-0.5 block truncate text-[12px] text-[#7B8AA3]">{{ accountSummary }}</span>
                </span>
                <ChevronRight class="h-4 w-4 shrink-0 text-[#B5C2D5] transition-transform group-hover:translate-x-0.5 group-hover:text-[#2360E6]" />
              </button>

              <button
                type="button"
                class="group flex w-full items-center gap-3.5 rounded-xl border border-[#E5EAF4] bg-white px-4 py-3.5 text-left transition-all hover:border-[#BFD2F2] hover:shadow-[0_10px_24px_-22px_rgba(35,96,230,0.5)]"
                @click="go('/settings?tab=notifications')"
              >
                <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#EEF4FF] text-[#2360E6]">
                  <Bell class="h-[19px] w-[19px]" />
                </span>
                <span class="min-w-0 flex-1">
                  <span class="text-[15px] font-black text-[#1A2F52]">通知</span>
                  <span class="mt-0.5 block truncate text-[12px] text-[#7B8AA3]">{{ notificationSummary }}</span>
                </span>
                <ChevronRight class="h-4 w-4 shrink-0 text-[#B5C2D5] transition-transform group-hover:translate-x-0.5 group-hover:text-[#2360E6]" />
              </button>

              <button
                type="button"
                class="group flex w-full items-center gap-3.5 rounded-xl border border-[#E5EAF4] bg-white px-4 py-3.5 text-left transition-all hover:border-[#BFD2F2] hover:shadow-[0_10px_24px_-22px_rgba(35,96,230,0.5)]"
                @click="go('/settings?tab=ai')"
              >
                <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#EEF4FF] text-[#2360E6]">
                  <Sparkles class="h-[19px] w-[19px]" />
                </span>
                <span class="min-w-0 flex-1">
                  <span class="text-[15px] font-black text-[#1A2F52]">AI 判断</span>
                  <span class="mt-0.5 block truncate text-[12px] text-[#7B8AA3]">{{ aiSummary }}</span>
                </span>
                <ChevronRight class="h-4 w-4 shrink-0 text-[#B5C2D5] transition-transform group-hover:translate-x-0.5 group-hover:text-[#2360E6]" />
              </button>

              <button
                type="button"
                class="group flex w-full items-center gap-3.5 rounded-xl border border-[#E5EAF4] bg-white px-4 py-3.5 text-left transition-all hover:border-[#BFD2F2] hover:shadow-[0_10px_24px_-22px_rgba(35,96,230,0.5)]"
                @click="go('/settings?tab=status')"
              >
                <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#EEF4FF] text-[#2360E6]">
                  <Database class="h-[19px] w-[19px]" />
                </span>
                <span class="min-w-0 flex-1">
                  <span class="text-[15px] font-black text-[#1A2F52]">数据与安全</span>
                  <span class="mt-0.5 block truncate text-[12px] text-[#7B8AA3]">本机访问 · SQLite 数据存储正常</span>
                </span>
                <ChevronRight class="h-4 w-4 shrink-0 text-[#B5C2D5] transition-transform group-hover:translate-x-0.5 group-hover:text-[#2360E6]" />
              </button>
            </div>
          </div>

          <div class="border-t border-[#EBEFF7] bg-white px-6 py-4">
            <button
              type="button"
              class="flex w-full items-center justify-center gap-1.5 py-1 text-[13px] font-black text-[#2360E6] transition-colors hover:text-[#1748B8]"
              @click="go('/settings')"
            >
              进入完整设置
              <ArrowRight class="h-4 w-4" />
            </button>
            <p class="mt-2 text-center text-[10.5px] leading-relaxed text-[#94A2B8]">
              未处理的账号或任务问题会持续显示在顶栏
            </p>
          </div>
        </aside>
      </div>
    </transition>
  </Teleport>
</template>

<style scoped>
.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 0.18s ease;
}
.drawer-enter-active aside,
.drawer-leave-active aside {
  transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1);
}
.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}
.drawer-enter-from aside,
.drawer-leave-to aside {
  transform: translateX(24px);
}
</style>
