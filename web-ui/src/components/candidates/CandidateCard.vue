<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  BellRing,
  Bookmark,
  Check,
  CircleHelp,
  Clock3,
  ImageOff,
  MessageSquareText,
  ShieldAlert,
  Star,
  TrendingDown,
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

const GRADE_META: Record<string, { label: string; hint: string; badge: string; ring: string; bar: string }> = {
  S: {
    label: 'S 级',
    hint: '立刻联系',
    badge: 'border-[#9FDCC4] bg-[#E6F7F0] text-[#0A6B4C]',
    ring: 'text-[#0A6B4C]',
    bar: 'bg-[#14A06E]',
  },
  A: {
    label: 'A 级',
    hint: '可谈',
    badge: 'border-[#BFD4F7] bg-[#EDF3FE] text-[#1E5BD8]',
    ring: 'text-[#1E5BD8]',
    bar: 'bg-[#3B78ED]',
  },
  B: {
    label: 'B 级',
    hint: '补证据',
    badge: 'border-[#F1D7A7] bg-[#FFF8EA] text-[#A56209]',
    ring: 'text-[#B77912]',
    bar: 'bg-[#E1A23C]',
  },
  C: {
    label: 'C 级',
    hint: '观察',
    badge: 'border-[#E2E8F1] bg-[#F5F7FA] text-[#64748B]',
    ring: 'text-[#64748B]',
    bar: 'bg-[#9AA8BC]',
  },
  D: {
    label: 'D 级',
    hint: '放弃',
    badge: 'border-[#F1D3CE] bg-[#FFF4F2] text-[#B83B2D]',
    ring: 'text-[#B83B2D]',
    bar: 'bg-[#D26A58]',
  },
}

const grade = computed(() => props.candidate.ai_grade || '')
const gradeMeta = computed(() => GRADE_META[grade.value] || null)
const isFavorite = computed(() => props.candidate.review_status === 'favorite')
const isHandled = computed(() => props.candidate.review_status === 'handled')
const evidence = computed(() => props.candidate.ai_summary || 'AI 尚未给出完整判断。')
const missing = computed(() => props.candidate.missing_checks.join('、'))
const scoreTone = computed(() => gradeMeta.value?.ring || 'text-[#64748B]')
const scoreBarTone = computed(() => gradeMeta.value?.bar || 'bg-[#9AA8BC]')
const caps = computed(() => props.candidate.caps_applied || [])

// 品类分区：显卡看型号/显存/性能档，手机看电池/保修/账号，其他品类不额外占位。
const category = computed<'gpu' | 'phone' | 'other'>(() => {
  const c = props.candidate
  if (c.category) return c.category
  if (c.specs?.model) return 'gpu'
  return 'other'
})

const CARD_CLASS_LABEL: Record<string, string> = {
  professional: '专业卡',
  mining: '矿卡',
  consumer: '消费级',
  unknown: '',
}

const gpuChips = computed(() => {
  const c = props.candidate
  if (category.value !== 'gpu' || !c.specs) return []
  const chips: { text: string; tone: string }[] = []
  const label = c.specs.model_label || c.specs.model
  if (label) chips.push({ text: label, tone: 'border-[#C9DBF8] bg-[#EEF4FF] text-[#1E5BD8]' })
  if (c.specs.vram_gb) {
    chips.push({ text: `${c.specs.vram_gb}G`, tone: 'border-[#E2E8F1] bg-[#F5F7FA] text-[#52637B]' })
  }
  if (typeof c.specs.performance === 'number') {
    chips.push({
      text: `性能 ${c.specs.performance}`,
      tone: 'border-[#D7E4F6] bg-[#F1F7FF] text-[#2B5D9E]',
    })
  }
  const classLabel = CARD_CLASS_LABEL[c.specs.card_class] || ''
  if (classLabel && c.specs.card_class !== 'consumer') {
    chips.push({ text: classLabel, tone: 'border-[#F1D3CE] bg-[#FFF4F2] text-[#B83B2D]' })
  }
  return chips
})

