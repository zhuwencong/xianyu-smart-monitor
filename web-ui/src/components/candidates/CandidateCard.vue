<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Bookmark,
  Check,
  CircleHelp,
  Clock3,
  ImageOff,
  MessageSquareText,
  ShieldAlert,
  Sparkles,
  Star,
  XCircle,
} from 'lucide-vue-next'
import type { Candidate } from '@/api/workbench'

const props = defineProps<{ candidate: Candidate }>()
const emit = defineEmits<{
  (event: 'open'): void
  (event: 'favorite'): void
  (event: 'handle'): void
  (event: 'ignore'): void
}>()

const imageFailed = ref(false)

const tone = computed(() => {
  switch (props.candidate.ai_verdict) {
    case 'recommend':
      return {
        badge: 'border-[#BFE8D7] bg-[#EAF8F2] text-[#0C7A56]',
        icon: Sparkles,
        label: '建议关注',
      }
    case 'verify':
      return {
        badge: 'border-[#F1D7A7] bg-[#FFF8EA] text-[#A56209]',
        icon: ShieldAlert,
        label: '需核实',
      }
    case 'failed':
      return {
        badge: 'border-[#F1D3CE] bg-[#FFF4F2] text-[#B83B2D]',
        icon: XCircle,
        label: 'AI 分析失败',
      }
    default:
      return {
        badge: 'border-[#E2E8F1] bg-[#F5F7FA] text-[#64748B]',
        icon: XCircle,
        label: '不匹配',
      }
  }
})

const isFavorite = computed(() => props.candidate.review_status === 'favorite')
const isHandled = computed(() => props.candidate.review_status === 'handled')
const evidence = computed(() => props.candidate.ai_summary || 'AI 尚未给出完整判断。')
const missing = computed(() => props.candidate.missing_checks.join('、'))
const scoreTone = computed(() => {
  const score = props.candidate.ai_score ?? 0
  if (score >= 75) return 'text-[#1E5BD8]'
  if (score >= 60) return 'text-[#B77912]'
  return 'text-[#B54A3A]'
})
const scoreBarTone = computed(() => {
  const score = props.candidate.ai_score ?? 0
  if (score >= 75) return 'bg-[#3B78ED]'
  if (score >= 60) return 'bg-[#E1A23C]'
  return 'bg-[#D26A58]'
})

function openDetail() {
  emit('open')
}
</script>

