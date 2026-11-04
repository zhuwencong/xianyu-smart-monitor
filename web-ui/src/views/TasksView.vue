<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowRight,
  ChevronRight,
  Clock3,
  FileClock,
  Loader2,
  Pause,
  Pencil,
  Play,
  Plus,
  Square,
  Trash2,
} from 'lucide-vue-next'
import {
  getTaskRuns,
  getWorkbenchTasks,
  type WorkbenchRun,
  type WorkbenchTask,
} from '@/api/workbench'
import { deleteTask, getAllTasks, startTask, stopTask, updateTask } from '@/api/tasks'
import type { Task, TaskUpdate } from '@/types/task.d.ts'
import { listAccounts, type AccountItem } from '@/api/accounts'
import TaskCreateDialog from '@/components/tasks/TaskCreateDialog.vue'
import TaskForm from '@/components/tasks/TaskForm.vue'
import TaskRunPanel from '@/components/tasks/TaskRunPanel.vue'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { toast } from '@/components/ui/toast'
import { useWorkbench } from '@/composables/useWorkbench'
import { useWebSocket } from '@/composables/useWebSocket'
import { formatRelativeDay } from '@/lib/format'

const route = useRoute()
const router = useRouter()
const { refreshSummary } = useWorkbench()
const { on } = useWebSocket()

const tasks = ref<WorkbenchTask[]>([])
const rawTasks = ref<Task[]>([])
const counts = ref<Record<string, number>>({ all: 0, running: 0, waiting: 0, cooldown: 0, paused: 0 })
const selectedTaskId = ref<number | null>(null)
const selectedRuns = ref<WorkbenchRun[]>([])
const isLoading = ref(true)
const error = ref<Error | null>(null)
const actionTaskId = ref<number | null>(null)
const filter = ref<'all' | 'running' | 'waiting' | 'cooldown' | 'paused'>('all')
const accountOptions = ref<AccountItem[]>([])

const isEditOpen = ref(false)
const editingTask = ref<Task | null>(null)
const isEditSubmitting = ref(false)
const isDeleteOpen = ref(false)
const deletingTask = ref<Task | null>(null)
const isAllRunsOpen = ref(false)

const selectedTask = computed(() => tasks.value.find((task) => task.id === selectedTaskId.value) || null)
const filteredTasks = computed(() =>
  filter.value === 'all' ? tasks.value : tasks.value.filter((task) => task.status === filter.value)
)
const filterTabs = computed(() => [
  { key: 'all' as const, label: '全部', count: counts.value.all || tasks.value.length },
  { key: 'running' as const, label: '运行中', count: counts.value.running || 0 },
  { key: 'waiting' as const, label: '等待中', count: counts.value.waiting || 0 },
  { key: 'cooldown' as const, label: '冷却中', count: counts.value.cooldown || 0 },
  { key: 'paused' as const, label: '已暂停', count: counts.value.paused || 0 },
])

function statusTone(status: string) {
  switch (status) {
    case 'running':
      return 'border-[#BFE8D7] bg-[#EAF8F2] text-[#0C7A56]'
    case 'cooldown':
      return 'border-[#F1D7A7] bg-[#FFF8EA] text-[#A56209]'
    case 'paused':
      return 'border-[#E0E5EE] bg-[#F5F7FA] text-[#64748B]'
    default:
      return 'border-[#DDE6F2] bg-[#F5F8FC] text-[#52637B]'
  }
}

function runTone(status?: string) {
  if (status === 'completed') return 'border-[#BFE8D7] bg-[#EAF8F2] text-[#0C7A56]'
  if (status === 'partial') return 'border-[#F1D7A7] bg-[#FFF8EA] text-[#A56209]'
  if (status === 'failed') return 'border-[#F1D3CE] bg-[#FFF4F2] text-[#B83B2D]'
  if (status === 'running') return 'border-[#C9DCF8] bg-[#F0F6FF] text-[#2360E6]'
  return 'border-[#E0E5EE] bg-[#F5F7FA] text-[#64748B]'
}

