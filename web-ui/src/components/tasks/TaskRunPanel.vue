<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleSlash,
  Clock3,
  FileText,
  Loader2,
  PlayCircle,
  Search,
  X,
} from 'lucide-vue-next'
import type { WorkbenchRun, WorkbenchTask } from '@/api/workbench'
import { formatDuration, formatRelativeDay } from '@/lib/format'

const props = defineProps<{
  task: WorkbenchTask
  runs: WorkbenchRun[]
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'view-results'): void
  (event: 'full-log'): void
}>()

const selectedId = ref<string | number | null>(null)

const selectedRun = computed<WorkbenchRun | null>(() => {
  return props.runs.find((run) => run.id === selectedId.value) || props.runs[0] || null
})

watch(
  () => props.task.id,
  () => {
    selectedId.value = props.runs[0]?.id ?? null
  },
  { immediate: true }
)

watch(
  () => props.runs,
  (runs) => {
    if (!runs.some((run) => run.id === selectedId.value)) {
      selectedId.value = runs[0]?.id ?? null
    }
  }
)

function runTone(status: string) {
  switch (status) {
    case 'completed':
      return {
        chip: 'border-[#BFE8D7] bg-[#EAF8F2] text-[#0C7A56]',
        icon: CheckCircle2,
        accent: 'border-[#CFECE1] bg-[#F3FBF8]',
        title: 'text-[#0C7A56]',
      }
    case 'partial':
      return {
        chip: 'border-[#F1D7A7] bg-[#FFF8EA] text-[#A56209]',
        icon: AlertTriangle,
        accent: 'border-[#F2DDB5] bg-[#FFFAF0]',
        title: 'text-[#9A5708]',
      }
    case 'failed':
      return {
        chip: 'border-[#F1D3CE] bg-[#FFF4F2] text-[#B83B2D]',
        icon: CircleSlash,
        accent: 'border-[#F3D8D3] bg-[#FFF8F6]',
        title: 'text-[#B83B2D]',
      }
    case 'running':
      return {
        chip: 'border-[#C9DCF8] bg-[#F0F6FF] text-[#2360E6]',
        icon: Loader2,
        accent: 'border-[#D4E2F8] bg-[#F5F9FF]',
        title: 'text-[#2360E6]',
      }
    case 'stopped':
      return {
        chip: 'border-[#E0E5EE] bg-[#F5F7FA] text-[#64748B]',
        icon: CircleSlash,
        accent: 'border-[#E3E8F1] bg-[#FAFBFD]',
        title: 'text-[#52637B]',
      }
    default:
      return {
        chip: 'border-[#E0E5EE] bg-[#F5F7FA] text-[#64748B]',
        icon: CircleSlash,
        accent: 'border-[#E3E8F1] bg-[#FAFBFD]',
        title: 'text-[#52637B]',
      }
  }
}

const detailTone = computed(() => runTone(selectedRun.value?.status || 'no_new'))

const detailTitle = computed(() => {
  const run = selectedRun.value
  if (!run) return '暂无运行记录'
  if (run.status === 'running') return '本轮正在运行'
  if (run.status === 'partial') return '本轮未完成，已有结果已保留'
  if (run.status === 'failed') return '本轮未能完成'
  if (run.status === 'stopped') return '本轮已手动停止'
  if (run.status === 'no_new') return '本轮没有发现新商品'
  return '本轮已完成'
})

const detailDescription = computed(() => {
  const run = selectedRun.value
  if (!run) return ''
  if (run.error_message) return run.error_message
  return run.summary || '运行记录已保存。'
})

function selectRun(run: WorkbenchRun) {
  selectedId.value = run.id
}

function statusText(run: WorkbenchRun) {
  if (run.status === 'completed') return `已完成 · 已保存 ${run.saved_count} 条`
  if (run.status === 'partial') return `部分完成 · 已保存 ${run.saved_count} 条`
  if (run.status === 'failed') return '异常退出'
  if (run.status === 'no_new') return '无新增'
  if (run.status === 'running') return '运行中'
  return run.status_label || '已结束'
}
</script>

