<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  ArrowUpRight,
  Bookmark,
  Check,
  CircleAlert,
  CircleCheck,
  CircleHelp,
  Cpu,
  MapPin,
  Smartphone,
  Star,
  Store,
  Tag,
} from 'lucide-vue-next'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import type { Candidate } from '@/api/workbench'

const props = defineProps<{ candidate: Candidate | null }>()
const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{
  (event: 'favorite'): void
  (event: 'handle'): void
  (event: 'ignore'): void
}>()

const activeImage = ref(0)
const imageBroken = ref(false)

watch(
  () => props.candidate?.item_id,
  () => {
    activeImage.value = 0
    imageBroken.value = false
  }
)

const images = computed(() => props.candidate?.images?.filter(Boolean) || [])
const currentImage = computed(() => images.value[activeImage.value] || props.candidate?.image || '')
const isFavorite = computed(() => props.candidate?.review_status === 'favorite')
const isHandled = computed(() => props.candidate?.review_status === 'handled')

const verdictTone = computed(() => {
  switch (props.candidate?.ai_verdict) {
    case 'recommend':
      return 'border-[#BFE8D7] bg-[#EAF8F2] text-[#0C7A56]'
    case 'verify':
      return 'border-[#F1D7A7] bg-[#FFF8EA] text-[#A56209]'
    case 'failed':
      return 'border-[#F1D3CE] bg-[#FFF4F2] text-[#B83B2D]'
    default:
      return 'border-[#E2E8F1] bg-[#F5F7FA] text-[#64748B]'
  }
})

const GRADE_META: Record<string, { label: string; hint: string; badge: string }> = {
  S: { label: 'S 级', hint: '立刻联系', badge: 'border-[#9FDCC4] bg-[#E6F7F0] text-[#0A6B4C]' },
  A: { label: 'A 级', hint: '可谈', badge: 'border-[#BFD4F7] bg-[#EDF3FE] text-[#1E5BD8]' },
  B: { label: 'B 级', hint: '补证据', badge: 'border-[#F1D7A7] bg-[#FFF8EA] text-[#A56209]' },
  C: { label: 'C 级', hint: '观察', badge: 'border-[#DDE3EC] bg-[#F4F6FA] text-[#52637B]' },
  D: { label: 'D 级', hint: '放弃', badge: 'border-[#F1D3CE] bg-[#FFF4F2] text-[#B83B2D]' },
}

const gradeMeta = computed(() => (props.candidate?.ai_grade ? GRADE_META[props.candidate.ai_grade] || null : null))
const caps = computed(() => props.candidate?.caps_applied || [])
const priceGapText = computed(() => {
  const gap = props.candidate?.price_gap
  if (gap === null || gap === undefined) return null
  const diff = Math.round((1 - gap) * 100)
  const approx = props.candidate?.price_gap_scope === 'keyword' ? '约' : ''
  if (Math.abs(diff) < 1) return '与行情持平'
  return diff > 0 ? `${approx}低于行情 ${diff}%` : `${approx}高于行情 ${Math.abs(diff)}%`
})

function criteriaTone(status: string) {
  if (status === 'PASS') return 'border-[#CAEBDD] bg-[#F0FBF6] text-[#0C7A56]'
  if (status === 'FAIL') return 'border-[#F2D2CD] bg-[#FFF5F3] text-[#B83B2D]'
  if (status === 'WARNING' || status === 'WARN') return 'border-[#F1D7A7] bg-[#FFF9ED] text-[#A56209]'
  return 'border-[#DDE5F1] bg-[#F6F8FC] text-[#5B6B82]'
}

function scoreColor(value: number) {
  if (value >= 75) return 'text-[#1E5BD8]'
  if (value >= 60) return 'text-[#B77912]'
  return 'text-[#B54A3A]'
}

function scoreBar(value: number) {
  if (value >= 75) return 'bg-[#3B78ED]'
  if (value >= 60) return 'bg-[#E1A23C]'
  return 'bg-[#D26A58]'
}

