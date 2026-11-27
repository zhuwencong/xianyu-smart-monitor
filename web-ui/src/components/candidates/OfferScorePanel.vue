<script setup lang="ts">
/**
 * 绝对分评级面板：总评分 + 两个价格锚点 + 6 条维度进度条 + 一票否决红条。
 *
 * 设计目标只有一个：**一眼看出该不该看这台**。为此做了四件事：
 *
 * 1. **两个价格锚点提到最显眼的位置**，用一句话说清「贵不贵」和「值不值」。
 *    这是整套模型的核心判断（防骗 + 防买亏），埋在进度条里等于没做。
 * 2. **价格分 / 性价比分单独成组**，用一条分隔线与「人/货/机/交易」隔开。
 *    六个维度平铺会让人误以为权重相同，实际上前两项占了 55 分。
 * 3. **进度条画粗、字号加大**，并且**掉分的维度用彩色数字**标出来，
 *    这样不用逐条读，视线会自己跳到红/黄那一行。
 * 4. **不可判画成灰色虚线条 + 明确文字**，绝不画成空条——
 *    空条会被读成「这项得零分」，是错误信息。
 */
import { computed } from 'vue'
import { AlertOctagon, Ban, CircleHelp, Minus, TrendingDown, TrendingUp } from 'lucide-vue-next'
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
      label: '别买',
    }
  }
  switch (props.offer.grade) {
    case 'buy':
      return {
        text: 'text-[#0C7A56]',
        badge: 'border-[#A9E2CB] bg-[#E8F8F1] text-[#0C7A56]',
        label: props.offer.grade_label,
      }
    case 'negotiate':
      return {
        text: 'text-[#9A6A08]',
        badge: 'border-[#F0DCA4] bg-[#FFF8E4] text-[#9A6A08]',
        label: props.offer.grade_label,
      }
    case 'watch':
      return {
        text: 'text-[#A2570C]',
        badge: 'border-[#F2D2B0] bg-[#FFF4E8] text-[#A2570C]',
        label: props.offer.grade_label,
      }
    default:
      return {
        text: 'text-[#64748B]',
        badge: 'border-[#DCE3EC] bg-[#F3F6FA] text-[#64748B]',
        label: props.offer.grade_label,
      }
  }
})

const dims = computed<OfferDimension[]>(() => props.offer.dimensions || [])
/** 两个价格维度单独成组：它们合计 55 分，且回答的是完全不同的问题。 */
const priceDims = computed(() =>
  dims.value.filter((d) => d.key === 'price_market' || d.key === 'value_vs_new'),
)
const otherDims = computed(() =>
  dims.value.filter((d) => d.key !== 'price_market' && d.key !== 'value_vs_new'),
)

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

/**
 * 掉分维度的**文字**也要跟着变色。
 *
 * 只给进度条上色不够——条子短了，但右边的 `6/10` 还是灰的，
 * 视线不会停。数字变红才会让人想「为什么只有 6 分」，
 * 然后才会去看「电池未知」这个真正的原因。
 */
function valueTone(dim: OfferDimension) {
  if (!dim.scored || dim.value === null) return 'text-[#B6C2D2]'
  const ratio = dim.value / dim.max
  if (ratio >= 0.8) return 'text-[#15805E]'
  if (ratio >= 0.5) return 'text-[#2F5FA8]'
  if (ratio >= 0.25) return 'text-[#A5720A]'
  return 'text-[#C0392B]'
}

const hasPartialInfo = computed(() => props.offer.scored_max < props.offer.max_total)
const adjustments = computed(() => props.offer.adjustments || [])
const activeAdjustments = computed(() =>
  adjustments.value.filter((item) => item.delta !== 0 && item.tone !== 'neutral'),
)

/**
 * 两个价格锚点，是这块面板里最该被看到的信息。
 *
 * 「行情」回答「卖家要价离谱吗」，「全新」回答「这台到底值不值得买」。
 * 两者会给出相反结论（行情偏低但全新也没便宜多少），所以必须并排显示，
 * 不能合成一个数——合成就再也拆不开了。
 */
