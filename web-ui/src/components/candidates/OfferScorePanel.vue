<script setup lang="ts">
/**
 * 绝对分评级面板：6 条维度进度条 + 辅助加减分 + 总评分徽标 + 一票否决红条。
 *
 * 几个设计决定值得说明：
 *
 * 1. **进度条按「得分/满分」画**，不是按 0–100。价格分满分 30，赚 30 就是满格；
 *    如果统一按 100 画，所有维度都会缩成一小截，看不出哪个维度掉了分。
 * 2. **不可判 ≠ 0 分**。拿不到事实的维度画成灰色虚线条并标「不可判」，
 *    绝不画成空条——空条会被读成「这项得零分」，是错误信息。
 * 3. **命中否决时徽标不说「跳过」而说「别买」**，并把总分压成次要信息。
 *    分数高但被否决，是最容易被误读的情形（"86分为什么不能买"），
 *    所以红条必须排在分数上面。
 * 4. **价格分与性价比分必须分开显示**（detail 模式额外标两个比率）。
 *    它们会给出相反结论：一台机器可以「比二手行情低」但「比全新只便宜一点」。
 *    合并成一个数字，用户就永远无法判断自己是「捡漏」还是「买了个不划算的便宜」。
 */
import { computed } from 'vue'
import { AlertOctagon, Ban, CircleHelp, TrendingDown, TrendingUp } from 'lucide-vue-next'
import type { OfferDimension, OfferScore } from '@/api/workbench'

const props = defineProps<{
  offer: OfferScore
  /** compact = 卡片内紧凑版；full = 详情页完整版 */
  variant?: 'compact' | 'full'
}>()

const isFull = computed(() => props.variant === 'full')

const gradeTone = computed(() => {
  if (props.offer.vetoed) {
    return {
      text: 'text-[#A32D2D]',
      badge: 'border-[#F1C9C4] bg-[#FDEDEB] text-[#A32D2D]',
      bar: 'bg-[#D9544A]',
      label: '别买',
    }
  }
  switch (props.offer.grade) {
    case 'buy':
      return {
        text: 'text-[#0C7A56]',
        badge: 'border-[#A9E2CB] bg-[#E8F8F1] text-[#0C7A56]',
        bar: 'bg-[#18A97C]',
        label: props.offer.grade_label,
      }
    case 'negotiate':
      return {
        text: 'text-[#9A6A08]',
        badge: 'border-[#F0DCA4] bg-[#FFF8E4] text-[#9A6A08]',
        bar: 'bg-[#D9A22B]',
        label: props.offer.grade_label,
      }
    case 'watch':
      return {
        text: 'text-[#A2570C]',
        badge: 'border-[#F2D2B0] bg-[#FFF4E8] text-[#A2570C]',
        bar: 'bg-[#E08A3C]',
        label: props.offer.grade_label,
      }
    default:
      return {
        text: 'text-[#64748B]',
        badge: 'border-[#DCE3EC] bg-[#F3F6FA] text-[#64748B]',
        bar: 'bg-[#94A3B8]',
        label: props.offer.grade_label,
      }
  }
})

const dims = computed<OfferDimension[]>(() => props.offer.dimensions || [])

function barWidth(dim: OfferDimension) {
  if (!dim.scored || dim.value === null) return 0
  return Math.max(0, Math.min(100, (dim.value / dim.max) * 100))
}

/** 维度条的颜色按「该维度拿到几成」决定，一眼看出哪里掉分。 */
function barTone(dim: OfferDimension) {
  if (!dim.scored || dim.value === null) return ''
  const ratio = dim.value / dim.max
  if (ratio >= 0.8) return 'bg-[#18A97C]'
  if (ratio >= 0.5) return 'bg-[#4C86E8]'
  if (ratio >= 0.25) return 'bg-[#E0A93C]'
  return 'bg-[#D9685A]'
}

const hasPartialInfo = computed(() => props.offer.scored_max < props.offer.max_total)

const adjustments = computed(() => props.offer.adjustments || [])

/** 只展示命中的辅助信号；没命中就不占位置，避免「一堆 0」。 */
const activeAdjustments = computed(() =>
  adjustments.value.filter((item) => item.delta !== 0 && item.tone !== 'neutral'),
)

/**
 * 两个价格锚点的说明文字。
 *
 * 分开展示是刻意的：二手行情比看「卖家要价离谱吗」，
 * 全新价比看「这台到底值不值得买」。两个数都缺时如实说缺，
 * 不拿其中一个冒充另一个。
 */