function latestRunLabel(task: WorkbenchTask) {
  const run = task.latest_run
  if (!run) return '暂无记录'
  if (run.status === 'completed') return `已完成 · 已保存 ${run.saved_count} 条`
  if (run.status === 'partial') return `部分完成 · 已保存 ${run.saved_count} 条`
  if (run.status === 'failed') return '异常退出'
  if (run.status === 'no_new') return '无新增'
  if (run.status === 'running') return '运行中'
  return run.status_label || '已结束'
}

async function loadTasks(silent = false) {
  if (!silent) isLoading.value = true
  error.value = null
  try {
    const data = await getWorkbenchTasks()
    tasks.value = data.items
    counts.value = data.counts as Record<string, number>
    const routeTaskId = typeof route.query.task === 'string' ? Number(route.query.task) : NaN
    if (Number.isFinite(routeTaskId) && data.items.some((task) => task.id === routeTaskId)) {
      selectedTaskId.value = routeTaskId
    } else if (!data.items.some((task) => task.id === selectedTaskId.value)) {
      const enabled = data.items.filter((task) => task.enabled)
      const preferred = enabled.find((task) => task.latest_run?.status === 'partial')
        || enabled.find((task) => task.latest_run?.status === 'failed')
        || enabled.find((task) => task.latest_run?.status === 'completed')
        || enabled[0]
        || data.items[0]
      selectedTaskId.value = preferred?.id ?? null
    }
    if (selectedTaskId.value) await loadRuns(selectedTaskId.value)
  } catch (e) {
    error.value = e instanceof Error ? e : new Error('加载监控任务失败')
  } finally {
    isLoading.value = false
  }
}

async function loadRuns(taskId: number) {
  try {
    const data = await getTaskRuns(taskId)
    if (selectedTaskId.value === taskId) {
      selectedRuns.value = data.runs
    }
  } catch {
    const fallback = tasks.value.find((task) => task.id === taskId)?.recent_runs || []
    selectedRuns.value = fallback
  }
}

async function loadRawTasks() {
  try {
    rawTasks.value = await getAllTasks()
  } catch {
    rawTasks.value = []
  }
}

async function loadAccounts() {
  try {
    accountOptions.value = await listAccounts()
  } catch {
    accountOptions.value = []
  }
}

function selectTask(task: WorkbenchTask) {
  if (selectedTaskId.value === task.id) return
  selectedTaskId.value = task.id
  selectedRuns.value = task.recent_runs || []
  loadRuns(task.id)
}

async function handleStart(task: WorkbenchTask) {
  actionTaskId.value = task.id
  try {
    await startTask(task.id)
    toast({ title: `已启动「${task.task_name}」` })
    setTimeout(() => loadTasks(true), 600)
  } catch (e) {
    toast({ title: '启动失败', description: (e as Error).message, variant: 'destructive' })
  } finally {
    actionTaskId.value = null
  }
}

async function handleStop(task: WorkbenchTask) {
  actionTaskId.value = task.id
  try {
    await stopTask(task.id)
    toast({ title: `正在停止「${task.task_name}」` })
    setTimeout(() => loadTasks(true), 600)
  } catch (e) {
    toast({ title: '停止失败', description: (e as Error).message, variant: 'destructive' })
  } finally {
    actionTaskId.value = null
  }
}

async function toggleEnabled(task: WorkbenchTask) {
  actionTaskId.value = task.id
  try {
    await updateTask(task.id, { enabled: !task.enabled })
    toast({ title: task.enabled ? `已暂停「${task.task_name}」` : `已启用「${task.task_name}」` })
    await loadTasks(true)
    refreshSummary()
  } catch (e) {
    toast({ title: '更新失败', description: (e as Error).message, variant: 'destructive' })
  } finally {
    actionTaskId.value = null
  }
}

function openEdit(task: WorkbenchTask) {
  const raw = rawTasks.value.find((item) => item.id === task.id) || null
  editingTask.value = raw
  isEditOpen.value = true
}

async function handleUpdateTask(data: TaskUpdate) {
  if (!editingTask.value) return
  isEditSubmitting.value = true
  try {
    await updateTask(editingTask.value.id, data)
    toast({ title: '任务已更新' })
    isEditOpen.value = false
    await Promise.all([loadTasks(true), loadRawTasks()])
    refreshSummary()
  } catch (e) {
    toast({ title: '更新失败', description: (e as Error).message, variant: 'destructive' })
  } finally {
    isEditSubmitting.value = false
  }
}