const priceAnchors = computed(() => {
  const out: {
    key: string
    label: string
    value: string
    tone: 'good' | 'bad' | 'neutral'
    icon: 'down' | 'up' | 'flat'
    hint: string
  }[] = []
  const o = props.offer

  if (o.price_ratio !== null && o.market_median !== null) {
    const pct = Math.round((1 - o.price_ratio) * 100)
    out.push({
      key: 'market',
      label: isFull.value ? `二手行情 ¥${Math.round(o.market_median)}` : '行情',
      value: pct > 0 ? `低 ${pct}%` : pct < 0 ? `高 ${Math.abs(pct)}%` : '持平',
      tone: pct >= 10 ? 'good' : pct < 0 ? 'bad' : 'neutral',
      icon: pct > 0 ? 'down' : pct < 0 ? 'up' : 'flat',
      hint: `同型号二手行情中位价 ¥${Math.round(o.market_median)}，高于此价说明要价偏高`,
    })
  }

  if (o.ratio_used_vs_new !== null && o.new_price_anchor !== null) {
    const saved = Math.round((1 - o.ratio_used_vs_new) * 100)
    out.push({
      key: 'new',
      label: isFull.value ? `全新 ¥${Math.round(o.new_price_anchor)}` : '全新',
      // 「省 xx%」比「是全新的 xx%」好懂：用户关心省了多少，不是比例本身
      value: saved > 0 ? `省 ${saved}%` : `贵 ${Math.abs(saved)}%`,
      tone: saved >= 25 ? 'good' : saved < 10 ? 'bad' : 'neutral',
      icon: saved > 0 ? 'down' : 'up',
      hint: `当前电商全新最低价 ¥${Math.round(o.new_price_anchor)}${o.new_price_note ? `（${o.new_price_note}）` : ''}`,
    })
  }

  return out
})

