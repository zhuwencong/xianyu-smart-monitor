<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  ClipboardList,
  Loader2,
  Plus,
  ScanLine,
  Search,
  Sparkles,
  TrendingUp,
  UserPlus,
  X,
} from 'lucide-vue-next'
import { getCandidates, updateCandidateReview, type Candidate, type CandidateResponse, type ReviewStatus, type AiVerdict } from '@/api/workbench'
import { getAllTasks } from '@/api/tasks'
import { launchAccountLogin } from '@/api/accounts'
import type { Task } from '@/types/task.d.ts'
import CandidateCard from '@/components/candidates/CandidateCard.vue'
import CandidateDetailDialog from '@/components/candidates/CandidateDetailDialog.vue'
import { useWorkbench } from '@/composables/useWorkbench'
import { useWebSocket } from '@/composables/useWebSocket'
import { toast } from '@/components/ui/toast'
import { formatNumber } from '@/lib/format'

const route = useRoute()
const router = useRouter()
const { summary, refreshSummary } = useWorkbench()
const { on } = useWebSocket()

const tasks = ref<Task[]>([])
const tasksLoaded = ref(false)
const items = ref<Candidate[]>([])
const counts = ref<Record<ReviewStatus, number>>({ unseen: 0, favorite: 0, handled: 0 })
const aiCounts = ref<Record<'all' | AiVerdict, number>>({ all: 0, recommend: 0, verify: 0, mismatch: 0, failed: 0 })
const total = ref(0)
const page = ref(1)
const isLoading = ref(true)
const isLoadingMore = ref(false)
const error = ref<Error | null>(null)

const reviewTab = ref<ReviewStatus>('unseen')
const aiFilter = ref<'all' | AiVerdict>('all')
const taskFilter = ref('all')
const sortBy = ref<'score' | 'newest' | 'price_asc' | 'price_desc'>('score')
const searchText = ref('')
const appliedSearch = ref('')
const selected = ref<Candidate | null>(null)
const isDetailOpen = ref(false)
const updatingItemId = ref('')
const isLaunchingLogin = ref(false)

let searchTimer: ReturnType<typeof setTimeout> | null = null
let loadToken = 0

const tabs = computed(() => [
  { key: 'unseen' as ReviewStatus, label: '未查看', count: counts.value.unseen },
  { key: 'favorite' as ReviewStatus, label: '已收藏', count: counts.value.favorite },
  { key: 'handled' as ReviewStatus, label: '已处理', count: counts.value.handled },
])

const aiOptions = computed(() => [
  { value: 'all', label: '全部 AI 判断' },
  { value: 'recommend', label: `建议关注 ${aiCounts.value.recommend}` },
  { value: 'verify', label: `需核实 ${aiCounts.value.verify}` },
  { value: 'mismatch', label: `不匹配 ${aiCounts.value.mismatch}` },
  { value: 'failed', label: `AI 分析失败 ${aiCounts.value.failed}` },
])

const hasMore = computed(() => items.value.length < total.value)
const activeTask = computed(() => tasks.value.find((task) => String(task.id) === taskFilter.value) || null)
const accountAlerts = computed(() =>
  (summary.value?.accounts || []).filter((account) => account.status === 'needs_update')
)
const accountAlertText = computed(() => {
  const names = accountAlerts.value
    .slice(0, 3)
    .map((account) => `${account.name}${account.last_failure_label ? `（${account.last_failure_label}）` : ''}`)
    .join('、')
  const extra = accountAlerts.value.length > 3 ? ` 等 ${accountAlerts.value.length} 个` : ''
  return `${names}${extra}`
})
const selectedTaskCount = computed(() => {
  if (taskFilter.value === 'all') return total.value
  return total.value
})

const showFirstRun = computed(() => !isLoading.value && tasksLoaded.value && tasks.value.length === 0)
const hasFilters = computed(() => reviewTab.value !== 'unseen' || aiFilter.value !== 'all' || taskFilter.value !== 'all' || appliedSearch.value)

