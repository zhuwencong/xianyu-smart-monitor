<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuth } from '@/composables/useAuth'
import LocaleToggle from '@/components/layout/LocaleToggle.vue'
import BrandBanner from '@/components/layout/BrandBanner.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ArrowRight, ShieldCheck, Sparkles } from 'lucide-vue-next'
import brandLogoUrl from '@/assets/brand-logo.webp'
import { useI18n } from 'vue-i18n'

const username = ref('admin')
const password = ref('admin123')
const isLoading = ref(false)
const error = ref('')

const { login } = useAuth()
const router = useRouter()
const route = useRoute()
const { t } = useI18n()

async function handleLogin() {
  if (!username.value || !password.value) {
    error.value = t('login.errors.missingCredentials')
    return
  }

  isLoading.value = true
  error.value = ''

  try {
    const success = await login(username.value, password.value)
    if (success) {
      const redirectPath = (route.query.redirect as string) || '/'
      router.push(redirectPath)
    } else {
      error.value = t('login.errors.invalidCredentials')
    }
  } catch (e) {
    error.value = t('login.errors.unexpected')
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="relative min-h-screen overflow-hidden bg-[#f3f7fd] px-4 py-6 sm:px-6 lg:px-8">
    <div aria-hidden="true" class="absolute inset-0">
      <div class="absolute -left-32 -top-32 h-96 w-96 rounded-full bg-blue-200/35 blur-[100px]"></div>
      <div class="absolute -bottom-40 -right-24 h-[480px] w-[480px] rounded-full bg-cyan-100/60 blur-[110px]"></div>
      <div class="absolute inset-0 opacity-40 [background-image:radial-gradient(#94b8ed_0.8px,transparent_0.8px)] [background-size:26px_26px]"></div>
    </div>

    <div class="absolute right-5 top-5 z-20 sm:right-8 sm:top-8">
      <LocaleToggle />
    </div>

    <div class="relative z-10 mx-auto flex min-h-[calc(100vh-3rem)] max-w-6xl items-center justify-center pb-6 pt-20 lg:py-8 lg:pt-8">
      <div class="grid w-full min-w-0 overflow-hidden rounded-[30px] border border-white/90 bg-white shadow-[0_35px_100px_-45px_rgba(30,64,175,0.5)] lg:grid-cols-[1.08fr_0.92fr]">
        <div class="hidden lg:block">
          <BrandBanner variant="login" />
        </div>

        <div class="flex min-w-0 items-center p-6 sm:p-10 lg:p-12">
          <div class="mx-auto w-full min-w-0 max-w-md">
            <img :src="brandLogoUrl" alt="创客星辰 AI · Maker Cosmos AI" class="mb-8 h-16 w-auto lg:hidden" />

            <div class="mb-4 inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-[10px] font-extrabold tracking-[0.16em] text-blue-700">
              <Sparkles class="h-3.5 w-3.5 text-amber-500" />
              MAKER COSMOS · AI CONSOLE
            </div>
            <h1 class="text-3xl font-black tracking-tight text-[#102a56]">{{ t('login.title') }}</h1>
            <p class="mt-3 text-sm leading-6 text-slate-500">{{ t('login.description') }}</p>

            <form class="mt-8 space-y-5" @submit.prevent="handleLogin">
              <div class="grid gap-2.5">
                <Label for="username" class="text-xs font-bold text-slate-600">{{ t('login.username') }}</Label>
                <Input
                  id="username"
                  v-model="username"
                  type="text"
                  placeholder="admin"
                  autocomplete="username"
                  class="h-12 rounded-xl border-slate-200 bg-slate-50/70 px-4 focus-visible:border-blue-400 focus-visible:bg-white focus-visible:ring-blue-100"
                  required
                />
              </div>
              <div class="grid gap-2.5">
                <Label for="password" class="text-xs font-bold text-slate-600">{{ t('login.password') }}</Label>
                <Input
                  id="password"
                  v-model="password"
                  type="password"
                  autocomplete="current-password"
                  class="h-12 rounded-xl border-slate-200 bg-slate-50/70 px-4 focus-visible:border-blue-400 focus-visible:bg-white focus-visible:ring-blue-100"
                  required
                />
              </div>
              <div v-if="error" class="rounded-xl border border-rose-100 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-600" role="alert">
                {{ error }}
              </div>
              <Button
                class="h-12 w-full rounded-xl font-bold shadow-[0_14px_30px_-14px_rgba(18,95,224,0.85)]"
                type="submit"
                :disabled="isLoading"
              >
                {{ isLoading ? t('login.submitting') : t('login.submit') }}
                <ArrowRight v-if="!isLoading" class="ml-1 h-4 w-4" />
              </Button>
            </form>

            <div class="mt-8 flex items-center justify-center gap-2 border-t border-slate-100 pt-6 text-[11px] font-medium text-slate-400">
              <ShieldCheck class="h-4 w-4 text-blue-400" />
              Maker Cosmos AI · Secure Console
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