const priceAnchors = computed(() => {
  const out: { label: string; text: string; tone: 'good' | 'bad' | 'neutral' }[] = []
  const o = props.offer

  if (o.price_ratio !== null && o.market_median !== null) {
    const pct = Math.round((1 - o.price_ratio) * 100)
    out.push({
      label: `二手行情 ¥${Math.round(o.market_median)}`,
      text: pct > 0 ? `低 ${pct}%` : pct < 0 ? `高 ${Math.abs(pct)}%` : '持平',
      tone: pct >= 10 ? 'good' : pct < 0 ? 'bad' : 'neutral',
    })
  }

  if (o.ratio_used_vs_new !== null && o.new_price_anchor !== null) {
    const saved = Math.round((1 - o.ratio_used_vs_new) * 100)
    out.push({
      label: `全新 ¥${Math.round(o.new_price_anchor)}`,
      // 「省 xx%」比「是全新的 xx%」更好懂：用户关心省了多少，不是比例本身
      text: saved > 0 ? `省 ${saved}%` : `贵 ${Math.abs(saved)}%`,
      tone: saved >= 25 ? 'good' : saved < 10 ? 'bad' : 'neutral',
    })
  }

  return out
})

const anchorTone: Record<string, string> = {
  good: 'text-[#0C7A56]',
  bad: 'text-[#A32D2D]',
  neutral: 'text-[#5B6B82]',
}

/**
 * 分数是否「不作数」：命中否决，或被引擎 verdict 降级。
 *
 * 这里不用删除线——删除线在列表里会被读成「这个数字算错了」，
 * 而实际含义是「分数是对的，但结论不是这个」。改用降透明度 + 一行红字说明。
 */
const isScoreVoid = computed(() => props.offer.vetoed || Boolean(props.offer.demoted_by))

const voidReason = computed(() => {
  if (props.offer.vetoed) return `命中否决：${props.offer.veto_flags.map((f) => f.label).join('、')}`
  if (props.offer.demoted_by === 'verdict') return '底层判定不匹配，分数仅供看性价比'
  return '仍需核实关键信息'
})
</script>