// ---------- 品类分区：显卡看硬件，手机看关键核实 ----------
const category = computed<'gpu' | 'phone' | 'other'>(() => {
  const c = props.candidate
  if (!c) return 'other'
  if (c.category) return c.category
  if (c.specs?.model) return 'gpu'
  return 'other'
})

// 维度数量不同（手机 5 个、显卡 7 个），列数跟着调，避免最后一格孤零零。
const breakdownGrid = computed(() => {
  const count = props.candidate?.score_breakdown?.length || 0
  if (count <= 4) return 'grid-cols-4'
  if (count === 5) return 'grid-cols-5'
  if (count <= 6) return 'grid-cols-3'
  return 'grid-cols-4'
})

const CARD_CLASS_LABEL: Record<string, string> = {
  consumer: '消费级',
  professional: '专业卡',
  mining: '矿卡',
  unknown: '卡型未知',
}

const gpuSpecs = computed(() => {
  const c = props.candidate
  if (!c || category.value !== 'gpu' || !c.specs) return null
  const expected = c.specs.expected_price
  let verdict = ''
  if (expected && c.price) {
    const diff = Math.round((c.price / expected - 1) * 100)
    if (diff <= -25) verdict = `比同档参考价低 ${Math.abs(diff)}%，捡漏区间`
    else if (diff <= -10) verdict = `比同档参考价低 ${Math.abs(diff)}%，偏便宜`
    else if (diff < 10) verdict = '与同档参考价基本持平'
    else verdict = `比同档参考价高 ${diff}%，偏贵`
  }
  return {
    model: c.specs.model_label || c.specs.model || '型号未识别',
    vram: c.specs.vram_gb ? `${c.specs.vram_gb}G` : '未知',
    cardClass: CARD_CLASS_LABEL[c.specs.card_class] || '卡型未知',
    performance: c.specs.performance ?? null,
    expected,
    verdict,
  }
})