function openDelete(taskId: number) {
  deletingTask.value = rawTasks.value.find((item) => item.id === taskId) || null
  isDeleteOpen.value = true
}

async function handleDelete() {
  if (!deletingTask.value) return
  try {
    await deleteTask(deletingTask.value.id)
    toast({ title: '任务已删除' })
    isDeleteOpen.value = false
    deletingTask.value = null
    await loadTasks(true)
    refreshSummary()
  } catch (e) {
    toast({ title: '删除失败', description: (e as Error).message, variant: 'destructive' })
  }
}

async function handleCreated() {
  await Promise.all([loadTasks(true), loadRawTasks()])
  refreshSummary()
}

function openAllRuns() {
  isAllRunsOpen.value = true
}

function jumpToTask(taskId: number) {
  isAllRunsOpen.value = false
  const task = tasks.value.find((item) => item.id === taskId)
  if (!task) return
  selectedTaskId.value = taskId
  selectedRuns.value = task.recent_runs || []
  loadRuns(taskId)
}

function viewSavedResults() {
  if (!selectedTaskId.value) return
  router.push({ path: '/results', query: { task: String(selectedTaskId.value) } })
}

function viewFullLog() {
  if (!selectedTaskId.value) return
  router.push({ path: '/logs', query: { task: String(selectedTaskId.value) } })
}

function createMonitor() {
  router.push({ name: 'Tasks', query: { create: '1' } })
}

on('tasks_updated', () => loadTasks(true))
on('task_status_changed', () => loadTasks(true))
on('results_updated', () => loadTasks(true))

onMounted(async () => {
  await Promise.all([loadTasks(), loadRawTasks(), loadAccounts()])
})
</script>