<template>
  <div class="overflow-hidden rounded-xl border" :class="offer.vetoed ? 'border-[#F1C9C4]' : 'border-[#E1EAF8]'">
    <!-- 一票否决红条：优先级最高，必须压在分数之上 -->
    <div v-if="offer.vetoed" class="bg-[#FDEDEB] px-3 py-2.5">
      <div class="flex items-start gap-2">
        <AlertOctagon class="mt-[1px] h-4 w-4 shrink-0 text-[#C0392B]" :stroke-width="2.4" />
        <div class="min-w-0">
          <p class="text-[11.5px] font-black leading-none text-[#A32D2D]">
            一票否决 · 命中 {{ offer.veto_flags.length }} 条
          </p>
          <ul class="mt-1.5 space-y-1">
            <li
              v-for="flag in offer.veto_flags"
              :key="flag.key + flag.detail"
              class="flex items-start gap-1.5 text-[11px] leading-[1.5] text-[#8C3A32]"
            >
              <Ban class="mt-[2px] h-3 w-3 shrink-0 text-[#C0392B]" :stroke-width="2.4" />
              <span class="min-w-0">
                <b class="font-black">{{ flag.label }}</b>
                <span class="text-[#A85C52]"> — {{ flag.detail }}</span>
              </span>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div :class="[isFull ? 'p-4' : 'p-2.5', offer.vetoed ? 'bg-[#FFFCFC]' : 'bg-[#F8FBFF]']">
      <!-- 总评分徽标 -->
      <div class="flex items-center gap-3">
        <div class="flex shrink-0 items-baseline gap-1">
          <span
            class="font-black leading-none tracking-tight"
            :class="[gradeTone.text, isFull ? 'text-[40px]' : 'text-[27px]', isScoreVoid ? 'opacity-50' : '']"
          >
            {{ offer.total ?? '—' }}
          </span>
          <span class="text-[10px] font-bold leading-none text-[#94A2B8]">/100</span>
        </div>
        <div class="min-w-0 flex-1">
          <!-- 紧凑模式下卡片右上角已经有同源徽标，这里不重复显示 -->
          <span
            v-if="isFull"
            class="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-black leading-none"
            :class="gradeTone.badge"
          >
            {{ gradeTone.label }}
          </span>
          <p
            v-if="isFull && offer.grade_note"
            class="mt-1 text-[10px] leading-[1.4] text-[#94A2B8]"
          >
            {{ offer.grade_note }}
          </p>
          <p
            v-else-if="!isFull && isScoreVoid"
            class="text-[9.5px] font-bold leading-[1.35] text-[#A32D2D]"
          >
            {{ voidReason }}
          </p>
          <p v-else-if="hasPartialInfo" class="text-[9.5px] leading-[1.35] text-[#94A2B8]">
            有效满分 {{ offer.scored_max }}，缺项按 0 计
          </p>
        </div>
      </div>

      <!-- 6 条维度进度条 -->
      <div class="mt-2.5" :class="isFull ? 'space-y-2' : 'space-y-1.5'">
        <div v-for="dim in dims" :key="dim.key" class="flex items-center gap-2">
          <span
            class="shrink-0 text-[9.5px] font-bold leading-none"
            :class="isFull ? 'w-[52px] text-[11px]' : 'w-[46px]'"
            :title="`${dim.label}（满分 ${dim.max}）`"
          >
            <span :class="dim.scored ? 'text-[#8190A6]' : 'text-[#B6C2D2]'">{{ dim.label }}</span>
          </span>
          <div class="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full" :class="dim.scored ? 'bg-[#E8EEF8]' : 'bg-[#EEF2F7]'">
            <span
              v-if="dim.scored"
              class="block h-full rounded-full transition-[width] duration-500"
              :class="barTone(dim)"
              :style="{ width: `${barWidth(dim)}%` }"
            ></span>
            <!-- 不可判：虚线底纹，明确不是「0 分」 -->
            <span v-else class="block h-full w-full rounded-full bg-[repeating-linear-gradient(45deg,#DFE6F0_0_3px,transparent_3px_6px)]"></span>
          </div>
          <span
            class="shrink-0 text-right font-bold leading-none"
            :class="[isFull ? 'w-[38px] text-[11px]' : 'w-[30px] text-[9px]', dim.scored ? 'text-[#40526C]' : 'text-[#B6C2D2]']"
          >
            {{ dim.scored ? `${dim.value}/${dim.max}` : '不可判' }}
          </span>
          <CircleHelp
            v-if="dim.inferred && isFull"
            class="h-3 w-3 shrink-0 text-[#C6A879]"
            :stroke-width="2"
            :title="`含推定成分：${dim.reason}`"
          />
        </div>
      </div>

      <!-- 辅助加减分：命中才显示，没命中不占位 -->
      <div v-if="activeAdjustments.length" class="mt-2 flex flex-wrap items-center gap-1">
        <span class="text-[9.5px] font-bold text-[#94A2B8]">附加</span>
        <span
          v-for="item in activeAdjustments"
          :key="item.key"
          class="inline-flex items-center gap-0.5 rounded border px-1 py-[1px] text-[9.5px] font-bold leading-none"
          :class="
            item.delta > 0
              ? 'border-[#A9E2CB] bg-[#E8F8F1] text-[#0C7A56]'
              : 'border-[#F1C9C4] bg-[#FDEDEB] text-[#A32D2D]'
          "
          :title="item.label"
        >
          <TrendingUp v-if="item.delta > 0" class="h-2.5 w-2.5" :stroke-width="2.6" />
          <TrendingDown v-else class="h-2.5 w-2.5" :stroke-width="2.6" />
          {{ item.delta > 0 ? '+' : '' }}{{ item.delta }}
        </span>
        <span
          v-if="offer.adjustment_total !== offer.adjustment_intent"
          class="text-[9px] text-[#94A2B8]"
          title="辅助分被缺项上限吃掉了一部分：拿不到的分不能靠时效性补回来"
        >
          （实计 {{ offer.adjustment_total >= 0 ? '+' : '' }}{{ offer.adjustment_total }}）
        </span>
      </div>

      <!-- 两个价格锚点：行情比 vs 全新价比，故意分开显示 -->
      <div v-if="isFull && priceAnchors.length" class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span v-for="anchor in priceAnchors" :key="anchor.label" class="text-[10px] leading-none text-[#94A2B8]">
          {{ anchor.label }}
          <b class="font-black" :class="anchorTone[anchor.tone]">{{ anchor.text }}</b>
        </span>
        <span
          v-if="offer.new_price_note"
          class="text-[9.5px] text-[#B6C2D2]"
          :title="offer.new_price_note"
        >锚点来源：{{ offer.new_price_note }}</span>
      </div>
      <p
        v-else-if="isFull && !offer.value_judged"
        class="mt-2 text-[10px] leading-[1.5] text-[#A57A29]"
      >
        未配置「全新最低价」锚点，性价比分 {{ offer.weights.value_vs_new }} 分未计入 — 去任务设置里填一个当前电商最低价，否则无法判断这台是否真划算。
      </p>

      <!-- 详情页展开每条维度的依据 -->
      <div v-if="isFull" class="mt-3 space-y-1.5 border-t border-[#E7EEF9] pt-2.5">
        <div v-for="dim in dims" :key="`r-${dim.key}`" class="flex gap-1.5 text-[10.5px] leading-[1.5]">
          <span class="w-[52px] shrink-0 font-bold text-[#7B8AA3]">{{ dim.label }}</span>
          <span class="min-w-0 flex-1 text-[#5B6B82]">
            {{ dim.reason }}
            <span v-if="dim.inferred" class="ml-1 rounded bg-[#FFF6E5] px-1 py-[1px] text-[9.5px] font-bold text-[#A57A29]">推定</span>
          </span>
        </div>
        <!-- 命中的辅助分也要列出来，否则「总分比六维之和高」无解释 -->
        <div v-for="item in activeAdjustments" :key="`a-${item.key}`" class="flex gap-1.5 text-[10.5px] leading-[1.5]">
          <span class="w-[52px] shrink-0 font-bold text-[#7B8AA3]">附加</span>
          <span class="min-w-0 flex-1" :class="item.delta > 0 ? 'text-[#0C7A56]' : 'text-[#A32D2D]'">
            {{ item.label }} {{ item.delta > 0 ? '+' : '' }}{{ item.delta }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
