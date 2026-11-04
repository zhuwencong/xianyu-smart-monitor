import { computed, ref } from 'vue'
import { getWorkbenchSummary, type WorkbenchSummary } from '@/api/workbench'

const summary = ref<WorkbenchSummary | null>(null)
const isLoading = ref(false)
const error = ref<Error | null>(null)
const isManagementOpen = ref(false)
const managementSection = ref<'overview' | 'accounts' | 'notifications' | 'ai' | 'data'>('overview')
let inflight: Promise<WorkbenchSummary | null> | null = null

async function refreshSummary(): Promise<WorkbenchSummary | null> {
  if (inflight) return inflight
  isLoading.value = true
  error.value = null
  inflight = (async () => {
    try {
      const data = await getWorkbenchSummary()
      summary.value = data
      return data
    } catch (e) {
      error.value = e instanceof Error ? e : new Error('无法加载工作台摘要')
      return null
    } finally {
      isLoading.value = false
      inflight = null
    }
  })()
  return inflight
}

function openManagement(section: 'overview' | 'accounts' | 'notifications' | 'ai' | 'data' = 'overview') {
  managementSection.value = section
  isManagementOpen.value = true
}

function closeManagement() {
  isManagementOpen.value = false
}

export function useWorkbench() {
  return {
    summary,
    isLoading,
    error,
    isManagementOpen,
    managementSection,
    pendingCount: computed(() => summary.value?.pending_count ?? 0),
    issues: computed(() => summary.value?.issues ?? []),
    refreshSummary,
    openManagement,
    closeManagement,
  }
}