const PHONE_KEYS = [
  'battery_health',
  'battery',
  'warranty',
  'account_and_codes',
  'imei',
  'condition',
]
const phoneChecks = computed(() => {
  const c = props.candidate
  if (!c || category.value !== 'phone') return []
  const byKey = new Map(c.criteria.map((item) => [item.key, item]))
  const picked: { key: string; label: string; status: string; statusLabel: string; comment: string }[] = []
  for (const key of PHONE_KEYS) {
    const item = byKey.get(key)
    if (!item) continue
    picked.push({
      key,
      label: key === 'battery_health' || key === 'battery' ? '电池健康' : item.label || key,
      status: String(item.status || '').toUpperCase(),
      statusLabel: item.status_label || item.status,
      comment: (item.comment || item.evidence || '').trim(),
    })
    if (picked.length >= 4) break
  }
  return picked
})
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent
      v-if="candidate"
      class="max-h-[92vh] w-[min(1000px,94vw)] overflow-hidden rounded-2xl border-0 p-0 sm:max-w-[1000px]"
    >
      <div class="flex max-h-[92vh] flex-col overflow-y-auto">
        <div class="flex items-start gap-4 border-b border-[#EDF1F7] px-6 py-5 pr-14">
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <span
                v-if="gradeMeta"
                class="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-black"
                :class="gradeMeta.badge"
              >
                {{ gradeMeta.label }} · {{ gradeMeta.hint }}
              </span>
              <span class="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-black" :class="verdictTone">
                <CircleCheck v-if="candidate.ai_verdict === 'recommend'" class="h-3 w-3" />
                <CircleHelp v-else-if="candidate.ai_verdict === 'verify'" class="h-3 w-3" />
                <CircleAlert v-else class="h-3 w-3" />
                {{ candidate.ai_label }}
              </span>
              <span class="rounded-md bg-[#F2F5FA] px-2 py-1 text-[10.5px] font-semibold text-[#718199]">
                {{ candidate.task_name }}
              </span>
            </div>
            <h2 class="mt-2 text-[20px] font-black leading-[1.4] tracking-tight text-[#172B4D]">
              {{ candidate.title }}
            </h2>
            <p class="mt-2 flex flex-wrap items-baseline gap-2">
              <span class="text-[26px] font-black leading-none text-[#E03838]">{{ candidate.price_display }}</span>
              <span v-if="priceGapText" class="text-[11.5px] font-bold text-[#0A6B4C]">{{ priceGapText }}</span>
            </p>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <a
              :href="candidate.link"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex h-11 items-center gap-2 rounded-lg bg-[#2360E6] px-5 text-[13px] font-bold text-white shadow-[0_10px_22px_-12px_rgba(35,96,230,0.9)] transition-colors hover:bg-[#1B51C9]"
            >
              <ArrowUpRight class="h-4 w-4" :stroke-width="2.4" />
              打开闲鱼商品
            </a>
          </div>
        </div>

        <div class="grid gap-0 lg:grid-cols-[minmax(0,0.88fr)_minmax(0,1.12fr)]">
          <div class="border-b border-[#EDF1F7] bg-[#F7F9FD] p-5 lg:border-b-0 lg:border-r">
            <div class="overflow-hidden rounded-xl border border-[#E4EAF4] bg-white">
              <div class="aspect-[4/3]">
                <img
                  v-if="currentImage && !imageBroken"
                  :src="currentImage"
                  :alt="candidate.title"
                  class="h-full w-full object-contain"
                  referrerpolicy="no-referrer"
                  @error="imageBroken = true"
                />
                <div v-else class="flex h-full items-center justify-center text-[12px] text-[#9BAECB]">暂无商品图片</div>
              </div>
            </div>
            <div v-if="images.length > 1" class="mt-3 flex gap-2 overflow-x-auto pb-1">
              <button
                v-for="(image, index) in images"
                :key="image"
                type="button"
                class="h-14 w-16 shrink-0 overflow-hidden rounded-lg border-2 transition-all"
                :class="activeImage === index ? 'border-[#2360E6]' : 'border-transparent opacity-70 hover:opacity-100'"
                @click="activeImage = index; imageBroken = false"
              >
                <img :src="image" alt="" class="h-full w-full object-cover" referrerpolicy="no-referrer" />
              </button>
            </div>

            <div class="mt-4 rounded-xl border border-[#E5EAF4] bg-white p-3.5">
              <p class="text-[10px] font-black uppercase tracking-[0.14em] text-[#9AA8BC]">卖家</p>
              <div class="mt-2 flex items-center gap-3">
                <span class="flex h-9 w-9 items-center justify-center rounded-full bg-[#EEF4FF] text-[#2360E6]">
                  <Store class="h-4 w-4" />
                </span>
                <div class="min-w-0">
                  <p class="truncate text-[13px] font-black text-[#263B5C]">{{ candidate.seller.name }}</p>
                  <p class="mt-0.5 truncate text-[10.5px] text-[#7B8AA3]">
                    {{ candidate.seller.registered || '注册时长未知' }}
                    <template v-if="candidate.seller.rating"> · 好评 {{ candidate.seller.rating }}</template>
                  </p>
                </div>
              </div>
              <div class="mt-3 grid grid-cols-2 gap-2 text-[11px]">
                <span class="rounded-lg bg-[#F6F8FC] px-2.5 py-2 text-[#65758C]">
                  <span class="text-[#98A5B9]">信用</span>
                  <b class="ml-1 text-[#334155]">{{ candidate.seller.credit }}</b>
                </span>
                <span class="rounded-lg bg-[#F6F8FC] px-2.5 py-2 text-[#65758C]">
                  <span class="text-[#98A5B9]">地区</span>
                  <b class="ml-1 text-[#334155]">{{ candidate.location || '未知' }}</b>
                </span>
              </div>
            </div>
          </div>

          <div class="space-y-4 p-5">
            <section v-if="candidate.ai_score !== null && candidate.score_breakdown?.length" class="rounded-xl border border-[#DCE6F5] bg-white p-4">
              <div class="flex items-center gap-3">
                <div class="flex items-baseline gap-1.5">
                  <span class="text-[38px] font-black leading-none tracking-tight" :class="scoreColor(candidate.ai_score)">{{ candidate.ai_score }}</span>
                  <div>
                    <p class="text-[11px] font-black text-[#40526C]">综合评分</p>
                    <p class="text-[9.5px] text-[#94A2B8]">多维评估</p>
                  </div>
                </div>
                <span class="ml-auto rounded-md bg-[#F3F7FF] px-2 py-1 text-[10px] font-bold text-[#52709B]">
                  评分越高越值得优先核实
                </span>
              </div>
              <div v-if="caps.length" class="mt-3 rounded-lg border border-[#F1D7A7] bg-[#FFF9ED] px-3 py-2">
                <p class="text-[10.5px] font-black text-[#A56209]">已触发封顶规则，总分不得高于上限</p>
                <ul class="mt-1 space-y-0.5">
                  <li v-for="cap in caps" :key="cap" class="text-[11px] leading-snug text-[#9B6A2F]">· {{ cap }}</li>
                </ul>
              </div>
              <p
                v-if="candidate.recommended && !candidate.meets_push"
                class="mt-3 rounded-lg bg-[#F6F8FC] px-3 py-2 text-[11px] leading-relaxed text-[#71809A]"
              >
                AI 建议关注，但 {{ candidate.ai_score }} 分未达推送线 {{ candidate.push_min_score }} 分，本次不会发送微信通知。进入面板可见，便于人工复核。
              </p>
              <p
                v-else-if="candidate.meets_push"
                class="mt-3 rounded-lg bg-[#EAF8F2] px-3 py-2 text-[11px] font-bold leading-relaxed text-[#0A6B4C]"
              >
                已达推送线（{{ candidate.push_min_score }} 分），会发送微信通知。
              </p>
              <div class="mt-3 grid gap-3" :class="breakdownGrid">
                <div v-for="dimension in candidate.score_breakdown" :key="dimension.key">
                  <div class="flex items-center justify-between text-[10.5px] font-bold">
                    <span class="text-[#7B8AA3]">{{ dimension.label }}</span>
                    <span class="text-[#334867]">{{ dimension.value }}</span>
                  </div>
                  <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[#EDF1F8]">
                    <span class="block h-full rounded-full" :class="scoreBar(dimension.value)" :style="{ width: `${dimension.value}%` }"></span>
                  </div>
                </div>
              </div>
            </section>

            <section v-if="gpuSpecs" class="rounded-xl border border-[#DCE6F5] bg-white p-4">
              <div class="flex items-center gap-2">
                <span class="flex h-6 w-6 items-center justify-center rounded-md bg-[#E2EDFF] text-[#2360E6]">
                  <Cpu class="h-3.5 w-3.5" />
                </span>
                <h3 class="text-[13px] font-black text-[#1D3557]">显卡规格</h3>
                <span class="ml-auto text-[10px] font-bold text-[#8B9AB0]">型号与性能档决定上限</span>
              </div>
              <div class="mt-3 grid grid-cols-3 gap-2.5">
                <div class="rounded-lg bg-[#F6F9FE] px-3 py-2">
                  <p class="text-[10px] font-bold text-[#94A2B8]">型号</p>
                  <p class="mt-1 text-[13px] font-black text-[#1D3557]">{{ gpuSpecs.model }}</p>
                </div>
                <div class="rounded-lg bg-[#F6F9FE] px-3 py-2">
                  <p class="text-[10px] font-bold text-[#94A2B8]">显存</p>
                  <p class="mt-1 text-[13px] font-black text-[#1D3557]">{{ gpuSpecs.vram }}</p>
                </div>
                <div class="rounded-lg bg-[#F6F9FE] px-3 py-2">
                  <p class="text-[10px] font-bold text-[#94A2B8]">卡型</p>
                  <p
                    class="mt-1 text-[13px] font-black"
                    :class="gpuSpecs.cardClass === '矿卡' || gpuSpecs.cardClass === '专业卡' ? 'text-[#B83B2D]' : 'text-[#1D3557]'"
                  >{{ gpuSpecs.cardClass }}</p>
                </div>
              </div>
              <div v-if="gpuSpecs.performance !== null" class="mt-3">
                <div class="flex items-center justify-between text-[10.5px] font-bold">
                  <span class="text-[#7B8AA3]">性能档（RTX 5090 = 100 分）</span>
                  <span class="text-[#334867]">{{ gpuSpecs.performance }} / 100</span>
                </div>
                <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[#EDF1F8]">
                  <span class="block h-full rounded-full bg-[#3B78ED]" :style="{ width: `${gpuSpecs.performance}%` }"></span>
                </div>
              </div>
              <div v-if="gpuSpecs.expected" class="mt-3 flex flex-wrap items-center gap-2 text-[11.5px]">
                <span class="rounded-md bg-[#F3F7FF] px-2 py-1 font-bold text-[#52709B]">
                  同档参考价 ¥{{ Math.round(gpuSpecs.expected) }}
                </span>
                <span
                  v-if="gpuSpecs.verdict"
                  class="font-bold"
                  :class="gpuSpecs.verdict.includes('低') ? 'text-[#0A6B4C]' : gpuSpecs.verdict.includes('高') ? 'text-[#B83B2D]' : 'text-[#7B8AA3]'"
                >
                  {{ gpuSpecs.verdict }}
                </span>
              </div>
            </section>

            <section v-if="phoneChecks.length" class="rounded-xl border border-[#DCE6F5] bg-white p-4">
              <div class="flex items-center gap-2">
                <span class="flex h-6 w-6 items-center justify-center rounded-md bg-[#E2EDFF] text-[#2360E6]">
                  <Smartphone class="h-3.5 w-3.5" />
                </span>
                <h3 class="text-[13px] font-black text-[#1D3557]">手机关键项</h3>
                <span class="ml-auto text-[10px] font-bold text-[#8B9AB0]">电池/保修/账号是三处最容易踩坑</span>
              </div>
              <div class="mt-3 grid grid-cols-2 gap-2.5">
                <div
                  v-for="check in phoneChecks"
                  :key="check.key"
                  class="rounded-lg border px-3 py-2"
                  :class="criteriaTone(check.status)"
                >
                  <div class="flex items-center justify-between">
                    <span class="text-[10.5px] font-black">{{ check.label }}</span>
                    <span class="text-[9.5px] font-bold opacity-80">{{ check.statusLabel }}</span>
                  </div>
                  <p class="mt-1 line-clamp-2 text-[10.5px] leading-snug opacity-90">
                    {{ check.comment || '未提供' }}
                  </p>
                </div>
              </div>
            </section>

            <section class="rounded-xl border border-[#DCE6F5] bg-[#F4F8FF] p-4">
              <div class="flex items-center gap-2">
                <span class="flex h-6 w-6 items-center justify-center rounded-md bg-[#E2EDFF] text-[#2360E6]">
                  <Star class="h-3.5 w-3.5" />
                </span>
                <h3 class="text-[13px] font-black text-[#1D3557]">AI 判断依据</h3>
              </div>
              <p class="mt-2 text-[12.5px] leading-[1.7] text-[#4A5C75]">
                {{ candidate.ai_reason || candidate.ai_summary }}
              </p>
              <div v-if="candidate.ai_summary && candidate.ai_summary !== candidate.ai_reason" class="mt-2 rounded-lg bg-white/80 px-3 py-2 text-[11.5px] leading-relaxed text-[#65758C]">
                {{ candidate.ai_summary }}
              </div>
              <div v-if="candidate.risk_tags.length" class="mt-3 flex flex-wrap gap-1.5">
                <span
                  v-for="tag in candidate.risk_tags"
                  :key="tag"
                  class="rounded-md border border-[#F0D5C8] bg-[#FFF8F4] px-2 py-1 text-[10px] font-semibold text-[#A85B32]"
                >
                  {{ tag }}
                </span>
              </div>
            </section>

            <section>
              <div class="flex items-center justify-between">
                <h3 class="text-[13px] font-black text-[#1D3557]">核实清单</h3>
                <span class="text-[10.5px] text-[#8B9AB0]">共 {{ candidate.criteria.length }} 项依据</span>
              </div>
              <div v-if="candidate.criteria.length" class="mt-2 space-y-2">
                <div
                  v-for="item in candidate.criteria"
                  :key="item.key"
                  class="rounded-xl border border-[#EBEFF6] bg-white p-3"
                >
                  <div class="flex items-start gap-2">
                    <span class="mt-[1px] inline-flex shrink-0 rounded-md border px-1.5 py-0.5 text-[9.5px] font-black" :class="criteriaTone(item.status)">
                      {{ item.status_label }}
                    </span>
                    <div class="min-w-0">
                      <p class="text-[11.5px] font-bold text-[#3A4D69]">{{ item.label }}</p>
                      <p class="mt-1 line-clamp-2 text-[11px] leading-relaxed text-[#728197]">{{ item.comment || item.evidence }}</p>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="mt-2 rounded-xl border border-dashed border-[#DCE4F0] px-4 py-6 text-center text-[11.5px] text-[#8B9AB0]">
                这条记录没有结构化核实项，可查看上方 AI 依据。
              </div>
            </section>

            <section class="grid grid-cols-2 gap-2.5">
              <div class="rounded-xl border border-[#EBEFF6] bg-[#FAFBFD] px-3 py-2.5">
                <p class="text-[10px] font-bold text-[#94A2B8]">发现时间</p>
                <p class="mt-1 text-[12px] font-bold text-[#40526C]">{{ candidate.crawl_label }}</p>
              </div>
              <div class="rounded-xl border border-[#EBEFF6] bg-[#FAFBFD] px-3 py-2.5">
                <p class="text-[10px] font-bold text-[#94A2B8]">发布时间</p>
                <p class="mt-1 text-[12px] font-bold text-[#40526C]">{{ candidate.publish_label || '未知' }}</p>
              </div>
              <div class="col-span-2 flex flex-wrap items-center gap-2 rounded-xl border border-[#EBEFF6] bg-[#FAFBFD] px-3 py-2.5 text-[11px] text-[#65758C]">
                <MapPin class="h-3.5 w-3.5 text-[#9AA8BC]" />
                {{ candidate.location || '发货地未知' }}
                <span class="text-[#D3DBE8]">|</span>
                <Tag class="h-3.5 w-3.5 text-[#9AA8BC]" />
                {{ candidate.tags.length ? candidate.tags.join(' · ') : '无特殊标签' }}
                <span v-if="candidate.wants" class="ml-auto">想要 {{ candidate.wants }}</span>
              </div>
            </section>

            <div class="flex flex-wrap items-center gap-2 border-t border-[#EDF1F7] pt-4">
              <button
                type="button"
                class="inline-flex h-10 items-center gap-1.5 rounded-lg border px-4 text-[12px] font-bold transition-colors"
                :class="isFavorite
                  ? 'border-[#E7C98B] bg-[#FFF8E8] text-[#A5660A]'
                  : 'border-[#DCE4F0] bg-white text-[#40526C] hover:border-[#B8C8E2] hover:text-[#2360E6]'"
                @click="emit('favorite')"
              >
                <Check v-if="isFavorite" class="h-4 w-4" />
                <Bookmark v-else class="h-4 w-4" />
                {{ isFavorite ? '已收藏' : '收藏' }}
              </button>
              <button
                type="button"
                class="inline-flex h-10 items-center gap-1.5 rounded-lg bg-[#2360E6] px-4 text-[12px] font-bold text-white transition-colors hover:bg-[#1B51C9]"
                @click="emit('handle')"
              >
                <CircleCheck class="h-4 w-4" />
                {{ isHandled ? '已处理' : '标记已处理' }}
              </button>
              <button
                type="button"
                class="ml-auto h-10 rounded-lg px-3 text-[12px] font-semibold text-[#9AA7BA] transition-colors hover:bg-[#F4F6FA] hover:text-[#52637B]"
                @click="emit('ignore')"
              >
                忽略这条
              </button>
            </div>
          </div>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>