const anchorTone: Record<string, string> = {
  good: 'border-[#A9E2CB] bg-[#E8F8F1] text-[#0C7A56]',
  bad: 'border-[#F1C9C4] bg-[#FDEDEB] text-[#A32D2D]',
  neutral: 'border-[#DCE3EC] bg-[#F3F6FA] text-[#5B6B82]',
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

/** 详情页用：把「为什么缺分」讲清，避免用户以为评分算错。 */
const missingWeight = computed(() => props.offer.max_total - props.offer.scored_max)
</script>

<template>
  <div class="overflow-hidden rounded-xl border" :class="offer.vetoed ? 'border-[#F1C9C4]' : 'border-[#E1EAF8]'">
    <!-- 一票否决红条：优先级最高，必须压在分数之上 -->
    <div v-if="offer.vetoed" class="bg-[#FDEDEB] px-3 py-2.5">
      <div class="flex items-start gap-2">
        <AlertOctagon class="mt-[1px] h-4 w-4 shrink-0 text-[#C0392B]" :stroke-width="2.4" />
        <div class="min-w-0">
          <p class="text-[12px] font-black leading-none text-[#A32D2D]">
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
      <!-- ① 总评分 + 评级 + 两个价格锚点：这一行是整块面板的结论 -->
      <div class="flex items-start gap-2.5">
        <div class="flex shrink-0 flex-col items-center">
          <div class="flex items-baseline gap-0.5">
            <span
              class="font-black leading-none tracking-tight"
              :class="[gradeTone.text, isFull ? 'text-[44px]' : 'text-[32px]', isScoreVoid ? 'opacity-45' : '']"
            >
              {{ offer.total ?? '—' }}
            </span>
            <span class="text-[10px] font-bold leading-none text-[#94A2B8]">/100</span>
          </div>
          <!-- 评级文字只在详情页显示：卡片右上角已有同源徽标，
               重复显示会把价格 chip 挤到窄列里换行，反而更难读。 -->
          <span
            v-if="isFull"
            class="mt-1 inline-flex items-center rounded border px-1.5 py-[2px] text-[10px] font-black leading-none"
            :class="gradeTone.badge"
          >
            {{ gradeTone.label }}
          </span>
        </div>

        <div class="min-w-0 flex-1">
          <!-- 价格锚点 chips 必须占**整行**宽度。
               曾经把它挤在徽标右侧的窄列里，两个 chip 一换行就被压成
               两行三截，反而比不显示更难读。 -->
          <div v-if="priceAnchors.length" class="flex flex-wrap items-center gap-1">
            <span
              v-for="anchor in priceAnchors"
              :key="anchor.key"
              class="inline-flex items-center gap-0.5 whitespace-nowrap rounded border px-1.5 py-[3px] text-[10.5px] font-bold leading-none"
              :class="anchorTone[anchor.tone]"
              :title="anchor.hint"
            >
              <span class="font-semibold opacity-75">{{ anchor.label }}</span>
              <TrendingDown v-if="anchor.icon === 'down'" class="h-2.5 w-2.5" :stroke-width="2.8" />
              <TrendingUp v-else-if="anchor.icon === 'up'" class="h-2.5 w-2.5" :stroke-width="2.8" />
              <Minus v-else class="h-2.5 w-2.5" :stroke-width="2.8" />
              <b class="font-black">{{ anchor.value }}</b>
            </span>
          </div>
          <!-- 没配锚点时明确说出来，不能让人以为「性价比 0 分」 -->
          <div v-else-if="!offer.value_judged" class="rounded border border-[#F0DCA4] bg-[#FFF8E4] px-1.5 py-[3px]">
            <span class="text-[10px] font-bold leading-[1.35] text-[#9A6A08]">
              未配置全新价 · {{ offer.weights.value_vs_new }} 分未计
            </span>
          </div>

          <!-- 分数不作数的原因，或有效满分的说明 -->
          <p v-if="isScoreVoid" class="mt-1 text-[10px] font-bold leading-[1.4] text-[#A32D2D]">
            {{ voidReason }}
          </p>
          <p
            v-else-if="hasPartialInfo"
            class="mt-1 text-[10px] leading-[1.4] text-[#8B9AB0]"
            :title="`固定分母 100，缺项按 0 计，不做重标定：缺项就是拿不到分`"
          >
            定价可判 {{ offer.scored_max }}/100（缺 {{ missingWeight }} 分未计）
          </p>
        </div>
      </div>

      <!-- ② 两个价格维度：单独成组，因为它们占了 55 分 -->
      <div class="mt-2.5 space-y-1.5">
        <div v-for="dim in priceDims" :key="dim.key" class="flex items-center gap-2">
          <span
            class="shrink-0 font-bold leading-none"
            :class="[isFull ? 'w-[58px] text-[11px]' : 'w-[52px] text-[10.5px]', dim.scored ? 'text-[#4A5C75]' : 'text-[#AEBACA]']"
            :title="`${dim.label}（满分 ${dim.max} 分）`"
          >
            {{ dim.label }}
          </span>
          <div
            class="min-w-0 flex-1 overflow-hidden rounded-full"
            :class="[isFull ? 'h-2' : 'h-[7px]', dim.scored ? 'bg-[#E2EAF6]' : 'bg-[#EEF2F7]']"
          >
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
            class="shrink-0 text-right font-black leading-none tabular-nums"
            :class="[isFull ? 'w-[42px] text-[11.5px]' : 'w-[38px] text-[10.5px]', valueTone(dim)]"
          >
            {{ dim.scored ? `${dim.value}/${dim.max}` : '不可判' }}
          </span>
        </div>
      </div>

      <!-- ③ 其余四维：与价格组用分隔线隔开，避免「六维等权」的误解 -->
      <div class="mt-2 space-y-1.5 border-t border-dashed border-[#DDE7F5] pt-2">
        <div v-for="dim in otherDims" :key="dim.key" class="flex items-center gap-2">
          <span
            class="shrink-0 font-bold leading-none"
            :class="[isFull ? 'w-[58px] text-[11px]' : 'w-[52px] text-[10.5px]', dim.scored ? 'text-[#6B7C93]' : 'text-[#AEBACA]']"
            :title="`${dim.label}（满分 ${dim.max} 分）`"
          >
            {{ dim.label }}
          </span>
          <div
            class="min-w-0 flex-1 overflow-hidden rounded-full"
            :class="[isFull ? 'h-2' : 'h-[7px]', dim.scored ? 'bg-[#E2EAF6]' : 'bg-[#EEF2F7]']"
          >
            <span
              v-if="dim.scored"
              class="block h-full rounded-full transition-[width] duration-500"
              :class="barTone(dim)"
              :style="{ width: `${barWidth(dim)}%` }"
            ></span>
            <span v-else class="block h-full w-full rounded-full bg-[repeating-linear-gradient(45deg,#DFE6F0_0_3px,transparent_3px_6px)]"></span>
          </div>
          <span
            class="shrink-0 text-right font-black leading-none tabular-nums"
            :class="[isFull ? 'w-[42px] text-[11.5px]' : 'w-[38px] text-[10.5px]', valueTone(dim)]"
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

      <!-- ④ 辅助加减分：命中才显示，没命中不占位 -->
      <div v-if="activeAdjustments.length" class="mt-2 flex flex-wrap items-center gap-1">
        <span class="text-[9.5px] font-bold text-[#94A2B8]">附加</span>
        <span
          v-for="item in activeAdjustments"
          :key="item.key"
          class="inline-flex items-center gap-0.5 rounded border px-1 py-[1.5px] text-[10px] font-black leading-none"
          :class="
            item.delta > 0
              ? 'border-[#A9E2CB] bg-[#E8F8F1] text-[#0C7A56]'
              : 'border-[#F1C9C4] bg-[#FDEDEB] text-[#A32D2D]'
          "
          :title="item.label"
        >
          <TrendingUp v-if="item.delta > 0" class="h-2.5 w-2.5" :stroke-width="2.8" />
          <TrendingDown v-else class="h-2.5 w-2.5" :stroke-width="2.8" />
          {{ item.delta > 0 ? '+' : '' }}{{ item.delta }}
        </span>
        <span
          v-if="offer.adjustment_total !== offer.adjustment_intent"
          class="text-[9.5px] text-[#94A2B8]"
          title="辅助分被缺项上限吃掉了一部分：拿不到的分不能靠时效性补回来"
        >
          （实计 {{ offer.adjustment_total >= 0 ? '+' : '' }}{{ offer.adjustment_total }}）
        </span>
      </div>

      <!-- ⑤ 详情页：逐条依据，把「凭什么给这个分」讲透 -->
      <div v-if="isFull" class="mt-3 space-y-1.5 border-t border-[#E7EEF9] pt-2.5">
        <p v-if="offer.grade_note" class="rounded bg-white/70 px-2 py-1.5 text-[10.5px] leading-[1.5] text-[#7B8AA3]">
          {{ offer.grade_note }}
        </p>
        <div v-for="dim in dims" :key="`r-${dim.key}`" class="flex gap-1.5 text-[10.5px] leading-[1.5]">
          <span class="w-[58px] shrink-0 font-bold text-[#7B8AA3]">{{ dim.label }}</span>
          <span class="min-w-0 flex-1 text-[#5B6B82]">
            {{ dim.reason }}
            <span v-if="dim.inferred" class="ml-1 rounded bg-[#FFF6E5] px-1 py-[1px] text-[9.5px] font-bold text-[#A57A29]">推定</span>
          </span>
        </div>
        <!-- 命中的辅助分也要列出来，否则「总分比六维之和高」无解释 -->
        <div v-for="item in activeAdjustments" :key="`a-${item.key}`" class="flex gap-1.5 text-[10.5px] leading-[1.5]">
          <span class="w-[58px] shrink-0 font-bold text-[#7B8AA3]">附加</span>
          <span class="min-w-0 flex-1" :class="item.delta > 0 ? 'text-[#0C7A56]' : 'text-[#A32D2D]'">
            {{ item.label }} {{ item.delta > 0 ? '+' : '' }}{{ item.delta }}
          </span>
        </div>
        <p v-if="offer.new_price_note" class="pt-1 text-[9.5px] leading-[1.5] text-[#B6C2D2]">
          全新价锚点来源：{{ offer.new_price_note }}
        </p>
      </div>
    </div>
  </div>
</template>