const PHONE_KEY_KEYS = ['battery_health', 'battery', 'warranty', 'account_and_codes', 'imei']
const phoneChips = computed(() => {
  const c = props.candidate
  if (category.value !== 'phone') return []
  const byKey = new Map(c.criteria.map((item) => [item.key, item]))
  const chips: { text: string; tone: string }[] = []
  for (const key of PHONE_KEY_KEYS) {
    const item = byKey.get(key)
    if (!item) continue
    const status = String(item.status || '').toUpperCase()
    const tone =
      status === 'PASS'
        ? 'border-[#CAEBDD] bg-[#F0FBF6] text-[#0C7A56]'
        : status === 'FAIL'
          ? 'border-[#F2D2CD] bg-[#FFF5F3] text-[#B83B2D]'
          : 'border-[#F1D7A7] bg-[#FFF9ED] text-[#A56209]'
    const label = key === 'battery_health' || key === 'battery' ? '电池' : item.label || key
    const detail = (item.comment || item.evidence || '').trim()
    chips.push({ text: detail ? `${label} ${detail.slice(0, 14)}` : label, tone })
    if (chips.length >= 3) break
  }
  return chips
})

// 价格位置：<1 表示比行情便宜。关键词口径只作估算，加「约」弱化。
const priceGap = computed(() => {
  const gap = props.candidate.price_gap
  if (gap === null || gap === undefined) return null
  const diff = Math.round((1 - gap) * 100)
  const approx = props.candidate.price_gap_scope === 'keyword' ? '约' : ''
  if (Math.abs(diff) < 1) return { text: '与行情持平', good: false, approx }
  if (diff > 0) return { text: `${approx}低于行情 ${diff}%`, good: true, approx }
  return { text: `${approx}高于行情 ${Math.abs(diff)}%`, good: false, approx }
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
          v-if="gradeMeta"
          class="mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-black leading-none"
          :class="gradeMeta.badge"
        >
          {{ gradeMeta.label }}
          <span class="text-[9.5px] font-bold opacity-80">{{ gradeMeta.hint }}</span>
        </span>
        <span
          v-else
          class="mt-0.5 inline-flex shrink-0 items-center rounded-md border border-[#E2E8F1] bg-[#F5F7FA] px-2 py-1 text-[11px] font-bold leading-none text-[#8492A6]"
        >
          待评估
        </span>
      </div>

      <div class="mt-2 flex items-baseline gap-2">
        <span class="text-[27px] font-black leading-none tracking-tight text-[#E03838]">{{ candidate.price_display }}</span>
        <span
          v-if="priceGap"
          class="ml-auto inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10.5px] font-bold"
          :class="priceGap.good ? 'bg-[#E9F7F0] text-[#0A6B4C]' : 'bg-[#F5F7FA] text-[#7B8AA3]'"
        >
          <TrendingDown v-if="priceGap.good" class="h-3 w-3" :stroke-width="2.2" />
          {{ priceGap.text }}
        </span>
        <span v-else-if="candidate.market.label" class="ml-auto text-[10.5px] font-medium text-[#8B9AB0]">
          {{ candidate.market.label }}
        </span>
      </div>

      <div
        v-if="gpuChips.length || phoneChips.length"
        class="mt-2 flex flex-wrap items-center gap-1"
      >
        <span
          v-for="chip in (category === 'gpu' ? gpuChips : phoneChips)"
          :key="chip.text"
          class="inline-flex max-w-full items-center truncate rounded-md border px-1.5 py-0.5 text-[10px] font-bold leading-none"
          :class="chip.tone"
        >
          {{ chip.text }}
        </span>
      </div>

      <div
        v-if="candidate.ai_score !== null && candidate.score_breakdown?.length"
        class="mt-2.5 rounded-lg border border-[#E1EAF8] bg-[#F7FAFF] px-2.5 py-2"
      >
        <div class="flex items-center gap-3">
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
        <p v-if="caps.length" class="mt-1.5 flex items-start gap-1 border-t border-[#EDF2FA] pt-1.5 text-[10px] leading-snug text-[#A56209]">
          <ShieldAlert class="mt-[1px] h-3 w-3 shrink-0" :stroke-width="2" />
          <span class="line-clamp-2">已封顶：{{ caps.join('；') }}</span>
        </p>
        <p
          v-if="candidate.recommended && !candidate.meets_push"
          class="mt-1.5 border-t border-[#EDF2FA] pt-1.5 text-[10px] leading-snug text-[#8B9AB0]"
        >
          AI 建议关注，但未达推送线 {{ candidate.push_min_score }} 分，不会发通知
        </p>
        <p
          v-else-if="candidate.meets_push"
          class="mt-1.5 flex items-center gap-1 border-t border-[#EDF2FA] pt-1.5 text-[10px] font-bold leading-snug text-[#0A6B4C]"
        >
          <BellRing class="h-3 w-3" :stroke-width="2.2" /> 已达推送线，会发送通知
        </p>
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