function readAiFromRoute() {
  const ai = typeof route.query.ai === 'string' ? route.query.ai : ''
  if (['recommend', 'verify', 'mismatch', 'failed'].includes(ai)) {
    aiFilter.value = ai as AiVerdict
  }
  if (typeof route.query.task === 'string') {
    taskFilter.value = route.query.task
  } else {
    taskFilter.value = 'all'
  }
}

async function fetchTasks() {
  try {
    tasks.value = await getAllTasks()
  } catch {
    tasks.value = []
  } finally {
    tasksLoaded.value = true
  }
}

async function loadCandidates(reset = true) {
  if (reset) {
    page.value = 1
    isLoading.value = true
  } else {
    isLoadingMore.value = true
  }
  error.value = null
  const token = ++loadToken
  try {
    const data: CandidateResponse = await getCandidates({
      review_status: reviewTab.value,
      ai_verdict: aiFilter.value,
      task_id: taskFilter.value === 'all' ? undefined : Number(taskFilter.value),
      q: appliedSearch.value,
      sort: sortBy.value,
      page: page.value,
      limit: 12,
    })
    if (token !== loadToken) return
    counts.value = data.counts
    aiCounts.value = data.ai_counts
    total.value = data.total
    items.value = reset ? data.items : [...items.value, ...data.items]
  } catch (e) {
    if (token !== loadToken) return
    error.value = e instanceof Error ? e : new Error('加载候选商品失败')
    if (reset) items.value = []
  } finally {
    if (token === loadToken) {
      isLoading.value = false
      isLoadingMore.value = false
    }
  }
}

function changeTab(tab: ReviewStatus) {
  if (reviewTab.value === tab) return
  reviewTab.value = tab
  loadCandidates(true)
}

function changeAiFilter(value: string) {
  aiFilter.value = value as 'all' | AiVerdict
  loadCandidates(true)
}

function changeTaskFilter(value: string) {
  taskFilter.value = value
  loadCandidates(true)
}

function changeSort(value: string) {
  sortBy.value = value as typeof sortBy.value
  loadCandidates(true)
}

function clearSearch() {
  searchText.value = ''
  appliedSearch.value = ''
  loadCandidates(true)
}

function clearFilters() {
  reviewTab.value = 'unseen'
  aiFilter.value = 'all'
  taskFilter.value = 'all'
  searchText.value = ''
  appliedSearch.value = ''
  loadCandidates(true)
}

function loadMore() {
  if (!hasMore.value || isLoadingMore.value) return
  page.value += 1
  loadCandidates(false)
}

function openDetail(candidate: Candidate) {
  selected.value = candidate
  isDetailOpen.value = true
}

function applyLocalUpdate(candidate: Candidate, status: ReviewStatus) {
  const previous = candidate.review_status
  if (previous === status) return
  counts.value = {
    ...counts.value,
    [previous]: Math.max(0, counts.value[previous] - 1),
    [status]: counts.value[status] + 1,
  }
  candidate.review_status = status
  candidate.review_label = status === 'favorite' ? '已收藏' : status === 'handled' ? '已处理' : '未查看'
  if (selected.value?.item_id === candidate.item_id) {
    selected.value = { ...candidate }
  }
  if (status !== reviewTab.value) {
    items.value = items.value.filter((item) => item.item_id !== candidate.item_id)
    total.value = Math.max(0, total.value - 1)
  }
}

async function setReview(candidate: Candidate, status: ReviewStatus, message?: string) {
  if (updatingItemId.value === candidate.item_id) return
  updatingItemId.value = candidate.item_id
  try {
    await updateCandidateReview(candidate.item_id, status)
    applyLocalUpdate(candidate, status)
    if (message) toast({ title: message })
    refreshSummary()
  } catch (e) {
    toast({
      title: '状态更新失败',
      description: (e as Error).message,
      variant: 'destructive',
    })
  } finally {
    updatingItemId.value = ''
  }
}

