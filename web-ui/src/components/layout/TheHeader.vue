<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'
import DashboardTaskSearch from '@/components/layout/DashboardTaskSearch.vue'
import LocaleToggle from '@/components/layout/LocaleToggle.vue'
import SessionLogout from '@/components/layout/SessionLogout.vue'
import {
  Bell,
  Search,
  UserCircle,
  HelpCircle,
  Menu
} from 'lucide-vue-next'
import brandLogoUrl from '@/assets/brand-logo.webp'
import brandMarkUrl from '@/assets/brand-mark.png'
import { useMobileNav } from '@/composables/useMobileNav'
import { useI18n } from 'vue-i18n'

const router = useRouter()
const route = useRoute()
const { toggleMobileNav } = useMobileNav()
const inactiveSearchValue = ref('')
const { t } = useI18n()

const isDashboard = computed(() => route.name === 'Dashboard')

function goAccounts() {
  router.push('/accounts')
}

function goNotifications() {
  router.push({ name: 'Settings', query: { tab: 'notifications' } })
}

function goPrompts() {
  router.push({ name: 'Settings', query: { tab: 'prompts' } })
}
</script>

<template>
  <header class="sticky top-0 z-[100] flex h-[72px] items-center justify-between px-4 sm:px-6">
    <RouterLink
      to="/dashboard"
      class="group flex shrink-0 items-center gap-3 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      :aria-label="t('header.goHome')"
    >
      <img :src="brandMarkUrl" alt="创客星辰 AI" class="h-11 w-11 object-contain sm:hidden" />
      <img :src="brandLogoUrl" alt="创客星辰 AI · Maker Cosmos AI" class="hidden h-12 w-auto select-none sm:block" draggable="false" />
      <span class="hidden rounded-md border border-blue-100 bg-blue-50 px-2 py-1 text-[9px] font-extrabold tracking-[0.16em] text-blue-600 xl:inline-block">
        CONSOLE
      </span>
    </RouterLink>

    <div class="mx-6 hidden max-w-lg flex-grow md:flex lg:mx-10">
      <DashboardTaskSearch v-if="isDashboard" />
      <div v-else class="group relative w-full">
        <Search class="absolute left-3.5 top-1/2 w-4 h-4 -translate-y-1/2 text-slate-400" />
        <input
          type="text"
          v-model="inactiveSearchValue"
          readonly
          aria-disabled="true"
          :placeholder="t('header.searchUnavailable')"
          class="h-10 w-full rounded-xl border border-slate-200/80 bg-slate-50/80 pl-10 pr-4 text-sm text-slate-500 outline-none"
        />
        <kbd class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded border border-slate-200 bg-white px-1.5 py-0.5 font-sans text-[10px] text-slate-400 shadow-sm">
          /
        </kbd>
      </div>
    </div>

    <div class="flex items-center gap-1 sm:gap-2">
      <LocaleToggle />
      <SessionLogout />

      <div class="hidden items-center gap-1 sm:flex">
        <Button
          variant="ghost"
          size="icon"
          class="rounded-xl text-slate-500 hover:bg-blue-50 hover:text-primary"
          :aria-label="t('header.openNotifications')"
          @click="goNotifications"
        >
          <Bell class="h-5 w-5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          class="rounded-xl text-slate-500 hover:bg-blue-50 hover:text-primary"
          :aria-label="t('header.openPrompts')"
          @click="goPrompts"
        >
          <HelpCircle class="h-5 w-5" />
        </Button>
      </div>

      <div class="mx-1 hidden h-7 w-px bg-slate-200 lg:block"></div>

      <Button
        variant="ghost"
        class="hidden items-center gap-2 rounded-xl px-2 hover:bg-blue-50 lg:flex"
        :aria-label="t('header.openAccounts')"
        @click="goAccounts"
      >
        <div class="flex h-9 w-9 items-center justify-center rounded-xl border border-blue-100 bg-gradient-to-br from-blue-50 to-indigo-100">
          <UserCircle class="h-5 w-5 text-blue-600" />
        </div>
        <div class="hidden text-left xl:block">
          <p class="text-xs font-extrabold leading-none text-slate-700">Maker Cosmos</p>
          <p class="mt-1 text-[10px] font-medium text-slate-400">{{ t('header.accountManagement') }}</p>
        </div>
      </Button>

      <Button
        variant="ghost"
        size="icon"
        class="rounded-xl hover:bg-blue-50 md:hidden"
        :aria-label="t('header.openNavigation')"
        @click="toggleMobileNav"
      >
        <Menu class="h-6 w-6 text-slate-700" />
      </Button>
    </div>
  </header>
</template>
