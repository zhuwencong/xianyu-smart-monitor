<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  ArrowUpRight,
  Bookmark,
  Check,
  CircleAlert,
  CircleCheck,
  CircleHelp,
  MapPin,
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
            <p class="mt-2 text-[26px] font-black leading-none text-[#E03838]">{{ candidate.price_display }}</p>
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
              <div class="mt-3 grid grid-cols-4 gap-3">
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
