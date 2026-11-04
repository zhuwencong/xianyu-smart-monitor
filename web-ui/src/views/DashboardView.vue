<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useDashboard } from '@/composables/useDashboard'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import Badge from '@/components/ui/badge/Badge.vue'
import PriceTrendChart from '@/components/results/PriceTrendChart.vue'
import BrandBanner from '@/components/layout/BrandBanner.vue'
import { formatNumber, formatRelativeTimeFromNow } from '@/i18n'
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Compass,
  LayoutDashboard,
  Plus,
  Search,
  Sparkles,
  Target,
  Zap,
} from 'lucide-vue-next'

const router = useRouter()
const { t } = useI18n()
const {
  focusInsights,
  focusTask,
  suggestion,
  stats,
  activities,
  isLoading,
  error,
} = useDashboard()

const statCards = computed(() => [
  {
    label: t('dashboard.stats.activeTasks'),
    value: String(stats.value.enabledTasks),
    detail: t('dashboard.stats.runningCount', { count: stats.value.runningTasks }),
    icon: Activity,
    color: 'text-blue-500',
    bg: 'bg-blue-500/10',
  },
  {
    label: t('dashboard.stats.scannedItems'),
    value: formatNumber(stats.value.scannedItems),
    detail: t('dashboard.stats.resultFiles', { count: stats.value.resultFiles }),
    icon: Search,
    color: 'text-emerald-500',
    bg: 'bg-emerald-500/10',
  },
  {
    label: t('dashboard.stats.recommendedItems'),
    value: String(stats.value.recommendedItems),
    detail: t('dashboard.stats.recommendedBreakdown', {
      ai: stats.value.aiRecommendedItems,
      keyword: stats.value.keywordRecommendedItems,
    }),
    icon: Target,
    color: 'text-amber-500',
    bg: 'bg-amber-500/10',
  },
  {
    label: t('dashboard.stats.monitoredTasks'),
    value: String(stats.value.totalTasks),
    detail: t('dashboard.stats.showAllTasks'),
    icon: Compass,
    color: 'text-purple-500',
    bg: 'bg-purple-500/10',
  },
])

const focusTitle = computed(() => focusTask.value?.task_name || t('dashboard.focus.defaultTitle'))
const focusMeta = computed(() => {
  if (!focusTask.value) return t('dashboard.focus.empty')
  const keyword = focusTask.value.keyword || t('dashboard.focus.missingKeyword')
  const count = focusTask.value.total_items
  return t('dashboard.focus.meta', { keyword, count })
})

const insightCards = computed(() => {
  const market = focusInsights.value?.market_summary
  const history = focusInsights.value?.history_summary
  return [
    {
      label: t('results.insights.currentAvg'),
      value: market?.avg_price ? `¥${market.avg_price}` : '—',
      hint: market
        ? t('results.insights.sampleCount', { count: market.sample_count })
        : t('results.grid.empty'),
    },
    {
      label: t('results.insights.historyAvg'),
      value: history?.avg_price ? `¥${history.avg_price}` : '—',
      hint: history
        ? t('results.insights.uniqueItems', { count: history.unique_items })
        : t('results.insights.noSnapshot'),
    },
    {
      label: t('results.card.marketAvg'),
      value: market?.min_price ? `¥${market.min_price}` : '—',
      hint: market?.max_price
        ? t('results.insights.highestPrice', { price: market.max_price })
        : t('results.insights.noRange'),
    },
  ]
})

function goCreateTask() {
  router.push({
    name: 'Tasks',
    query: { create: '1' },
  })
}

function openSuggestion() {
  router.push({
    name: suggestion.value.routeName,
    query: suggestion.value.query,
  })
}

function openActivity(activity: { filename: string | null; type: string }) {
  if (activity.filename) {
    router.push({ name: 'Results', query: { file: activity.filename } })
    return
  }
  if (activity.type === 'task') {
    router.push({ name: 'Tasks' })
    return
  }
  router.push({ name: 'Dashboard' })
}
</script>