<template>
  <article
    class="group flex h-full cursor-pointer flex-col overflow-hidden rounded-[14px] border border-[#E7ECF5] bg-white shadow-[0_1px_2px_rgba(16,42,86,0.03)] transition-all duration-200 hover:-translate-y-0.5 hover:border-[#CBD9EF] hover:shadow-[0_22px_44px_-30px_rgba(20,55,110,0.35)]"
    role="button"
    tabindex="0"
    :aria-label="`查看 ${candidate.title} 的详细说明`"
    @click="openDetail"
    @keydown.enter="openDetail"
  >
    <button
      type="button"
      class="relative block w-full overflow-hidden bg-[#EEF3FA] text-left"
      :aria-label="`查看 ${candidate.title} 的详细说明`"
      @click.stop="emit('open')"
    >
      <div class="aspect-[2.35/1] w-full border-b border-[#EDF1F7]">
        <img
          v-if="candidate.image && !imageFailed"
          :src="candidate.image"
          :alt="candidate.title"
          class="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.015]"
          loading="lazy"
          referrerpolicy="no-referrer"
          @error="imageFailed = true"
        />
        <div
          v-else
          class="flex h-full w-full flex-col items-center justify-center gap-1.5 bg-gradient-to-br from-[#EDF3FC] to-[#E4EDFA] text-[#9BAECB]"
        >
          <ImageOff class="h-6 w-6" :stroke-width="1.6" />
          <span class="text-[11px] font-medium">暂无商品图片</span>
        </div>
      </div>
      <span
        v-if="isHandled"
        class="absolute left-3 top-3 rounded-md bg-[#102A56]/80 px-2 py-1 text-[10px] font-bold text-white backdrop-blur-sm"
      >
        已处理
      </span>
      <span
        v-else-if="isFavorite"
        class="absolute left-3 top-3 inline-flex items-center gap-1 rounded-md bg-white/90 px-2 py-1 text-[10px] font-bold text-[#B47808] shadow-sm backdrop-blur-sm"
      >
        <Star class="h-3 w-3 fill-current" /> 已收藏
      </span>
      <span
        class="pointer-events-none absolute bottom-2.5 right-2.5 rounded-md bg-[#102A56]/78 px-2 py-1 text-[10px] font-bold text-white opacity-0 backdrop-blur-sm transition-opacity duration-200 group-hover:opacity-100"
      >
        查看详情
      </span>
    </button>

    <div class="flex flex-1 flex-col px-4 pb-3 pt-3">
      <div class="flex items-start justify-between gap-2.5">
        <h3 class="line-clamp-2 min-h-[42px] text-[15.5px] font-black leading-[1.36] tracking-tight text-[#172B4D]">
          <button type="button" class="text-left transition-colors hover:text-[#2360E6]" @click.stop="emit('open')">
            {{ candidate.title }}
          </button>
        </h3>
        <span
          class="mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-black leading-none"
          :class="tone.badge"
        >
          <component :is="tone.icon" class="h-3 w-3" :stroke-width="2.4" />
          {{ tone.label }}
        </span>
      </div>

      <div class="mt-2 flex items-baseline gap-2">
        <span class="text-[27px] font-black leading-none tracking-tight text-[#E03838]">{{ candidate.price_display }}</span>
        <span v-if="candidate.market.label" class="ml-auto text-[10.5px] font-medium text-[#8B9AB0]">
          {{ candidate.market.label }}
        </span>
      </div>

      <div
        v-if="candidate.ai_score !== null && candidate.score_breakdown?.length"
        class="mt-2.5 flex items-center gap-3 rounded-lg border border-[#E1EAF8] bg-[#F7FAFF] px-2.5 py-2"
      >
        <div class="flex w-[54px] shrink-0 flex-col items-center">
          <span class="text-[29px] font-black leading-none tracking-tight" :class="scoreTone">{{ candidate.ai_score }}</span>
          <span class="mt-0.5 text-[9px] font-bold leading-none text-[#7B8AA3]">综合评分</span>
        </div>
        <div class="grid min-w-0 flex-1 grid-cols-2 gap-x-3 gap-y-1.5">
          <div v-for="dimension in candidate.score_breakdown" :key="dimension.key" class="flex items-center gap-1.5">
            <span class="w-[22px] shrink-0 text-[9px] font-bold leading-none text-[#8190A6]">{{ dimension.label }}</span>
            <div class="h-1 min-w-0 flex-1 overflow-hidden rounded-full bg-[#E8EEF8]">
              <span class="block h-full rounded-full" :class="scoreBarTone" :style="{ width: `${dimension.value}%` }"></span>
            </div>
            <span class="w-[17px] shrink-0 text-right text-[9px] font-bold leading-none text-[#40526C]">{{ dimension.value }}</span>
          </div>
        </div>
      </div>
      <div
        v-else
        class="mt-2.5 flex items-center justify-between rounded-lg border border-[#F0E2D6] bg-[#FFF9F3] px-2.5 py-2 text-[10px] text-[#9B6A2F]"
      >
        <span>AI 分析未完成，暂不评分</span>
        <button type="button" class="font-bold text-[#A56209]" @click.stop="emit('open')">查看原因</button>
      </div>

      <div class="mt-2.5 space-y-1.5 text-[12.5px] leading-[1.6]">
        <div class="flex gap-1.5">
          <MessageSquareText class="mt-[2px] h-3.5 w-3.5 shrink-0 text-[#8FA3BE]" :stroke-width="1.9" />
          <p class="line-clamp-2 min-h-[40px] text-[#5B6B82]">
            <span class="font-bold text-[#40526C]">判断依据：</span>{{ evidence }}
          </p>
        </div>
        <div class="flex gap-1.5">
          <CircleHelp class="mt-[2px] h-3.5 w-3.5 shrink-0 text-[#C08A33]" :stroke-width="1.9" />
          <p class="line-clamp-1 text-[#7A879B]">
            <span class="font-bold text-[#8A651F]">还需确认：</span>{{ missing }}
          </p>
        </div>
      </div>

      <div class="mt-auto flex flex-wrap items-center gap-2 pt-3">
        <div class="flex min-w-0 flex-1 items-center gap-1.5 text-[11px] text-[#94A2B8]">
          <Clock3 class="h-3 w-3 shrink-0" />
          <span class="truncate">闲鱼 · {{ candidate.crawl_label }} 发现</span>
        </div>
        <div class="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            class="inline-flex h-8 items-center justify-center rounded-md bg-[#2360E6] px-3 text-[12px] font-bold text-white shadow-[0_6px_14px_-8px_rgba(35,96,230,0.8)] transition-colors hover:bg-[#1B51C9]"
            @click.stop="emit('open')"
          >
            查看详情
          </button>
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1 rounded-md border px-2.5 text-[11.5px] font-bold transition-colors"
              :class="isFavorite
              ? 'border-[#EBD39E] bg-[#FFFAED] text-[#A5660A]'
              : 'border-[#E1E7F0] bg-white text-[#52637B] hover:border-[#C7D4E7] hover:bg-[#F8FAFD]'"
            @click.stop="emit('favorite')"
          >
            <Check v-if="isFavorite" class="h-3 w-3" :stroke-width="2.6" />
            <Bookmark v-else class="h-3 w-3" :stroke-width="2" />
            {{ isFavorite ? '已收藏' : '收藏' }}
          </button>
          <button
            type="button"
            class="h-8 rounded-md px-1.5 text-[11.5px] font-semibold text-[#9AA7BA] transition-colors hover:bg-[#F4F6FA] hover:text-[#52637B]"
            @click.stop="emit('ignore')"
          >
            忽略
          </button>
        </div>
      </div>
    </div>
  </article>
</template>
