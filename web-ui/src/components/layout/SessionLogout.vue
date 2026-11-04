<script setup lang="ts">
import { ref } from 'vue'
import { useAuth } from '@/composables/useAuth'
import { Button } from '@/components/ui/button'
import { LogOut } from 'lucide-vue-next'

const { logout } = useAuth()
const pending = ref(false)

async function handleLogout() {
  pending.value = true
  try {
    await logout()
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <Button variant="ghost" size="sm" :disabled="pending" aria-label="退出登录" @click="handleLogout">
    <LogOut class="h-4 w-4 sm:mr-2" />
    <span class="hidden sm:inline">{{ pending ? '正在退出' : '退出登录' }}</span>
  </Button>
</template>