<template>
  <div class="space-y-6 animate-fade-in">
    <BrandBanner>
      <Button size="lg" class="rounded-xl px-5 font-bold shadow-[0_12px_30px_-12px_rgba(18,95,224,0.8)]" @click="goCreateTask">
        <Plus class="mr-1 h-4 w-4" />
        {{ t('dashboard.createTask') }}
      </Button>
      <Button
        size="lg"
        variant="outline"
        class="rounded-xl border-blue-200 bg-white/85 px-5 font-bold text-blue-700 backdrop-blur hover:bg-white hover:text-blue-800"
        @click="router.push({ name: 'Results' })"
      >
        {{ t('dashboard.viewResults') }}
        <ArrowUpRight class="ml-1 h-4 w-4" />
      </Button>
    </BrandBanner>

    <div v-if="error" class="app-alert-error" role="alert">
      {{ error.message }}
    </div>

    <section aria-label="dashboard statistics" class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Card
        v-for="stat in statCards"
        :key="stat.label"
        class="app-surface group transition-all duration-200 hover:-translate-y-1 hover:border-blue-200 hover:shadow-[0_22px_45px_-30px_rgba(30,64,175,0.55)]"
      >
        <CardContent class="p-5">
          <div class="flex items-start justify-between gap-4">
            <div>
              <p class="text-xs font-bold text-slate-500">{{ stat.label }}</p>
              <h3 class="mt-2 text-3xl font-black tracking-tight text-[#102a56]">{{ stat.value }}</h3>
            </div>
            <div :class="[stat.bg, 'rounded-xl p-3 transition-transform group-hover:scale-105']">
              <component :is="stat.icon" :class="['h-5 w-5', stat.color]" />
            </div>
          </div>
          <div class="mt-5 border-t border-slate-100 pt-3 text-xs font-medium text-slate-500">
            {{ stat.detail }}
          </div>
        </CardContent>
      </Card>
    </section>
    <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <Card class="app-surface lg:col-span-2">
        <CardHeader class="flex flex-col gap-4 border-b border-slate-100 pb-5 md:flex-row md:items-start md:justify-between">
          <div class="flex items-start gap-3">
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-primary">
              <LayoutDashboard class="h-5 w-5" />
            </span>
            <div class="space-y-1.5">
              <CardTitle class="text-lg font-extrabold text-[#102a56]">
                {{ focusTitle }}
              </CardTitle>
              <p class="text-sm text-slate-500">{{ focusMeta }}</p>
            </div>
          </div>
          <Badge variant="secondary" class="w-fit bg-blue-100 text-blue-600">
            {{ focusTask?.latest_crawl_time ? t('dashboard.focus.latestUpdate', { time: formatRelativeTimeFromNow(focusTask.latest_crawl_time) }) : t('dashboard.focus.waiting') }}
          </Badge>
        </CardHeader>
        <CardContent class="space-y-6 p-6">
          <div v-if="isLoading" class="rounded-2xl border border-dashed border-slate-200 bg-white/60 px-4 py-10 text-center text-sm text-slate-500">
            {{ t('dashboard.focus.loading') }}
          </div>
          <div v-else-if="!focusTask?.filename" class="rounded-2xl border border-dashed border-slate-200 bg-white/60 px-4 py-10 text-center text-sm text-slate-500">
            {{ t('dashboard.focus.noResults') }}
          </div>
          <template v-else>
            <div class="grid gap-4 md:grid-cols-3">
              <article
                v-for="card in insightCards"
                :key="card.label"
                class="rounded-2xl border border-slate-200/70 bg-slate-50/80 p-4 shadow-sm"
              >
                <p class="text-xs uppercase tracking-[0.18em] text-slate-500">{{ card.label }}</p>
                <p class="mt-3 text-2xl font-semibold text-slate-900">{{ card.value }}</p>
                <p class="mt-2 text-xs text-slate-500">{{ card.hint }}</p>
              </article>
            </div>
            <PriceTrendChart :points="focusInsights?.daily_trend || []" />
            <div class="grid gap-3 rounded-[28px] border border-slate-200/70 bg-white/80 p-5 shadow-sm md:grid-cols-3">
              <div class="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                {{ t('dashboard.focus.currentMedian') }}
                <span class="font-semibold text-slate-900">
                  {{ focusInsights?.market_summary.median_price ? `¥${focusInsights.market_summary.median_price}` : '—' }}
                </span>
              </div>
              <div class="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                {{ t('dashboard.focus.historyMin') }}
                <span class="font-semibold text-slate-900">
                  {{ focusInsights?.history_summary.min_price ? `¥${focusInsights.history_summary.min_price}` : '—' }}
                </span>
              </div>
              <div class="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                {{ t('dashboard.focus.historyMax') }}
                <span class="font-semibold text-slate-900">
                  {{ focusInsights?.history_summary.max_price ? `¥${focusInsights.history_summary.max_price}` : '—' }}
                </span>
              </div>
            </div>
          </template>
        </CardContent>
      </Card>
      <div class="space-y-6">
        <Card class="app-surface">
          <CardHeader class="border-b border-slate-100 pb-4">
            <CardTitle class="flex items-center gap-2 text-lg font-extrabold text-[#102a56]">
              <Activity class="h-5 w-5 text-primary" />
              {{ t('dashboard.activity.title') }}
            </CardTitle>
          </CardHeader>
          <CardContent class="p-0">
            <div v-if="activities.length === 0" class="px-4 pb-4 text-sm text-slate-500">
              {{ t('dashboard.activity.empty') }}
            </div>
            <div v-else class="divide-y divide-slate-100/50">
              <button
                v-for="activity in activities"
                :key="activity.id"
                class="w-full p-4 text-left hover:bg-slate-50/50 transition-colors"
                @click="openActivity(activity)"
              >
                <div class="flex items-center justify-between gap-3">
                  <div class="flex items-center gap-3 min-w-0">
                    <div class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shrink-0"></div>
                    <div class="min-w-0">
                      <p class="text-sm font-bold text-slate-700 truncate">{{ activity.title }}</p>
                      <p class="text-[11px] text-slate-400">
                        {{ activity.task_name }} · {{ formatRelativeTimeFromNow(activity.timestamp) }}
                      </p>
                      <p v-if="activity.detail" class="mt-1 text-xs text-slate-500 truncate">{{ activity.detail }}</p>
                    </div>
                  </div>
                  <Badge variant="outline" class="text-[10px] border-slate-200 shrink-0">
                    {{ activity.status }}
                  </Badge>
                </div>
              </button>
            </div>
            <button
              class="w-full py-3 text-xs font-bold text-primary hover:bg-slate-50 transition-colors flex items-center justify-center gap-2 border-t border-slate-100/50"
              @click="router.push({ name: 'Logs' })"
            >
              {{ t('dashboard.activity.viewAllLogs') }}
              <ArrowRight class="w-3 h-3" />
            </button>
          </CardContent>
        </Card>
        <div class="relative overflow-hidden rounded-[20px] bg-gradient-to-br from-[#102a56] via-[#123f85] to-[#125fe0] p-6 text-white shadow-[0_24px_50px_-30px_rgba(18,95,224,0.85)]">
          <div class="absolute -right-10 -top-10 h-32 w-32 rounded-full border-[22px] border-white/5"></div>
          <div class="relative">
            <div class="mb-4 flex items-center gap-2">
              <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-white/10">
                <Zap class="h-5 w-5 text-amber-400" />
              </span>
              <h4 class="text-lg font-extrabold">{{ t('dashboard.suggestion.sectionTitle') }}</h4>
            </div>
            <p class="mb-2 text-sm font-bold leading-relaxed text-white">{{ suggestion.title }}</p>
            <p class="mb-6 text-sm leading-relaxed text-blue-100">{{ suggestion.description }}</p>
            <Button class="w-full rounded-xl bg-white font-bold text-blue-700 shadow-lg hover:bg-blue-50" @click="openSuggestion">
              <Sparkles class="mr-2 h-4 w-4" />
              {{ suggestion.actionLabel }}
            </Button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
