<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AlertTriangle,
  Building2,
  ChevronDown,
  ChevronRight,
  LogOut,
  MonitorPlay,
  PackageSearch,
  Settings2,
  UserRound,
} from 'lucide-vue-next'
import brandLogoUrl from '@/assets/brand-logo-compact.webp'
import brandMarkUrl from '@/assets/brand-mark.png'
import AboutDialog from '@/components/layout/AboutDialog.vue'
import { useWorkbench } from '@/composables/useWorkbench'
import { useAuth } from '@/composables/useAuth'

const route = useRoute()
const router = useRouter()
const { username, isLocalAuto, logout } = useAuth()
const { summary, isManagementOpen, openManagement } = useWorkbench()

const isMenuOpen = ref(false)
const isAboutOpen = ref(false)
const menuRoot = ref<HTMLElement | null>(null)

const navItems = [
  { to: '/results', label: '候选商品', icon: PackageSearch },
  { to: '/tasks', label: '监控任务', icon: MonitorPlay },
]

const pendingCount = computed(() => summary.value?.pending_count ?? 0)
const userInitial = computed(() => (isLocalAuto.value ? '本' : (username.value || 'M').slice(0, 1).toUpperCase()))
const displayName = computed(() => (isLocalAuto.value ? '本机用户' : username.value || 'Maker Cosmos'))

function isActive(path: string) {
  return route.path === path
}

function handleDocumentClick(event: MouseEvent) {
  if (!menuRoot.value?.contains(event.target as Node)) {
    isMenuOpen.value = false
  }
}

function handleEscape(event: KeyboardEvent) {
  if (event.key === 'Escape') isMenuOpen.value = false
}

function goSettings() {
  isMenuOpen.value = false
  router.push({ name: 'Settings' })
}

function goAccounts() {
  isMenuOpen.value = false
  router.push({ name: 'Accounts' })
}

function openAbout() {
  isMenuOpen.value = false
  isAboutOpen.value = true
}

async function handleLogout() {
  isMenuOpen.value = false
  await logout()
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick)
  document.addEventListener('keydown', handleEscape)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)
  document.removeEventListener('keydown', handleEscape)
})
</script>

