import { http } from '@/lib/http'

export type ReviewStatus = 'unseen' | 'favorite' | 'handled'
export type AiVerdict = 'recommend' | 'verify' | 'mismatch' | 'failed'
export type TaskStatus = 'running' | 'waiting' | 'cooldown' | 'paused'

export interface CandidateCriteria {
  key: string
  label: string
  status: string
  status_label: string
  comment: string
  evidence: string
  persona?: string | null
}

export interface Candidate {
  id: number
  item_id: string
  title: string
  price: number | null
  price_display: string
  image: string
  images: string[]
  task_id: number | null
  task_name: string
  keyword: string
  crawl_time: string
  crawl_label: string
  publish_time?: string | null
  publish_label?: string | null
  location: string
  tags: string[]
  views?: string | number | null
  wants?: string | number | null
  link: string
  seller: {
    name: string
    credit: string
    rating: string
    registered: string
    location: string
    signature: string
  }
  review_status: ReviewStatus
  review_label: string
  ai_verdict: AiVerdict
  ai_label: string
  ai_reason: string
  ai_summary: string
  ai_score: number | null
  /** S/A/B/C/D，由总分换算；null 表示未分析 */
  ai_grade: string | null
  /** 触发的封顶规则（如「价格不低于行情，不算捡漏」），空数组表示未被封顶 */
  caps_applied: string[]
  /** 挂价 ÷ 行情中位数，精确口径（仅同型号样本足够时有值） */
  bargain_ratio: number | null
  /** 展示用价格位置，可能是关键词口径 */
  price_gap: number | null
  price_gap_scope: string | null
  ai_value_score: number | null
  score_breakdown: { key: string; label: string; value: number }[]
  risk_tags: string[]
  missing_checks: string[]
  criteria: CandidateCriteria[]
  recommended: boolean
  /** 当前推送门槛（分数），与后台推送逻辑同源 */
  push_min_score: number
  /** 是否达到推送线：达到才会发微信通知 */
  meets_push: boolean
  analysis_source: string
  ai_failed: boolean
  /** 底层硬门槛是否否决了这条候选（否决后分数封顶 40，且不会推送） */
  hard_blocked?: boolean
  hard_gates?: { key: string; label: string; detail: string; severity: string }[]
  specs?: {
    model: string
    /** 型号展示名，如 GTX 1070 / RX 580 / Quadro P620 */
    model_label?: string
    vram_gb: number | null
    card_class: string
    /** 性能档 0-100（仅显卡有） */
    performance?: number | null
    /** 该性能档的二手参考价（仅显卡有） */
    expected_price?: number | null
  }
  /** 品类分区：gpu 显卡 / phone 手机 / other 其他，UI 据此切换展示重点 */
  category?: 'gpu' | 'phone' | 'other'
  market: {
    avg: number | null
    low: number | null
    high: number | null
    samples: number | null
    label: string | null
    /** model / family 才代表同型号可比价，其它口径不参与评分 */
    scope?: string | null
    comparable?: boolean
  }
}

export interface CandidateResponse {
  total: number
  page: number
  limit: number
  items: Candidate[]
  counts: Record<ReviewStatus, number>
  ai_counts: Record<'all' | AiVerdict, number>
  task_counts: Record<string, number>
  grade_counts: Record<'all' | 'S' | 'A' | 'B' | 'C' | 'D', number>
  review_labels: Record<ReviewStatus, string>
  ai_labels: Record<AiVerdict, string>
  grade_labels: Record<string, string>
}

export interface CandidateQuery {
  review_status?: ReviewStatus | 'all'
  ai_verdict?: AiVerdict | 'all'
  grade?: 'all' | 'S' | 'A' | 'B' | 'C' | 'D'
  task_id?: number
  q?: string
  sort?: 'smart' | 'newest' | 'price_asc' | 'price_desc' | 'score'
  page?: number
  limit?: number
}

export interface WorkbenchRun {
  id: string | number
  task_id?: number
  task_name?: string
  trigger?: string
  status: 'running' | 'completed' | 'partial' | 'failed' | 'no_new' | 'stopped'
  status_label: string
  started_at?: string | null
  finished_at?: string | null
  started_label?: string
  finished_label?: string
  duration_seconds?: number | null
  saved_count: number
  discovered_count?: number
  pending_count?: number
  error_message?: string | null
  summary?: string | null
  timeline?: { time: string; text: string }[]
}

export interface WorkbenchTask {
  id: number
  task_name: string
  keyword: string
  min_price?: string | null
  max_price?: string | null
  budget: string
  enabled: boolean
  is_running: boolean
  cron?: string | null
  next_run_at?: string | null
  next_run_label: string
  status: TaskStatus
  status_label: string
  status_detail: string
  paused_until?: string | null
  latest_run?: WorkbenchRun | null
  recent_runs: WorkbenchRun[]
  decision_mode: string
  account_strategy: string
  account_state_file?: string | null
  description: string
  title_include_keywords: string[]
  title_exclude_keywords: string[]
}

export interface WorkbenchTaskResponse {
  items: WorkbenchTask[]
  counts: Record<'all' | TaskStatus, number>
}

export interface WorkbenchIssue {
  id: string
  type: 'task' | 'account' | 'ai'
  title: string
  detail: string
  action_label: string
  action_route: string
  severity: 'warning' | 'info'
}

export interface AccountHealth {
  name: string
  file: string
  updated_at: string
  updated_label: string
  age_days: number
  /** warning = 登录态可用，但上一轮实际运行失败（非登录原因） */
  status: 'ok' | 'warning' | 'needs_update'
  status_label: string
  reason: string
  last_failure_at?: string | null
  last_failure_label?: string
  last_success_at?: string | null
  last_success_label?: string
  last_run_status?: 'ok' | 'failed' | 'none'
  last_run_at?: string | null
  last_run_label?: string
  last_run_reason?: string
}

export interface WorkbenchSummary {
  task_count: number
  enabled_task_count: number
  running_count: number
  today_count: number
  pending_count: number
  issues: WorkbenchIssue[]
  accounts: AccountHealth[]
  account_count: number
  account_alert_count: number
  ai_configured: boolean
  ai_model: string
  notification_channels: string[]
  notification_configured: boolean
  daily_report_enabled: boolean
  daily_report_hour: number | null
  last_updated: string | null
}

export async function getWorkbenchSummary(): Promise<WorkbenchSummary> {
  return await http('/api/workbench/summary')
}

export async function getCandidates(params: CandidateQuery): Promise<CandidateResponse> {
  return await http('/api/workbench/candidates', {
    params: {
      review_status: params.review_status ?? 'all',
      ai_verdict: params.ai_verdict ?? 'all',
      grade: params.grade ?? 'all',
      task_id: params.task_id,
      q: params.q ?? '',
      sort: params.sort ?? 'smart',
      page: params.page ?? 1,
      limit: params.limit ?? 12,
    },
  })
}

export async function updateCandidateReview(itemId: string, reviewStatus: ReviewStatus): Promise<void> {
  await http(`/api/workbench/candidates/${encodeURIComponent(itemId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ review_status: reviewStatus }),
  })
}

export async function getWorkbenchTasks(): Promise<WorkbenchTaskResponse> {
  return await http('/api/workbench/tasks')
}

export async function getTaskRuns(taskId: number, limit = 8): Promise<{ task_id: number; task_name: string; runs: WorkbenchRun[] }> {
  return await http(`/api/workbench/tasks/${taskId}/runs`, { params: { limit } })
}

export async function getAccountHealth(): Promise<{ items: AccountHealth[] }> {
  return await http('/api/workbench/accounts')
}