function toggleFavorite(candidate: Candidate) {
  const next: ReviewStatus = candidate.review_status === 'favorite' ? 'unseen' : 'favorite'
  setReview(candidate, next, next === 'favorite' ? '已收藏' : '已取消收藏')
}

function markHandled(candidate: Candidate) {
  const next: ReviewStatus = candidate.review_status === 'handled' ? 'unseen' : 'handled'
  setReview(candidate, next, next === 'handled' ? '已标记为已处理' : '已移回未查看')
}

function ignoreCandidate(candidate: Candidate) {
  setReview(candidate, 'handled', '已忽略')
  if (selected.value?.item_id === candidate.item_id) {
    isDetailOpen.value = false
  }
}

function goTasks() {
  router.push('/tasks')
}

async function goScanLogin() {
  if (isLaunchingLogin.value) return
  isLaunchingLogin.value = true
  try {
    const result = await launchAccountLogin()
    toast({
      title: `已打开 ${result.account} 扫码窗口`,
      description: '请用对应账号的手机扫码，成功后回到本页刷新账号状态。',
    })
  } catch (e) {
    toast({
      title: '无法启动扫码登录',
      description: (e as Error).message,
      variant: 'destructive',
    })
    router.push({ name: 'Accounts', query: { action: 'scan' } })
  } finally {
    isLaunchingLogin.value = false
  }
}

function goCreateAccount() {
  router.push({ name: 'Accounts', query: { create: '1' } })
}

function createMonitor() {
  router.push({ name: 'Tasks', query: { create: '1' } })
}

on('results_updated', () => {
  if (updatingItemId.value) return
  loadCandidates(true)
  refreshSummary()
})

onMounted(() => {
  readAiFromRoute()
  fetchTasks()
  loadCandidates(true)
  refreshSummary()
})

watch(searchText, (value) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    appliedSearch.value = value.trim()
    loadCandidates(true)
  }, 260)
})