<template>
  <section class="overflow-hidden rounded-2xl border border-[#DDE6F3] bg-white shadow-[0_18px_50px_-42px_rgba(15,45,90,0.4)]">
    <header class="flex items-center justify-between border-b border-[#E9EEF7] bg-[#F8FAFE] px-5 py-3.5">
      <div class="flex min-w-0 items-center gap-2.5">
        <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white text-[#2360E6] shadow-sm">
          <Clock3 class="h-4 w-4" />
        </span>
        <div class="min-w-0">
          <h2 class="truncate text-[16px] font-black text-[#1B3358]">{{ task.task_name }} · 运行记录</h2>
          <p class="text-[11px] text-[#8796AC]">日志与保存结果都归属于当前任务</p>
        </div>
      </div>
      <button
        type="button"
        class="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold text-[#7B8AA3] transition-colors hover:bg-white hover:text-[#2360E6]"
        @click="emit('close')"
      >
        关闭
        <X class="h-3.5 w-3.5" />
      </button>
    </header>

    <div v-if="!runs.length" class="px-6 py-10 text-center text-[12.5px] text-[#8796AC]">
      还没有运行记录。手动运行一次或等待定时任务触发后，这里会显示结果。
    </div>

    <div v-else class="grid gap-3.5 p-3.5 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
      <div class="rounded-xl border border-[#E9EEF7]">
        <div class="border-b border-[#EEF2F8] px-4 py-3">
          <h3 class="text-[12.5px] font-black text-[#334867]">运行历史</h3>
        </div>
        <div class="max-h-[360px] overflow-y-auto">
          <button
            v-for="run in runs"
            :key="run.id"
            type="button"
            class="flex w-full items-start gap-3 border-b border-[#F1F4F9] px-4 py-2.5 text-left transition-colors last:border-b-0"
            :class="selectedRun?.id === run.id ? 'bg-[#F1F6FF]' : 'hover:bg-[#F9FBFE]'"
            @click="selectRun(run)"
          >
            <span
              class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
              :class="run.status === 'completed' ? 'bg-[#18A879]' : run.status === 'failed' ? 'bg-[#D65A4A]' : run.status === 'running' ? 'bg-[#2360E6]' : 'bg-[#E1A23C]'"
            ></span>
            <span class="min-w-0 flex-1">
              <span class="flex flex-wrap items-center gap-2">
                <span class="text-[11.5px] font-bold text-[#334867]">{{ formatRelativeDay(run.started_at) }}</span>
                <span class="inline-flex rounded-md border px-1.5 py-0.5 text-[9.5px] font-black" :class="runTone(run.status).chip">
                  {{ run.status_label }}
                </span>
              </span>
              <span class="mt-1 block truncate text-[10.5px] text-[#7C8BA1]">{{ statusText(run) }}</span>
            </span>
            <span class="mt-1 shrink-0 text-[10px] font-medium text-[#A1AEC0]">
              {{ formatDuration(run.duration_seconds) }}
            </span>
          </button>
        </div>
      </div>

      <div v-if="selectedRun" class="rounded-xl border" :class="detailTone.accent">
        <div class="flex items-start gap-2.5 border-b border-white/70 px-4 py-3">
          <component
            :is="detailTone.icon"
            class="mt-0.5 h-4 w-4 shrink-0"
            :class="[detailTone.title, selectedRun.status === 'running' ? 'animate-spin' : '']"
          />
          <div class="min-w-0">
            <h3 class="text-[13px] font-black" :class="detailTone.title">{{ detailTitle }}</h3>
            <p class="mt-1 text-[11px] leading-relaxed text-[#5F7089]">{{ detailDescription }}</p>
          </div>
        </div>

        <div class="grid grid-cols-3 gap-2 px-4 py-2.5">
          <div class="rounded-lg border border-[#E6ECF6] bg-white/80 px-2.5 py-2 text-center">
            <p class="text-[9.5px] font-bold text-[#8B9AB0]">已发现</p>
            <p class="mt-0.5 text-[17px] font-black text-[#2360E6]">{{ selectedRun.discovered_count ?? selectedRun.saved_count }}</p>
          </div>
          <div class="rounded-lg border border-[#E6ECF6] bg-white/80 px-2.5 py-2 text-center">
            <p class="text-[9.5px] font-bold text-[#8B9AB0]">已保存</p>
            <p class="mt-0.5 text-[17px] font-black text-[#16A071]">{{ selectedRun.saved_count }}</p>
          </div>
          <div class="rounded-lg border border-[#E6ECF6] bg-white/80 px-2.5 py-2 text-center">
            <p class="text-[9.5px] font-bold text-[#8B9AB0]">待分析</p>
            <p class="mt-0.5 text-[17px] font-black text-[#C08A33]">{{ selectedRun.pending_count ?? 0 }}</p>
          </div>
        </div>

        <div class="px-4 pb-3">
          <div v-if="selectedRun.timeline?.length" class="space-y-2">
            <div v-for="(line, index) in selectedRun.timeline.slice(-4)" :key="`${line.time}-${index}`" class="flex gap-2 text-[10.5px]">
              <span class="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-[#9FB4D2]"></span>
              <span class="w-[84px] shrink-0 text-[#7C8BA1]">{{ line.time.split(' ').pop() }}</span>
              <span class="min-w-0 flex-1 leading-relaxed text-[#52637B]">{{ line.text }}</span>
            </div>
          </div>
          <div v-else class="space-y-2 text-[10.5px] text-[#52637B]">
            <div class="flex gap-2">
              <span class="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-[#9FB4D2]"></span>
              <span class="w-[84px] shrink-0 text-[#7C8BA1]">开始</span>
              <span>{{ formatRelativeDay(selectedRun.started_at) }}</span>
            </div>
            <div class="flex gap-2">
              <span class="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-[#9FB4D2]"></span>
              <span class="w-[84px] shrink-0 text-[#7C8BA1]">结束</span>
              <span>{{ selectedRun.finished_at ? formatRelativeDay(selectedRun.finished_at) : '仍在进行' }}</span>
            </div>
          </div>
        </div>

        <div class="flex flex-wrap gap-2 border-t border-white/70 px-4 py-3">
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-md bg-[#2360E6] px-3 text-[10.5px] font-bold text-white transition-colors hover:bg-[#1B51C9]"
            @click="emit('view-results')"
          >
            <Search class="h-3.5 w-3.5" />
            查看已保存商品
          </button>
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-md border border-[#D9E2F0] bg-white px-3 text-[10.5px] font-bold text-[#52637B] transition-colors hover:border-[#B9C9E2] hover:text-[#2360E6]"
            @click="emit('full-log')"
          >
            <FileText class="h-3.5 w-3.5" />
            完整日志
          </button>
          <span class="ml-auto inline-flex items-center gap-1 text-[10px] text-[#8B9AB0]">
            <PlayCircle class="h-3 w-3" />
            {{ selectedRun.trigger === 'scheduled' ? '定时触发' : '手动触发' }}
            <ArrowRight class="h-3 w-3" />
          </span>
        </div>
      </div>
    </div>
  </section>
</template>
