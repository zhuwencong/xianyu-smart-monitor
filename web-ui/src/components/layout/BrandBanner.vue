<script setup lang="ts">
import { Sparkles } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import bannerUrl from '@/assets/brand-banner.webp'
import brandLogoUrl from '@/assets/brand-logo.webp'
import brandHeroUrl from '@/assets/brand-hero.webp'

withDefaults(defineProps<{
  variant?: 'dashboard' | 'login'
}>(), {
  variant: 'dashboard',
})

const { t } = useI18n()
</script>

<template>
  <section
    v-if="variant === 'dashboard'"
    class="relative overflow-hidden rounded-[28px] border border-blue-100 bg-[#f8fbff] shadow-[0_24px_70px_-42px_rgba(30,64,175,0.55)]"
  >
    <img
      :src="bannerUrl"
      alt="创客星辰 AI · Maker Cosmos AI"
      class="absolute inset-0 h-full w-full select-none object-cover object-[68%_center]"
      draggable="false"
      fetchpriority="high"
    />
    <div class="absolute inset-0 bg-white/90 md:bg-gradient-to-r md:from-[#f8fbff] md:via-[#f8fbff]/95 md:to-transparent"></div>
    <div class="absolute -left-20 -top-24 h-64 w-64 rounded-full border-[40px] border-blue-100/40"></div>

    <div class="relative z-10 flex min-h-[290px] items-center p-6 sm:p-8 lg:min-h-[310px] lg:p-10">
      <div class="max-w-2xl">
        <div class="mb-5 inline-flex items-center gap-2 rounded-full border border-blue-200/80 bg-white/85 px-3 py-1.5 text-[10px] font-extrabold tracking-[0.16em] text-blue-700 shadow-sm backdrop-blur sm:text-xs">
          <Sparkles class="h-4 w-4 text-amber-500" />
          MAKER COSMOS AI
          <span class="hidden h-3 w-px bg-blue-200 sm:block"></span>
          <span class="hidden text-blue-400 sm:inline">INTELLIGENT CONSOLE</span>
        </div>
        <h1 class="max-w-2xl text-3xl font-black leading-tight tracking-tight text-[#102a56] sm:text-4xl lg:text-[42px]">
          <span class="block">{{ t('dashboard.heroTitleLine1') }}</span>
          <span class="block">{{ t('dashboard.heroTitleLine2') }}</span>
        </h1>
        <p class="mt-4 max-w-lg text-sm font-medium leading-7 text-slate-600 sm:text-base">
          {{ t('dashboard.heroDescription') }}
        </p>
        <div class="mt-7 flex flex-col gap-3 sm:flex-row">
          <slot />
        </div>
      </div>
    </div>
  </section>

  <section v-else class="relative flex h-full min-h-[620px] flex-col overflow-hidden bg-gradient-to-br from-[#071d49] via-[#0b3988] to-[#1264d8] p-8 xl:p-10">
    <div class="absolute -right-24 -top-24 h-72 w-72 rounded-full border-[45px] border-white/5"></div>
    <div class="absolute -bottom-32 -left-24 h-80 w-80 rounded-full bg-cyan-300/10 blur-3xl"></div>
    <div class="absolute inset-0 opacity-30 [background-image:radial-gradient(#ffffff_0.8px,transparent_0.8px)] [background-size:28px_28px]"></div>

    <img
      :src="brandLogoUrl"
      alt="创客星辰 AI"
      class="relative z-10 w-48 rounded-2xl bg-white/95 p-2 shadow-xl"
    />

    <div class="relative z-10 my-auto flex items-center justify-center py-6">
      <div class="pointer-events-none absolute h-[300px] w-[300px] rounded-full bg-cyan-300/20 blur-[85px]"></div>
      <div class="pointer-events-none absolute h-[340px] w-[340px] rounded-full border border-white/10"></div>
      <img
        :src="brandHeroUrl"
        alt="创客星辰 AI 机器人"
        width="1200"
        height="716"
        class="relative h-auto w-full max-w-[520px] drop-shadow-[0_26px_42px_rgba(2,8,35,0.45)]"
        draggable="false"
      />
    </div>

    <div class="relative z-10 mt-auto text-white">
      <div class="mb-4 flex items-center gap-2 text-xs font-bold tracking-[0.22em] text-blue-200">
        <Sparkles class="h-4 w-4 text-amber-400" />
        MAKER COSMOS AI
      </div>
      <h2 class="max-w-md text-3xl font-black leading-tight tracking-tight">
        {{ t('login.brandSlogan') }}
      </h2>
      <p class="mt-3 max-w-sm text-sm leading-6 text-blue-100">
        {{ t('login.brandDescription') }}
      </p>
    </div>
  </section>
</template>
