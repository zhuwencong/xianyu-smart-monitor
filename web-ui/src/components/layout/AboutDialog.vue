<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ExternalLink, Mail, MapPin, Phone, Sparkles } from 'lucide-vue-next'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'
import brandMarkUrl from '@/assets/brand-mark.png'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (event: 'update:open', value: boolean): void }>()

const { t } = useI18n()

/** 公司官网：弹窗里再点一次才跳转。 */
const OFFICIAL_SITE = 'https://ckxingchen.cn/'
/** 商务邮箱（不放进 i18n，避免 @ 被当成消息语法）。 */
const CONTACT_EMAIL = 'zhuwencong@ckxingchen.cn'

const faqs = computed(() => [
  { q: t('support.faq.custom.q'), a: t('support.faq.custom.a') },
  { q: t('support.faq.integration.q'), a: t('support.faq.integration.a') },
  { q: t('support.faq.business.q'), a: t('support.faq.business.a') },
  { q: t('support.faq.hardware.q'), a: t('support.faq.hardware.a') },
  { q: t('support.faq.process.q'), a: t('support.faq.process.a') },
])

const phoneHref = computed(() => `tel:${t('support.contactPhone').replace(/\s+/g, '')}`)
const emailHref = computed(() => `mailto:${CONTACT_EMAIL}`)
</script>

<template>
  <Dialog :open="props.open" @update:open="(value: boolean) => emit('update:open', value)">
    <DialogContent class="flex max-h-[86vh] max-w-2xl flex-col gap-0 overflow-hidden p-0 sm:rounded-2xl">
      <div class="relative shrink-0 border-b border-[#EEF2F8] bg-[#F7FAFF] px-5 pb-5 pt-6 pr-12 sm:px-6">
        <div class="flex items-start gap-3.5">
          <span
            class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-[#E5EDFB] bg-white shadow-[0_8px_18px_-14px_rgba(15,35,70,0.5)]"
          >
            <img :src="brandMarkUrl" alt="" class="h-9 w-9 object-contain" draggable="false" />
          </span>
          <div class="min-w-0">
            <p
              class="inline-flex items-center gap-1.5 rounded-full border border-blue-100 bg-blue-50 px-2.5 py-1 text-[10px] font-extrabold tracking-[0.16em] text-blue-700"
            >
              <Sparkles class="h-3 w-3 text-amber-500" />
              {{ t('about.label') }}
            </p>
            <DialogTitle class="mt-2 text-[20px] font-black tracking-tight text-[#102A56]">
              {{ t('about.title') }}
            </DialogTitle>
            <DialogDescription class="mt-1 text-[12.5px] font-bold text-[#2360E6]">
              {{ t('about.company') }}
              <span class="font-semibold text-[#8794A8]">· {{ t('about.brand') }}</span>
            </DialogDescription>
          </div>
        </div>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-6">
        <p class="text-[13px] leading-7 text-[#46566F]">{{ t('about.description') }}</p>
        <p class="mt-3 flex items-start gap-1.5 text-[12px] leading-5 text-[#8794A8]">
          <MapPin class="mt-0.5 h-3.5 w-3.5 shrink-0" :stroke-width="2" />
          {{ t('about.address') }}
        </p>

        <div class="mt-5 border-t border-[#EEF2F8] pt-4">
          <h3 class="text-[13px] font-black text-[#102A56]">{{ t('support.title') }}</h3>
          <p class="mt-1 text-[11.5px] leading-5 text-[#8794A8]">{{ t('support.description') }}</p>
          <p class="mt-3 text-[11px] font-black tracking-[0.16em] text-[#8794A8]">{{ t('support.faqTitle') }}</p>
          <div class="mt-2 space-y-2">
            <div
              v-for="(item, index) in faqs"
              :key="item.q"
              class="rounded-xl border border-[#E9EEF6] bg-white px-4 py-3"
            >
              <p class="flex items-start gap-2.5 text-[13px] font-bold leading-6 text-[#1A2F52]">
                <span
                  class="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-[#EEF4FF] text-[10px] font-black text-[#2360E6]"
                >
                  Q{{ index + 1 }}
                </span>
                <span>{{ item.q }}</span>
              </p>
              <p class="mt-1.5 pl-[30px] text-[12.5px] leading-6 text-[#5B6B84]">{{ item.a }}</p>
            </div>
          </div>
        </div>

        <p class="mt-4 border-t border-[#EEF2F8] pt-3 text-[11px] leading-5 text-[#98A4B7]">
          {{ t('about.copyright') }}
        </p>
      </div>

      <div class="shrink-0 border-t border-[#EEF2F8] bg-white px-5 py-4 sm:px-6">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div class="min-w-0 space-y-1.5">
            <p class="text-[12.5px] font-black text-[#1A2F52]">{{ t('support.contactName') }}</p>
            <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-[#5B6B84]">
              <a :href="phoneHref" class="inline-flex items-center gap-1.5 transition-colors hover:text-[#2360E6]">
                <Phone class="h-3.5 w-3.5 text-[#7B8AA3]" />
                {{ t('support.contactPhone') }}
              </a>
              <a :href="emailHref" class="inline-flex items-center gap-1.5 transition-colors hover:text-[#2360E6]">
                <Mail class="h-3.5 w-3.5 text-[#7B8AA3]" />
                {{ CONTACT_EMAIL }}
              </a>
            </div>
          </div>
          <a
            :href="OFFICIAL_SITE"
            target="_blank"
            rel="noopener noreferrer"
            class="group inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-[#2360E6] px-4 py-2.5 text-[13px] font-bold text-white shadow-[0_14px_30px_-16px_rgba(35,96,230,0.9)] transition-all hover:-translate-y-0.5 hover:bg-[#1748B8] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2360E6]/35 focus-visible:ring-offset-2"
          >
            {{ t('about.websiteCta') }}
            <ExternalLink
              class="h-4 w-4 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
              :stroke-width="2.2"
            />
          </a>
        </div>
        <p class="mt-2 text-[11px] leading-5 text-[#98A4B7]">{{ t('support.note') }}</p>
      </div>
    </DialogContent>
  </Dialog>
</template>