watch(
  () => [route.query.ai, route.query.task],
  () => {
    readAiFromRoute()
    loadCandidates(true)
  }
)

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<template>
  <div class="mx-auto max-w-[1540px]">
    <section class="mb-5 flex min-h-[52px] flex-wrap items-center gap-y-2 rounded-xl border border-[#E2EAF7] bg-[#EEF4FD]/80 px-4 py-2.5 sm:px-5">
      <div class="flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px] font-semibold text-[#3E4F69]">
        <span class="inline-flex items-center gap-2">
          <ClipboardList class="h-4 w-4 text-[#2360E6]" :stroke-width="2" />
          <b class="font-black text-[#1D3557]">{{ summary?.task_count ?? tasks.length }}</b> 个监控任务
        </span>
        <span class="hidden h-3.5 w-px bg-[#CBD8EB] sm:block"></span>
        <span class="inline-flex items-center gap-2">
          <span class="relative flex h-3.5 w-3.5 items-center justify-center">
            <span class="absolute h-3.5 w-3.5 rounded-full" :class="(summary?.running_count ?? 0) > 0 ? 'bg-[#18B47B]/15' : 'bg-[#94A3B8]/10'"></span>
            <span class="h-1.5 w-1.5 rounded-full" :class="(summary?.running_count ?? 0) > 0 ? 'bg-[#11A66E]' : 'bg-[#94A3B8]'"></span>
          </span>
          <b class="font-black text-[#1D3557]">{{ summary?.running_count ?? 0 }}</b> 个运行中
        </span>
        <span class="hidden h-3.5 w-px bg-[#CBD8EB] sm:block"></span>
        <span class="inline-flex items-center gap-2">
          <TrendingUp class="h-4 w-4 text-[#2360E6]" :stroke-width="2" />
          今日发现 <b class="font-black text-[#1D3557]">{{ formatNumber(summary?.today_count ?? 0) }}</b> 条
        </span>
      </div>
      <button
        type="button"
        class="ml-auto inline-flex items-center gap-1 text-[12px] font-bold text-[#2360E6] transition-colors hover:text-[#1748B8]"
        @click="goTasks"
      >
        查看运行情况
        <ArrowRight class="h-3.5 w-3.5" />
      </button>
    </section>

    <section
      v-if="accountAlerts.length"
      class="mb-5 flex flex-col gap-3 rounded-xl border border-[#F0D3A2] bg-[#FFF8EC] px-4 py-3.5 sm:flex-row sm:items-center"
      role="alert"
    >
      <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#FBE7C7] text-[#B56B0B]">
        <AlertTriangle class="h-[18px] w-[18px]" :stroke-width="2.3" />
      </span>
      <div class="min-w-0 flex-1">
        <p class="text-[13px] font-black text-[#8A4E08]">
          闲鱼账号登录失效
          <span class="ml-1 rounded bg-[#F7D9A8] px-1.5 py-0.5 text-[10px] font-black text-[#8A4E08]">{{ accountAlerts.length }}</span>
        </p>
        <p class="mt-0.5 text-[11.5px] leading-relaxed text-[#9A6A2B]">
          {{ accountAlertText }}。失效期间相关监控任务可能无法继续抓取，请尽快重新扫码。
        </p>
      </div>
      <div class="flex shrink-0 flex-wrap items-center gap-2">
        <button
          type="button"
          class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[#B56B0B] px-3.5 text-[12px] font-bold text-white transition-colors hover:bg-[#975707] disabled:cursor-wait disabled:opacity-70"
          :disabled="isLaunchingLogin"
          @click="goScanLogin"
        >
          <Loader2 v-if="isLaunchingLogin" class="h-4 w-4 animate-spin" />
          <ScanLine v-else class="h-4 w-4" />
          {{ isLaunchingLogin ? '正在打开…' : '重新扫码登录' }}
        </button>
        <button
          type="button"
          class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[#E4BF86] bg-white/80 px-3.5 text-[12px] font-bold text-[#8A4E08] transition-colors hover:bg-white"
          @click="goCreateAccount"
        >
          <UserPlus class="h-4 w-4" />
          添加新账号
        </button>
      </div>
    </section>

    <div class="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="text-[32px] font-black leading-tight tracking-tight text-[#102A56]">候选商品</h1>
        <p class="mt-1 text-[13.5px] text-[#74839A]">先看新增，再核实，最后决定是否保留。</p>
      </div>
      <button
        type="button"
        class="inline-flex h-10 items-center gap-1.5 rounded-lg bg-[#2360E6] px-4 text-[13px] font-bold text-white shadow-[0_10px_22px_-14px_rgba(35,96,230,0.9)] transition-colors hover:bg-[#1B51C9]"
        @click="createMonitor"
      >
        <Plus class="h-4 w-4" :stroke-width="2.5" />
        新建监控
      </button>
    </div>

    <div v-if="error" class="app-alert-error mb-4" role="alert">{{ error.message }}</div>

    <div class="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-[#E7ECF5] bg-white px-3 py-2.5 shadow-[0_1px_2px_rgba(16,42,86,0.02)]">
      <div class="flex items-center rounded-lg bg-[#F4F7FC] p-1">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-[13px] font-bold transition-all"
          :class="reviewTab === tab.key
            ? 'border border-[#C9DBF8] bg-white text-[#2360E6] shadow-sm'
            : 'border border-transparent text-[#66768D] hover:text-[#2360E6]'"
          @click="changeTab(tab.key)"
        >
          {{ tab.label }}
          <span
            class="inline-flex min-w-[19px] items-center justify-center rounded px-1 text-[10.5px] font-black leading-[18px]"
            :class="reviewTab === tab.key ? 'bg-[#E7F0FF] text-[#2360E6]' : 'bg-[#E9EDF4] text-[#8492A6]'"
          >
            {{ tab.count }}
          </span>
        </button>
      </div>

      <span class="hidden h-5 w-px bg-[#E5EAF3] md:block"></span>

      <div class="relative min-w-[148px]">
        <select
          :value="aiFilter"
          class="h-9 w-full appearance-none rounded-lg border border-[#DCE4F0] bg-white pl-8 pr-7 text-[12.5px] font-bold text-[#40526C] outline-none transition-colors hover:border-[#B9C9E2] focus:border-[#2360E6]"
          aria-label="AI 判断筛选"
          @change="changeAiFilter(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="option in aiOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
        <Sparkles class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#2360E6]" />
        <ChevronDown class="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#8291A8]" />
      </div>

      <div class="relative min-w-[132px]">
        <select
          :value="taskFilter"
          class="h-9 w-full appearance-none rounded-lg border border-[#DCE4F0] bg-white pl-3 pr-7 text-[12.5px] font-bold text-[#40526C] outline-none transition-colors hover:border-[#B9C9E2] focus:border-[#2360E6]"
          aria-label="任务筛选"
          @change="changeTaskFilter(($event.target as HTMLSelectElement).value)"
        >
          <option value="all">全部任务</option>
          <option v-for="task in tasks" :key="task.id" :value="String(task.id)">{{ task.task_name }}</option>
        </select>
        <ChevronDown class="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#8291A8]" />
      </div>

      <div class="relative min-w-[128px]">
        <select
          :value="sortBy"
          class="h-9 w-full appearance-none rounded-lg border border-[#DCE4F0] bg-white pl-3 pr-7 text-[12.5px] font-bold text-[#40526C] outline-none transition-colors hover:border-[#B9C9E2] focus:border-[#2360E6]"
          aria-label="排序方式"
          @change="changeSort(($event.target as HTMLSelectElement).value)"
        >
          <option value="score">按综合评分</option>
          <option value="newest">最新发现</option>
          <option value="price_asc">价格从低到高</option>
          <option value="price_desc">价格从高到低</option>
        </select>
        <ChevronDown class="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#8291A8]" />
      </div>

      <div class="relative ml-auto w-full sm:w-[210px]">
        <Search class="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#93A1B5]" />
        <input
          v-model="searchText"
          type="search"
          placeholder="搜索商品或卖家"
          class="h-9 w-full rounded-lg border border-[#DCE4F0] bg-white pl-8 pr-8 text-[12.5px] text-[#334155] outline-none transition-colors placeholder:text-[#A3AFC1] hover:border-[#B9C9E2] focus:border-[#2360E6]"
        />
        <button
          v-if="searchText"
          type="button"
          class="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-[#93A1B5] hover:text-[#40526C]"
          aria-label="清空搜索"
          @click="clearSearch"
        >
          <X class="h-3.5 w-3.5" />
        </button>
      </div>
    </div>

    <div v-if="isLoading" class="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3" aria-busy="true">
      <div v-for="index in 6" :key="index" class="overflow-hidden rounded-[14px] border border-[#E7ECF5] bg-white">
        <div class="aspect-[2.35/1] animate-pulse bg-[#EDF1F8]"></div>
        <div class="space-y-3 p-4">
          <div class="flex gap-3">
            <div class="h-5 flex-1 animate-pulse rounded bg-[#EDF1F8]"></div>
            <div class="h-5 w-16 animate-pulse rounded bg-[#EDF1F8]"></div>
          </div>
          <div class="h-6 w-24 animate-pulse rounded bg-[#EDF1F8]"></div>
          <div class="h-4 w-full animate-pulse rounded bg-[#EDF1F8]"></div>
          <div class="h-4 w-4/5 animate-pulse rounded bg-[#EDF1F8]"></div>
          <div class="flex justify-between pt-2">
            <div class="h-4 w-28 animate-pulse rounded bg-[#EDF1F8]"></div>
            <div class="h-8 w-40 animate-pulse rounded bg-[#EDF1F8]"></div>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="showFirstRun" class="rounded-2xl border border-dashed border-[#CFDBEC] bg-white/70 px-6 py-16 text-center">
      <span class="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[#EEF4FF] text-[#2360E6]">
        <ClipboardList class="h-7 w-7" :stroke-width="1.6" />
      </span>
      <h2 class="mt-4 text-[17px] font-black text-[#1D3557]">创建第一个监控</h2>
      <p class="mx-auto mt-1.5 max-w-sm text-[12.5px] leading-relaxed text-[#7B8AA3]">
        设置要找的商品、预算和运行时间，系统会把新发现的候选商品放到这里。
      </p>
      <button
        type="button"
        class="mt-5 inline-flex h-9 items-center gap-1.5 rounded-lg bg-[#2360E6] px-4 text-[12px] font-bold text-white hover:bg-[#1B51C9]"
        @click="createMonitor"
      >
        <Plus class="h-4 w-4" /> 新建监控
      </button>
    </div>

    <div v-else-if="items.length === 0" class="rounded-2xl border border-dashed border-[#CFDBEC] bg-white/70 px-6 py-14 text-center">
      <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-[#F2F6FC] text-[#8297B5]">
        <Search class="h-6 w-6" :stroke-width="1.7" />
      </span>
      <h2 class="mt-4 text-[16px] font-black text-[#1D3557]">{{ hasFilters ? '没有符合条件的候选商品' : '暂无新的候选商品' }}</h2>
      <p class="mx-auto mt-1.5 max-w-md text-[12.5px] leading-relaxed text-[#7B8AA3]">
        {{ hasFilters
          ? '换一个筛选条件，或清空搜索后再看看。'
          : `监控任务会按计划继续检查${activeTask ? `「${activeTask.task_name}」` : ''}，下一轮发现后会出现在这里。` }}
      </p>
      <button
        v-if="hasFilters"
        type="button"
        class="mt-5 inline-flex h-9 items-center rounded-lg border border-[#DCE4F0] bg-white px-4 text-[12px] font-bold text-[#40526C] hover:border-[#B9C9E2]"
        @click="clearFilters"
      >
        清空筛选
      </button>
    </div>

    <template v-else>
      <div class="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
        <CandidateCard
          v-for="candidate in items"
          :key="candidate.item_id"
          :candidate="candidate"
          @open="openDetail(candidate)"
          @favorite="toggleFavorite(candidate)"
          @handle="markHandled(candidate)"
          @ignore="ignoreCandidate(candidate)"
        />
      </div>

      <div class="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#E7ECF5] bg-white px-4 py-3">
        <p class="text-[11.5px] text-[#8492A6]">
          已显示 <b class="text-[#40526C]">{{ items.length }}</b> / {{ total }} 条
          <span v-if="activeTask" class="ml-1">· {{ activeTask.task_name }}</span>
          <span v-else-if="selectedTaskCount">· 全部任务</span>
        </p>
        <button
          v-if="hasMore"
          type="button"
          class="inline-flex h-8 items-center gap-1.5 rounded-md border border-[#DCE4F0] bg-white px-3 text-[11.5px] font-bold text-[#40526C] transition-colors hover:border-[#B9C9E2] hover:text-[#2360E6] disabled:opacity-60"
          :disabled="isLoadingMore"
          @click="loadMore"
        >
          <Loader2 v-if="isLoadingMore" class="h-3.5 w-3.5 animate-spin" />
          加载更多
        </button>
        <span v-else class="text-[11px] text-[#A0ADBE]">已经到底了</span>
      </div>
    </template>

    <CandidateDetailDialog
      v-model:open="isDetailOpen"
      :candidate="selected"
      @favorite="selected && toggleFavorite(selected)"
      @handle="selected && markHandled(selected)"
      @ignore="selected && ignoreCandidate(selected)"
    />
  </div>
</template>
