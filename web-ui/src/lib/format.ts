const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六']

export function parseDate(value?: string | null): Date | null {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function pad(value: number): string {
  return String(value).padStart(2, '0')
}

export function formatClock(value?: string | null): string {
  const date = parseDate(value)
  return date ? `${pad(date.getHours())}:${pad(date.getMinutes())}` : '—'
}

export function formatShortDate(value?: string | null): string {
  const date = parseDate(value)
  if (!date) return '时间未知'
  const now = new Date()
  const sameYear = date.getFullYear() === now.getFullYear()
  return `${sameYear ? '' : `${date.getFullYear()}-`}${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function formatRelativeDay(value?: string | null): string {
  const date = parseDate(value)
  if (!date) return '时间未知'
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
  const diffDays = Math.round((startOfToday - target) / 86400000)
  const clock = `${pad(date.getHours())}:${pad(date.getMinutes())}`
  if (diffDays === 0) return `今天 ${clock}`
  if (diffDays === 1) return `昨天 ${clock}`
  if (diffDays > 1 && diffDays < 7) return `${diffDays} 天前 ${clock}`
  return formatShortDate(value)
}

export function formatNextRun(value?: string | null): string {
  const date = parseDate(value)
  if (!date) return '未排程'
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
  const diffDays = Math.round((target - startOfToday) / 86400000)
  const clock = `${pad(date.getHours())}:${pad(date.getMinutes())}`
  if (diffDays === 0) return `今天 ${clock}`
  if (diffDays === 1) return `明天 ${clock}`
  if (diffDays === 2) return `后天 ${clock}`
  if (diffDays > 2 && diffDays < 7) return `周${WEEKDAYS[date.getDay()]} ${clock}`
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${clock}`
}

export function formatDuration(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return `${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  if (minutes < 60) return remainder ? `${minutes} 分 ${remainder} 秒` : `${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  return `${hours} 小时 ${minutes % 60} 分`
}

export function formatPrice(value?: number | null): string {
  if (value === null || value === undefined) return '价格未知'
  return `¥${Math.round(value).toLocaleString('zh-CN')}`
}

export function formatNumber(value?: number | null): string {
  if (value === null || value === undefined) return '—'
  return Number(value).toLocaleString('zh-CN')
}

export function timeAgo(value?: string | null): string {
  const date = parseDate(value)
  if (!date) return '刚刚'
  const diff = Date.now() - date.getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} 天前`
  return formatShortDate(value)
}