<template>
  <div class="mx-auto max-w-[1540px]">
    <div class="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="text-[32px] font-black leading-tight tracking-tight text-[#102A56]">监控任务</h1>
        <p class="mt-1 text-[13.5px] text-[#74839A]">设置要找的商品，查看每次运行结果。</p>
      </div>
      <div class="flex items-center gap-2.5">
        <button
          type="button"
          class="inline-flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-[12px] font-bold text-[#40526C] transition-colors hover:bg-white hover:text-[#2360E6]"
          @click="openAllRuns"
        >
          全部运行记录
          <ArrowRight class="h-3.5 w-3.5" />
        </button>
        <TaskCreateDialog :account-options="accountOptions" @created="handleCreated">
          <template #trigger>
            <button
              type="button"
              class="inline-flex h-10 items-center gap-1.5 rounded-lg bg-[#2360E6] px-4 text-[13px] font-bold text-white shadow-[0_10px_22px_-14px_rgba(35,96,230,0.9)] transition-colors hover:bg-[#1B51C9]"
            >
              <Plus class="h-4 w-4" :stroke-width="2.5" />
              新建监控
            </button>
          </template>
        </TaskCreateDialog>
      </div>
    </div>

    <div v-if="error" class="app-alert-error mb-4" role="alert">{{ error.message }}</div>

    <div class="mb-4 flex flex-wrap items-center gap-1 rounded-xl border border-[#E7ECF5] bg-white px-2.5 py-2">
      <button
        v-for="tab in filterTabs"
        :key="tab.key"
        type="button"
        class="inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-[12.5px] font-bold transition-all"
        :class="filter === tab.key
          ? 'border border-[#C9DBF8] bg-[#F2F7FF] text-[#2360E6]'
          : 'border border-transparent text-[#66768D] hover:bg-[#F7F9FD] hover:text-[#2360E6]'"
        @click="filter = tab.key"
      >
        {{ tab.label }}
        <span
          class="inline-flex min-w-[18px] items-center justify-center rounded px-1 text-[10px] font-black leading-[17px]"
          :class="filter === tab.key ? 'bg-[#E2EDFF] text-[#2360E6]' : 'bg-[#EDF0F5] text-[#8492A6]'"
        >
          {{ tab.count }}
        </span>
      </button>
      <span class="ml-auto hidden items-center gap-1.5 pr-1 text-[10.5px] text-[#97A5B9] sm:flex">
        <Clock3 class="h-3.5 w-3.5" />
        任务运行在独立进程中，关闭页面不会中断
      </span>
    </div>

    <div class="overflow-hidden rounded-2xl border border-[#E4EAF4] bg-white shadow-[0_1px_2px_rgba(16,42,86,0.03)]">
      <div class="hidden grid-cols-[minmax(150px,1.05fr)_minmax(140px,0.95fr)_110px_minmax(180px,1.25fr)_110px_250px] items-center gap-3 border-b border-[#EBEFF7] bg-[#F8FAFD] px-4 py-2.5 text-[11.5px] font-black tracking-wide text-[#8492A6] lg:grid">
        <span>监控任务</span>
        <span>关键词与预算</span>
        <span>当前状态</span>
        <span>最近一轮</span>
        <span>下次运行</span>
        <span class="text-right">操作</span>
      </div>

      <div v-if="isLoading" class="space-y-0">
        <div v-for="index in 3" :key="index" class="flex items-center gap-4 border-b border-[#F1F4F9] px-4 py-5 last:border-b-0">
          <div class="h-9 w-9 animate-pulse rounded-lg bg-[#EDF1F8]"></div>
          <div class="h-4 w-36 animate-pulse rounded bg-[#EDF1F8]"></div>
          <div class="h-4 w-24 animate-pulse rounded bg-[#EDF1F8]"></div>
          <div class="ml-auto h-8 w-52 animate-pulse rounded bg-[#EDF1F8]"></div>
        </div>
      </div>

      <div v-else-if="!tasks.length" class="px-6 py-16 text-center">
        <span class="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[#EEF4FF] text-[#2360E6]">
          <FileClock class="h-7 w-7" :stroke-width="1.6" />
        </span>
        <h2 class="mt-4 text-[17px] font-black text-[#1D3557]">创建第一个监控</h2>
        <p class="mx-auto mt-1.5 max-w-sm text-[12.5px] leading-relaxed text-[#7B8AA3]">
          设定关键词、预算和运行时间，系统会按计划抓取并分析闲鱼商品。
        </p>
        <button
          type="button"
          class="mt-5 inline-flex h-9 items-center gap-1.5 rounded-lg bg-[#2360E6] px-4 text-[12px] font-bold text-white hover:bg-[#1B51C9]"
          @click="createMonitor"
        >
          <Plus class="h-4 w-4" /> 新建监控
        </button>
      </div>

      <div v-else-if="!filteredTasks.length" class="px-6 py-12 text-center text-[12.5px] text-[#8796AC]">
        这个状态下暂时没有任务。
      </div>

      <div v-else>
        <div
          v-for="task in filteredTasks"
          :key="task.id"
          class="group grid cursor-pointer grid-cols-1 items-center gap-3 border-b border-[#F0F3F8] px-4 py-3 transition-colors last:border-b-0 lg:grid-cols-[minmax(150px,1.05fr)_minmax(140px,0.95fr)_110px_minmax(180px,1.25fr)_110px_250px]"
          :class="selectedTaskId === task.id ? 'bg-[#F1F6FF]' : 'hover:bg-[#FAFCFF]'"
          @click="selectTask(task)"
        >
          <div class="flex min-w-0 items-center gap-2.5">
            <span
              class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border"
              :class="task.status === 'running' ? 'border-[#CBE9DD] bg-[#EEFBF5] text-[#0C7A56]' : 'border-[#E0E7F3] bg-[#F6F8FC] text-[#6F86A8]'"
            >
              <Play v-if="task.status === 'running'" class="h-3.5 w-3.5" />
              <FileClock v-else class="h-3.5 w-3.5" />
            </span>
            <div class="min-w-0">
              <p class="truncate text-[14px] font-black text-[#263B5C]">{{ task.task_name }}</p>
              <p class="mt-0.5 truncate text-[10.5px] text-[#8B9AB0]">{{ task.decision_mode === 'ai' ? 'AI 判断' : '关键词判断' }} · {{ task.account_strategy === 'fixed' ? '固定账号' : task.account_strategy === 'rotate' ? '轮换账号' : '自动账号' }}</p>
            </div>
          </div>

          <div class="min-w-0 text-[12px] text-[#52637B]">
            <p class="truncate font-bold text-[#40526C]">{{ task.keyword }}</p>
            <p class="mt-0.5 text-[10.5px] text-[#8B9AB0]">{{ task.budget }}</p>
          </div>

          <div>
            <span class="inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10.5px] font-black" :class="statusTone(task.status)">
              <span class="h-1.5 w-1.5 rounded-full" :class="task.status === 'running' ? 'bg-[#11A66E]' : task.status === 'cooldown' ? 'bg-[#E1A23C]' : 'bg-current opacity-50'"></span>
              {{ task.status_label }}
            </span>
            <p class="mt-1 text-[10px] text-[#8B9AB0]">{{ task.status_detail }}</p>
          </div>

          <div class="min-w-0">
            <span class="inline-flex max-w-full items-center gap-1.5 rounded-md border px-2 py-1 text-[10.5px] font-bold" :class="runTone(task.latest_run?.status)">
              <span class="truncate">{{ latestRunLabel(task) }}</span>
            </span>
            <p class="mt-1 truncate text-[10px] text-[#8B9AB0]">
              {{ task.latest_run ? formatRelativeDay(task.latest_run.started_at) : '点击运行一次试试' }}
            </p>
          </div>

          <div class="text-[11.5px] font-semibold text-[#52637B]">
            {{ task.next_run_label }}
          </div>

          <div class="flex items-center justify-end gap-1.5" @click.stop>
            <button
              v-if="!task.is_running"
              type="button"
              class="inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-md border border-[#DCE4F0] bg-white px-2 text-[10.5px] font-bold text-[#40526C] transition-colors hover:border-[#B9C9E2] hover:text-[#2360E6] disabled:opacity-50"
              :disabled="!task.enabled || actionTaskId === task.id"
              @click="handleStart(task)"
            >
              <Loader2 v-if="actionTaskId === task.id" class="h-3 w-3 animate-spin" />
              <Play v-else class="h-3 w-3" />
              运行
            </button>
            <button
              v-else
              type="button"
              class="inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-md border border-[#F0D3CE] bg-[#FFF8F6] px-2 text-[10.5px] font-bold text-[#B83B2D] hover:bg-[#FFF1ED]"
              :disabled="actionTaskId === task.id"
              @click="handleStop(task)"
            >
              <Square class="h-2.5 w-2.5 fill-current" />
              停止
            </button>
            <button
              type="button"
              class="inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-md border border-[#DCE4F0] bg-white px-2 text-[10.5px] font-bold text-[#52637B] transition-colors hover:border-[#B9C9E2] hover:text-[#2360E6]"
              :disabled="actionTaskId === task.id"
              @click="toggleEnabled(task)"
            >
              <Pause v-if="task.enabled" class="h-3 w-3" />
              <Play v-else class="h-3 w-3" />
              {{ task.enabled ? '暂停' : '启用' }}
            </button>
            <button
              type="button"
              class="inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-md border border-[#DCE4F0] bg-white px-2 text-[10.5px] font-bold text-[#52637B] transition-colors hover:border-[#B9C9E2] hover:text-[#2360E6]"
              @click="openEdit(task)"
            >
              <Pencil class="h-3 w-3" />
              编辑
            </button>
            <button
              type="button"
              class="inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-md px-1.5 text-[10.5px] font-bold text-[#7B8AA3] transition-colors hover:bg-white hover:text-[#2360E6]"
              @click="selectTask(task)"
            >
              记录
              <ChevronRight class="h-3 w-3" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="mt-4">
      <TaskRunPanel
        v-if="selectedTask"
        :task="selectedTask"
        :runs="selectedRuns"
        @close="selectedTaskId = null"
        @view-results="viewSavedResults"
        @full-log="viewFullLog"
      />
    </div>

    <Dialog v-model:open="isEditOpen">
      <DialogContent class="max-h-[88vh] overflow-y-auto sm:max-w-[680px]">
        <DialogHeader>
          <DialogTitle>编辑「{{ editingTask?.task_name || '' }}」</DialogTitle>
          <DialogDescription>修改关键词、预算、运行时间与判断方式。</DialogDescription>
        </DialogHeader>
        <TaskForm
          v-if="editingTask"
          mode="edit"
          :initial-data="editingTask"
          :account-options="accountOptions"
          @submit="(data) => handleUpdateTask(data as TaskUpdate)"
        />
        <DialogFooter class="flex items-center justify-between gap-2">
          <button
            type="button"
            class="inline-flex h-9 items-center gap-1.5 rounded-md px-2 text-[11.5px] font-bold text-[#B83B2D] hover:bg-[#FFF3F0]"
            @click="isEditOpen = false; editingTask && openDelete(editingTask.id)"
          >
            <Trash2 class="h-3.5 w-3.5" /> 删除任务
          </button>
          <div class="flex items-center gap-2">
            <button type="button" class="h-9 rounded-md border border-[#DCE4F0] bg-white px-4 text-[12px] font-bold text-[#52637B]" @click="isEditOpen = false">取消</button>
            <button type="submit" form="task-form" class="h-9 rounded-md bg-[#2360E6] px-5 text-[12px] font-bold text-white disabled:opacity-60" :disabled="isEditSubmitting">
              {{ isEditSubmitting ? '保存中…' : '保存修改' }}
            </button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="isDeleteOpen">
      <DialogContent class="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>删除监控任务</DialogTitle>
          <DialogDescription>
            确认删除「{{ deletingTask?.task_name || '' }}」？任务配置和运行日志会被移除，关联的监控结果也可能一并清理，删除后不可恢复。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <button type="button" class="h-9 rounded-md border border-[#DCE4F0] bg-white px-4 text-[12px] font-bold text-[#52637B]" @click="isDeleteOpen = false">取消</button>
          <button type="button" class="h-9 rounded-md bg-[#C43D2D] px-4 text-[12px] font-bold text-white" @click="handleDelete">确认删除</button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="isAllRunsOpen">
      <DialogContent class="max-h-[82vh] overflow-y-auto sm:max-w-[720px]">
        <DialogHeader>
          <DialogTitle>全部运行记录</DialogTitle>
          <DialogDescription>按任务集中排查最近几次运行结果。</DialogDescription>
        </DialogHeader>
        <div class="space-y-3">
          <div v-for="task in tasks" :key="task.id" class="rounded-xl border border-[#E7ECF5] bg-[#FBFCFE] p-3">
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2">
                <span class="h-2 w-2 rounded-full" :class="task.status === 'running' ? 'bg-[#11A66E]' : task.status === 'cooldown' ? 'bg-[#E1A23C]' : 'bg-[#B9C5D7]'"></span>
                <p class="text-[12.5px] font-black text-[#334867]">{{ task.task_name }}</p>
              </div>
              <button type="button" class="text-[10.5px] font-bold text-[#2360E6]" @click="jumpToTask(task.id)">查看任务 →</button>
            </div>
            <div v-if="task.recent_runs.length" class="mt-2 space-y-1">
              <button
                v-for="run in task.recent_runs.slice(0, 3)"
                :key="run.id"
                type="button"
                class="flex w-full items-center gap-2 rounded-md px-1.5 py-1.5 text-left hover:bg-white"
                @click="jumpToTask(task.id)"
              >
                <span class="w-[94px] shrink-0 text-[10.5px] text-[#7C8BA1]">{{ formatRelativeDay(run.started_at) }}</span>
                <span class="rounded border px-1.5 py-0.5 text-[9.5px] font-bold" :class="runTone(run.status)">{{ run.status_label }}</span>
                <span class="truncate text-[10.5px] text-[#7C8BA1]">{{ run.summary }}</span>
              </button>
            </div>
            <p v-else class="mt-2 text-[10.5px] text-[#98A5B9]">暂无运行记录</p>
          </div>
        </div>
        <DialogFooter>
          <button type="button" class="h-9 rounded-md border border-[#DCE4F0] bg-white px-4 text-[12px] font-bold text-[#52637B]" @click="isAllRunsOpen = false">关闭</button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
