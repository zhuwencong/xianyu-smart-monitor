<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
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

// ---------------------------------------------------------------------------
// 扫码添加账号：点一下就拉起登录窗口，扫完自动落盘，不用再碰 .bat
// ---------------------------------------------------------------------------
const isScanDialogOpen = ref(false)
const scanAccountName = ref('')
const scanStatus = ref<'launching' | 'waiting' | 'done' | 'error'>('launching')
const scanError = ref('')
let scanTimer: number | null = null

function nextAccountName(): string {
  const used = new Set(accounts.value.map((item) => item.name))
  let index = 1
  while (used.has(`acc_${index}`)) index += 1
  return `acc_${index}`
}

function stopScanPolling() {
  if (scanTimer !== null) {
    window.clearInterval(scanTimer)
    scanTimer = null
  }
}

function startScanPolling() {
  stopScanPolling()
  const startedAt = Date.now()
  scanTimer = window.setInterval(async () => {
    if (Date.now() - startedAt > 5 * 60 * 1000) {
      stopScanPolling()
      scanStatus.value = 'error'
      scanError.value = '等待超时。如果浏览器窗口被关掉了，重新点一次「添加账号」即可。'
      return
    }
    try {
      const list = await listAccounts()
      if (!list.some((item) => item.name === scanAccountName.value)) return
      stopScanPolling()
      scanStatus.value = 'done'
      await fetchAccounts()
      toast({
        title: `已添加 ${scanAccountName.value}`,
        description: '扫码成功，登录态已保存到 state/ 目录。',
      })
      window.setTimeout(() => {
        isScanDialogOpen.value = false
      }, 1200)
    } catch {
      // 轮询失败不打扰用户，等下一次
    }
  }, 3000)
}

async function startScanAdd() {
  scanAccountName.value = nextAccountName()
  scanStatus.value = 'launching'
  scanError.value = ''
  isScanDialogOpen.value = true
  await launchScanWindow()
}

async function launchScanWindow() {
  scanStatus.value = 'launching'
  scanError.value = ''
  try {
    const result = await launchAccountLogin(scanAccountName.value)
    scanAccountName.value = result.account
    scanStatus.value = 'waiting'
    startScanPolling()
  } catch (e) {
    scanStatus.value = 'error'
    scanError.value = (e as Error).message
  }
}

function closeScanDialog() {
  stopScanPolling()
  isScanDialogOpen.value = false
}

function switchToManualPaste() {
  closeScanDialog()
  openCreateDialog()
}

onBeforeUnmount(stopScanPolling)

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
      <Button class="w-full sm:w-auto" @click="startScanAdd">{{ t('accounts.add') }}</Button>
    </div>

    <div v-if="scanRequested" class="mb-6 rounded-xl border border-[#B9D3F8] bg-[#F2F7FF] p-4">
      <div class="flex items-start gap-3">
        <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#E2EDFF] text-[#2360E6]">
          <span class="text-[18px] font-black">↻</span>
        </span>
        <div class="min-w-0 flex-1">
          <h2 class="text-[15px] font-black text-[#173A6B]">重新扫码登录闲鱼账号</h2>
          <p class="mt-1 text-[12px] leading-relaxed text-[#5A6F8E]">
            点击 <b>「启动扫码窗口」</b> 会自动打开闲鱼登录页；用手机闲鱼扫码确认后，登录态会自动保存到
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
          扫码窗口由本页直接拉起（同一时间只允许一个）；已有 JSON 时也可在弹窗里改用「手动粘贴 JSON」。
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

    <Dialog v-model:open="isScanDialogOpen" @update:open="(open: boolean) => { if (!open) stopScanPolling() }">
      <DialogContent class="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>扫码添加账号</DialogTitle>
          <DialogDescription>
            已经为你打开闲鱼登录窗口，用手机扫码即可，登录态会自动保存。
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-3">
          <div class="flex items-center justify-between rounded-lg border border-[#E3EAF4] bg-[#F7FAFE] px-3 py-2 text-sm">
            <span class="text-[#5A6F8E]">账号名</span>
            <b class="text-[#173A6B]">{{ scanAccountName }}</b>
          </div>

          <p v-if="scanStatus === 'launching'" class="flex items-center gap-2 text-sm text-[#40526C]">
            <span class="h-2 w-2 animate-pulse rounded-full bg-[#2360E6]"></span>
            正在打开浏览器窗口…
          </p>
          <p v-else-if="scanStatus === 'waiting'" class="flex items-center gap-2 text-sm text-[#40526C]">
            <span class="h-2 w-2 animate-pulse rounded-full bg-[#2360E6]"></span>
            等待扫码…在浏览器窗口里用手机闲鱼「扫一扫」并确认登录
          </p>
          <p v-else-if="scanStatus === 'done'" class="text-sm font-medium text-[#0C7A56]">
            ✅ 扫码成功，账号已添加，列表正在刷新。
          </p>
          <p v-else class="text-sm font-medium text-[#B03A2E]">{{ scanError }}</p>

          <p class="text-[11px] leading-relaxed text-[#8B9AB0]">
            同一时间只允许一个扫码窗口；没看到浏览器窗口就先关掉旧的再点一次。<br />
            如果扫到的是已经存在的闲鱼号，脚本不会新增账号文件（会被标记为 .dup），换一个号再扫即可。
          </p>
        </div>
        <DialogFooter class="gap-2">
          <Button
            v-if="scanStatus === 'waiting' || scanStatus === 'error'"
            variant="outline"
            size="sm"
            @click="launchScanWindow"
          >
            重新打开窗口
          </Button>
          <Button variant="outline" size="sm" @click="switchToManualPaste">手动粘贴 JSON</Button>
          <Button size="sm" @click="closeScanDialog">关闭</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

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