<template>
  <header class="sticky top-0 z-[80] border-b border-[#E5EAF4] bg-white/95 backdrop-blur-xl">
    <div class="mx-auto flex h-[68px] max-w-[1600px] items-center gap-5 px-5 sm:px-7 lg:px-10">
      <RouterLink
        to="/results"
        class="group flex shrink-0 items-center gap-2.5 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2360E6]/40"
        aria-label="创客星辰 AI · 候选商品"
      >
        <img :src="brandMarkUrl" alt="" class="h-10 w-10 object-contain sm:hidden" draggable="false" />
        <img
          :src="brandLogoUrl"
          alt="创客星辰 AI · Maker Cosmos AI"
          class="hidden h-10 w-auto select-none sm:block"
          draggable="false"
        />
      </RouterLink>

      <span class="hidden h-7 w-px bg-[#E7ECF6] lg:block" aria-hidden="true"></span>

      <nav class="hidden h-full items-stretch gap-1 sm:flex" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="relative flex items-center gap-2 px-4 text-[15px] font-bold transition-colors lg:px-5"
          :class="isActive(item.to) ? 'text-[#2360E6]' : 'text-[#3B4A66] hover:text-[#2360E6]'"
        >
          <component :is="item.icon" class="h-[18px] w-[18px]" :stroke-width="isActive(item.to) ? 2.4 : 2" />
          <span>{{ item.label }}</span>
          <span
            v-if="isActive(item.to)"
            class="absolute inset-x-3 bottom-0 h-[3px] rounded-t-full bg-[#2360E6]"
          ></span>
        </RouterLink>
      </nav>

      <div class="ml-auto flex items-center gap-1.5 sm:gap-2.5">
        <button
          type="button"
          class="group inline-flex h-10 items-center gap-2 rounded-[10px] border px-2.5 text-[13px] font-bold transition-all sm:px-3.5"
          :class="pendingCount > 0
            ? 'border-[#F6D9A8] bg-[#FFF9EE] text-[#A75B09] hover:border-[#EDC078] hover:bg-[#FFF3DB]'
            : 'border-[#E6EAF2] bg-white text-[#64748B] hover:border-[#C9D5E8] hover:text-[#334155]'"
          :aria-label="`需处理 ${pendingCount} 项`"
          @click="openManagement('overview')"
        >
          <AlertTriangle class="h-4 w-4" :stroke-width="2.2" />
          <span class="hidden sm:inline">需处理</span>
          <span
            v-if="pendingCount > 0"
            class="inline-flex min-w-[20px] items-center justify-center rounded-md bg-[#F3B44B] px-1.5 text-[11px] font-black leading-5 text-white"
          >
            {{ pendingCount }}
          </span>
        </button>

        <button
          type="button"
          class="inline-flex h-10 items-center gap-2 rounded-[10px] px-2.5 text-[14px] font-bold transition-colors sm:px-3"
          :class="isManagementOpen ? 'bg-[#EEF4FF] text-[#2360E6]' : 'text-[#3B4A66] hover:bg-[#F3F6FC] hover:text-[#2360E6]'"
          aria-label="打开管理"
          @click="openManagement('overview')"
        >
          <Settings2 class="h-[19px] w-[19px]" :stroke-width="2.2" />
          <span class="hidden md:inline">管理</span>
        </button>

        <span class="hidden h-7 w-px bg-[#E7ECF6] sm:block" aria-hidden="true"></span>

        <div ref="menuRoot" class="relative">
          <button
            type="button"
            class="flex h-10 items-center gap-1.5 rounded-full pl-0.5 pr-1 transition-colors hover:bg-[#F3F6FC]"
            aria-label="账户菜单"
            :aria-expanded="isMenuOpen"
            @click.stop="isMenuOpen = !isMenuOpen"
          >
            <span
              class="flex h-8 w-8 items-center justify-center rounded-full border border-[#D8E3F7] bg-gradient-to-br from-[#EAF1FF] to-[#DCE9FF] text-[13px] font-black text-[#2360E6]"
            >
              {{ userInitial }}
            </span>
            <ChevronDown
              class="h-3.5 w-3.5 text-[#7B8AA3] transition-transform"
              :class="{ 'rotate-180': isMenuOpen }"
            />
          </button>

          <transition name="dropdown">
            <div
              v-if="isMenuOpen"
              class="absolute right-0 top-[48px] z-[90] w-[192px] overflow-hidden rounded-xl border border-[#E3E9F4] bg-white p-1.5 shadow-[0_18px_50px_-18px_rgba(15,35,70,0.35)]"
            >
              <div class="px-3 py-2">
                <p class="truncate text-[13px] font-bold text-[#152A4E]">{{ displayName }}</p>
                <p class="mt-0.5 text-[11px] text-[#8B98AD]">{{ isLocalAuto ? '本机免登录模式' : '本机管理账号' }}</p>
              </div>
              <div class="my-1 h-px bg-[#EEF1F7]"></div>
              <button
                type="button"
                class="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] font-semibold text-[#3B4A66] hover:bg-[#F4F7FC]"
                @click="goAccounts"
              >
                <UserRound class="h-4 w-4 text-[#7B8AA3]" />
                账号连接
              </button>
              <button
                type="button"
                class="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] font-semibold text-[#3B4A66] hover:bg-[#F4F7FC]"
                @click="goSettings"
              >
                <Settings2 class="h-4 w-4 text-[#7B8AA3]" />
                完整设置
              </button>
              <button
                type="button"
                class="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] font-semibold text-[#3B4A66] hover:bg-[#F4F7FC]"
                @click="openAbout"
              >
                <Building2 class="h-4 w-4 text-[#7B8AA3]" />
                关于我们
                <ChevronRight class="ml-auto h-3.5 w-3.5 text-[#B5C2D5]" />
              </button>
              <div class="my-1 h-px bg-[#EEF1F7]"></div>
              <button
                v-if="!isLocalAuto"
                type="button"
                class="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] font-semibold text-[#B42318] hover:bg-[#FEF3F2]"
                @click="handleLogout"
              >
                <LogOut class="h-4 w-4" />
                退出登录
              </button>
              <p v-else class="px-3 py-2 text-[11px] leading-5 text-[#8B98AD]">
                本机访问免登录，无需退出。需要账号密码时开启严格模式。
              </p>
            </div>
          </transition>
        </div>
      </div>
    </div>

    <nav class="flex h-11 items-stretch gap-1 border-t border-[#EEF2F8] px-4 sm:hidden" aria-label="主导航">
      <RouterLink
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        class="relative flex flex-1 items-center justify-center gap-1.5 text-[13px] font-bold"
        :class="isActive(item.to) ? 'text-[#2360E6]' : 'text-[#64748B]'"
      >
        <component :is="item.icon" class="h-4 w-4" />
        {{ item.label }}
        <span v-if="isActive(item.to)" class="absolute inset-x-5 bottom-0 h-[2px] rounded-full bg-[#2360E6]"></span>
      </RouterLink>
    </nav>

    <AboutDialog :open="isAboutOpen" @update:open="isAboutOpen = $event" />
  </header>
</template>

<style scoped>
.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity 0.14s ease, transform 0.14s ease;
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.98);
}
</style>
