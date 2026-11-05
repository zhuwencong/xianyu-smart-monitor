<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { listAccounts, getAccount, createAccount, updateAccount, deleteAccount, launchAccountLogin, type AccountItem } from '@/api/accounts'
import { getAccountHealth, type AccountHealth } from '@/api/workbench'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { toast } from '@/components/ui/toast'
const { t } = useI18n()

const accounts = ref<AccountItem[]>([])
const healthMap = ref<Record<string, AccountHealth>>({})
const isLoading = ref(false)
const isSaving = ref(false)
const router = useRouter()
const route = useRoute()
const scanRequested = computed(() => route.query.action === 'scan')
const launchingAccount = ref('')

const isCreateDialogOpen = ref(false)
const isEditDialogOpen = ref(false)
const isDeleteDialogOpen = ref(false)

const newName = ref('')
const newContent = ref('')
const editName = ref('')
const editContent = ref('')
const deleteName = ref('')

async function fetchAccounts() {
  isLoading.value = true
  try {
    const [list, health] = await Promise.all([
      listAccounts(),
      getAccountHealth().catch(() => ({ items: [] as AccountHealth[] })),
    ])
    accounts.value = list
    healthMap.value = Object.fromEntries(health.items.map((item) => [item.name, item]))
  } catch (e) {
    toast({ title: t('accounts.toasts.loadFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    isLoading.value = false
  }
}

function healthOf(name: string): AccountHealth | null {
  return healthMap.value[name] || null
}

function statusClass(status?: string) {
  if (status === 'needs_update') return 'border-[#F0D3A2] bg-[#FFF8EC] text-[#A75B09]'
  if (status === 'warning') return 'border-[#F1C9C3] bg-[#FDF3F2] text-[#B03A2E]'
  return 'border-[#BFE8D7] bg-[#EAF8F2] text-[#0C7A56]'
}

function runTextClass(status?: string) {
  if (status === 'needs_update') return 'font-medium leading-relaxed text-[#A75B09]'
  if (status === 'warning') return 'font-medium leading-relaxed text-[#B03A2E]'
  return 'leading-relaxed text-[#6F849F]'
}

function runSummary(name: string): string {
  const health = healthOf(name)
  if (!health) return '暂无运行记录'
  if (health.status === 'needs_update') return health.reason || '请重新扫码登录'
  if (health.status === 'warning') {
    const when = health.last_run_label ? ` ${health.last_run_label}` : ''
    const why = health.last_run_reason ? `：${health.last_run_reason}` : ''
    return `上次运行失败${when}${why}（登录态本身有效）`
  }
  return health.last_success_label ? `最近运行正常 ${health.last_success_label}` : '暂无运行记录'
}

async function launchLogin(account?: string) {
  const key = account || 'auto'
  if (launchingAccount.value) return
  launchingAccount.value = key
  try {
    const result = await launchAccountLogin(account)
    toast({
      title: `已打开 ${result.account} 扫码窗口`,
      description: '请用对应账号的手机扫码，成功后点击「我已扫码，刷新账号」。',
    })
  } catch (e) {
    toast({
      title: '无法启动扫码登录',
      description: (e as Error).message,
      variant: 'destructive',
    })
  } finally {
    launchingAccount.value = ''
  }
}

function openCreateDialog() {
  newName.value = ''
  newContent.value = ''
  isCreateDialogOpen.value = true
}

async function openEditDialog(name: string) {
  isSaving.value = true
  try {
    const detail = await getAccount(name)
    editName.value = detail.name
    editContent.value = detail.content
    isEditDialogOpen.value = true
  } catch (e) {
    toast({ title: t('accounts.toasts.loadContentFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    isSaving.value = false
  }
}

function openDeleteDialog(name: string) {
  deleteName.value = name
  isDeleteDialogOpen.value = true
}

function goCreateTask(name: string) {
  router.push({ path: '/tasks', query: { account: name, create: '1' } })
}

async function handleCreateAccount() {
  if (!newName.value.trim() || !newContent.value.trim()) {
    toast({ title: t('accounts.toasts.incomplete'), description: t('accounts.toasts.createDescriptionRequired'), variant: 'destructive' })
    return
  }
  isSaving.value = true
  try {
    await createAccount({ name: newName.value.trim(), content: newContent.value.trim() })
    toast({ title: t('accounts.toasts.created') })
    isCreateDialogOpen.value = false
    await fetchAccounts()
  } catch (e) {
    toast({ title: t('accounts.toasts.createFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    isSaving.value = false
  }
}

async function handleUpdateAccount() {
  if (!editContent.value.trim()) {
    toast({ title: t('accounts.toasts.contentRequired'), description: t('accounts.toasts.updateDescriptionRequired'), variant: 'destructive' })
    return
  }
  isSaving.value = true
  try {
    await updateAccount(editName.value, editContent.value.trim())
    toast({ title: t('accounts.toasts.updated') })
    isEditDialogOpen.value = false
    await fetchAccounts()
  } catch (e) {
    toast({ title: t('accounts.toasts.updateFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    isSaving.value = false
  }
}

async function handleDeleteAccount() {
  isSaving.value = true
  try {
    await deleteAccount(deleteName.value)
    toast({ title: t('accounts.toasts.deleted') })
    isDeleteDialogOpen.value = false
    await fetchAccounts()
  } catch (e) {
    toast({ title: t('accounts.toasts.deleteFailed'), description: (e as Error).message, variant: 'destructive' })
  } finally {
    isSaving.value = false
  }
}

function openCreateFromQuery() {
  if (route.query.create === '1' && !isCreateDialogOpen.value) {
    openCreateDialog()
  }
}

watch(
  () => route.query.create,
  () => openCreateFromQuery()
)

onMounted(() => {
  fetchAccounts()
  openCreateFromQuery()
})
</script>

<template>
  <div>
    <div class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-800">{{ t('accounts.title') }}</h1>
        <p class="text-sm text-gray-500 mt-1">{{ t('accounts.description') }}</p>
      </div>
      <Button class="w-full sm:w-auto" @click="openCreateDialog">{{ t('accounts.add') }}</Button>
    </div>

    <div v-if="scanRequested" class="mb-6 rounded-xl border border-[#B9D3F8] bg-[#F2F7FF] p-4">
      <div class="flex items-start gap-3">
        <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#E2EDFF] text-[#2360E6]">
          <span class="text-[18px] font-black">↻</span>
        </span>
        <div class="min-w-0 flex-1">
          <h2 class="text-[15px] font-black text-[#173A6B]">重新扫码登录闲鱼账号</h2>
          <p class="mt-1 text-[12px] leading-relaxed text-[#5A6F8E]">
            点击 <b>「启动扫码窗口」</b> 会自动打开闲鱼登录页；也可以双击项目根目录的 <b>「登录闲鱼账号.bat」</b>
            或 <b>「登录剩余账号_批量.bat」</b>。用手机闲鱼扫码确认后，登录态会自动保存到
            <code class="rounded bg-white px-1 py-0.5">state/</code>。
          </p>
          <div class="mt-3 flex flex-wrap gap-2">
            <Button size="sm" :disabled="!!launchingAccount" @click="launchLogin()">
              {{ launchingAccount ? '正在打开…' : '启动扫码窗口' }}
            </Button>
            <Button size="sm" variant="outline" @click="fetchAccounts">我已扫码，刷新账号</Button>
            <Button size="sm" variant="outline" @click="openCreateDialog">改为手动添加账号</Button>
          </div>
        </div>
      </div>
    </div>

    <Card class="app-surface mb-6 border-none">
      <CardHeader>
        <CardTitle>{{ t('accounts.cookieGuide.title') }}</CardTitle>
      </CardHeader>
      <CardContent class="text-sm text-gray-600">
        <ol class="list-decimal list-inside space-y-1.5">
          <li>{{ t('accounts.cookieGuide.step1Prefix') }}</li>
          <li>{{ t('accounts.cookieGuide.step2Prefix') }}</li>
          <li>{{ t('accounts.cookieGuide.step3') }}</li>
          <li>{{ t('accounts.cookieGuide.step4') }}</li>
          <li>{{ t('accounts.cookieGuide.step5') }}</li>
        </ol>
        <p class="mt-3 text-xs text-gray-400">
          登录脚本：登录闲鱼账号.bat / 登录闲鱼账号_2.bat（均在项目根目录）
        </p>
      </CardContent>
    </Card>

    <Card class="app-surface border-none">
      <CardHeader>
        <CardTitle>{{ t('accounts.list.title') }}</CardTitle>
        <CardDescription>{{ t('accounts.list.description') }}</CardDescription>
      </CardHeader>
      <CardContent>
        <div class="space-y-4 md:hidden">
          <div v-if="isLoading" class="py-10 text-center text-sm text-muted-foreground">{{ t('common.loading') }}</div>
          <div v-else-if="accounts.length === 0" class="py-10 text-center text-sm text-muted-foreground">{{ t('accounts.list.empty') }}</div>
          <article
            v-else
            v-for="account in accounts"
            :key="account.name"
            class="app-surface-subtle p-4"
          >
            <div class="space-y-2">
              <div class="flex items-center justify-between gap-3">
                <h3 class="truncate text-base font-semibold text-slate-900">{{ account.name }}</h3>
                <span
                  class="rounded-md border px-2 py-1 text-[10px] font-bold"
                  :class="statusClass(healthOf(account.name)?.status)"
                >
                  {{ healthOf(account.name)?.status_label || '可用' }}
                </span>
              </div>
              <p class="break-all text-sm text-slate-500">{{ account.path }}</p>
              <p class="text-[11px]" :class="runTextClass(healthOf(account.name)?.status)">
                {{ runSummary(account.name) }}
              </p>
            </div>
            <div class="mt-4 flex flex-wrap gap-2">
              <Button
                v-if="healthOf(account.name)?.status === 'needs_update'"
                size="sm"
                class="min-w-[120px] flex-1 bg-[#B56B0B] hover:bg-[#975707]"
                :disabled="!!launchingAccount"
                @click="launchLogin(account.name)"
              >
                {{ launchingAccount === account.name ? '正在打开…' : '重新扫码' }}
              </Button>
              <Button size="sm" variant="outline" class="flex-1 min-w-[120px]" @click="goCreateTask(account.name)">{{ t('accounts.list.createTask') }}</Button>
              <Button size="sm" variant="outline" class="flex-1 min-w-[120px]" @click="openEditDialog(account.name)">{{ t('accounts.list.update') }}</Button>
              <Button size="sm" variant="destructive" class="flex-1 min-w-[120px]" @click="openDeleteDialog(account.name)">{{ t('accounts.list.delete') }}</Button>
            </div>
          </article>
        </div>

        <div class="hidden md:block">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{{ t('accounts.list.name') }}</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>{{ t('accounts.list.file') }}</TableHead>
                <TableHead>最近运行</TableHead>
                <TableHead class="text-right">{{ t('accounts.list.actions') }}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-if="isLoading">
                <TableCell colspan="5" class="h-20 text-center text-muted-foreground">{{ t('common.loading') }}</TableCell>
              </TableRow>
              <TableRow v-else-if="accounts.length === 0">
                <TableCell colspan="5" class="h-20 text-center text-muted-foreground">{{ t('accounts.list.empty') }}</TableCell>
              </TableRow>
              <TableRow v-else v-for="account in accounts" :key="account.name">
                <TableCell class="font-medium">{{ account.name }}</TableCell>
                <TableCell>
                  <span
                    class="inline-flex rounded-md border px-2 py-1 text-[10px] font-bold"
                    :class="statusClass(healthOf(account.name)?.status)"
                  >
                    {{ healthOf(account.name)?.status_label || '可用' }}
                  </span>
                </TableCell>
                <TableCell class="text-sm text-gray-500">{{ account.path }}</TableCell>
                <TableCell class="max-w-[320px] text-xs">
                  <p :class="runTextClass(healthOf(account.name)?.status)">
                    {{ runSummary(account.name) }}
                  </p>
                </TableCell>
                <TableCell class="text-right">
                  <div class="flex justify-end gap-2">
                    <Button
                      v-if="healthOf(account.name)?.status === 'needs_update'"
                      size="sm"
                      class="bg-[#B56B0B] hover:bg-[#975707]"
                      :disabled="!!launchingAccount"
                      @click="launchLogin(account.name)"
                    >
                      {{ launchingAccount === account.name ? '正在打开…' : '重新扫码' }}
                    </Button>
                    <Button size="sm" variant="outline" @click="goCreateTask(account.name)">{{ t('accounts.list.createTask') }}</Button>
                    <Button size="sm" variant="outline" @click="openEditDialog(account.name)">{{ t('accounts.list.update') }}</Button>
                    <Button size="sm" variant="destructive" @click="openDeleteDialog(account.name)">{{ t('accounts.list.delete') }}</Button>
                  </div>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>

    <Dialog v-model:open="isCreateDialogOpen">
      <DialogContent class="sm:max-w-[700px]">
        <DialogHeader>
          <DialogTitle>{{ t('accounts.createDialog.title') }}</DialogTitle>
          <DialogDescription>{{ t('accounts.createDialog.description') }}</DialogDescription>
        </DialogHeader>
        <div class="space-y-4">
          <div class="grid gap-2">
            <Label>{{ t('accounts.createDialog.name') }}</Label>
            <Input v-model="newName" :placeholder="t('accounts.createDialog.namePlaceholder')" />
          </div>
          <div class="grid gap-2">
            <Label>{{ t('accounts.createDialog.jsonContent') }}</Label>
            <Textarea v-model="newContent" class="min-h-[200px]" :placeholder="t('accounts.createDialog.jsonPlaceholder')" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isCreateDialogOpen = false">{{ t('common.cancel') }}</Button>
          <Button :disabled="isSaving" @click="handleCreateAccount">
            {{ isSaving ? t('common.saving') : t('common.save') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="isEditDialogOpen">
      <DialogContent class="sm:max-w-[700px]">
        <DialogHeader>
          <DialogTitle>{{ t('accounts.editDialog.title', { name: editName }) }}</DialogTitle>
          <DialogDescription>{{ t('accounts.editDialog.description') }}</DialogDescription>
        </DialogHeader>
        <div class="space-y-4">
          <div class="grid gap-2">
            <Label>{{ t('accounts.createDialog.jsonContent') }}</Label>
            <Textarea v-model="editContent" class="min-h-[200px]" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isEditDialogOpen = false">{{ t('common.cancel') }}</Button>
          <Button :disabled="isSaving" @click="handleUpdateAccount">
            {{ isSaving ? t('common.saving') : t('common.save') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <Dialog v-model:open="isDeleteDialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ t('accounts.deleteDialog.title') }}</DialogTitle>
          <DialogDescription>{{ t('accounts.deleteDialog.description', { name: deleteName }) }}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" @click="isDeleteDialogOpen = false">{{ t('common.cancel') }}</Button>
          <Button variant="destructive" :disabled="isSaving" @click="handleDeleteAccount">
            {{ isSaving ? t('accounts.deleteDialog.deleting') : t('accounts.list.delete') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
