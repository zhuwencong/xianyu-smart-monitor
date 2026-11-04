<script setup lang="ts">
import { ref } from 'vue'
import { ArrowRight } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import AboutDialog from '@/components/layout/AboutDialog.vue'

const { t } = useI18n()

/** 页脚只保留一条很轻的入口，公司介绍与 Q&A 都放在弹窗里。 */
const isAboutOpen = ref(false)
</script>

<template>
  <footer class="mx-auto w-full max-w-[1600px] px-5 pb-8 pt-2 sm:px-7 lg:px-10">
    <div
      class="flex flex-col items-center gap-2 border-t border-[#E5EAF4] pt-5 text-[11px] font-medium text-[#9AA7BA] sm:flex-row sm:justify-between"
    >
      <span>{{ t('about.copyright') }}</span>
      <button
        type="button"
        class="group inline-flex items-center gap-1 rounded text-[11.5px] font-semibold text-[#8794A8] transition-colors hover:text-[#2360E6] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2360E6]/30 focus-visible:ring-offset-2"
        @click="isAboutOpen = true"
      >
        {{ t('about.title') }}
        <ArrowRight class="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
      </button>
    </div>

    <AboutDialog :open="isAboutOpen" @update:open="isAboutOpen = $event" />
  </footer>
</template>
