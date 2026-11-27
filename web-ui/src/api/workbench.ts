import { http } from '@/lib/http'

export type ReviewStatus = 'unseen' | 'favorite' | 'handled'
export type AiVerdict = 'recommend' | 'verify' | 'mismatch' | 'failed'
export type TaskStatus = 'running' | 'waiting' | 'cooldown' | 'paused'
export type OfferGrade = 'buy' | 'negotiate' | 'watch' | 'skip'

/** 六个主维度的 key。顺序即 UI 展示顺序（先「贵不贵」再「值不值」）。 */
export type OfferDimensionKey =
  | 'price_market'
  | 'value_vs_new'
  | 'seller'
  | 'authenticity'
  | 'device_health'
  | 'safety'

/** 绝对分模型里的单个维度。value 为 null 表示「不可判」，不是 0 分。 */
export interface OfferDimension {
  key: OfferDimensionKey
  label: string
  value: number | null
  /** 该维度满分，同时是进度条分母 */
  max: number
  /** 与 max 同值，保留旧字段名供 UI 标注「权重」 */
  weight: number
  reason: string
  /** true = 该分值含推定成分（如「描述与图片一致」未逐图比对） */
  inferred: boolean
  scored: boolean
}

/** 辅助加减分：不占权重，直接对总分做修正，合计钉死 ±10。 */
export interface OfferAdjustment {
  key: string
  label: string
  /** 正负分值。clamp 项的 delta 是「被压回」的差额，最终各项之和 = 实际加分 */
  delta: number
  tone: 'good' | 'bad' | 'neutral'
}

export interface OfferVeto {
  key: string
  label: string
  detail: string
  /** hard_gate = 来自底层硬门槛（矿卡/故障/维修史等） */
  source?: string
}

export interface OfferMissingItem {
  key: string
  label: string
  detail: string
  /** 可直接发给卖家的问句；为空表示需人工核对或属于任务配置问题 */
  ask: string
  /** 这一项缺失丢了多少分，用来判断补哪项最值 */
  weight_lost?: number
  /** true = 属于任务配置问题（如没填全新价锚点），问卖家无用 */
  internal?: boolean
  note?: string
}

/** 100 分制绝对分：6 维加权 + 辅助加减分 + 独立一票否决。不读 AI 输出。 */
export interface OfferScore {
  listing_id: string
  scores: Record<OfferDimensionKey, number | null>
  weights: Record<OfferDimensionKey, number>
  dimensions: OfferDimension[]
  /** 六维原始得分（未加辅助分） */
  base_total: number | null
  /** 最终得分（0–100）= base_total + adjustment_total，且不超过 scored_max */
  total: number | null
  /** 实际生效的辅助分（可能被缺项上限吃掉一部分） */
  adjustment_total: number
  /** 辅助分的「意图」总和（未受上限约束），用于解释少加的那部分 */
  adjustment_intent: number
  adjustments: OfferAdjustment[]
  /** 实际拿到过分的维度权重之和；< 100 说明有维度不可判 */
  scored_max: number
  max_total: number
  /** 二手行情维度是否可判 */
  price_judged: boolean
  /** 相对全新价维度是否可判（未配置价格锚点时 false） */
  value_judged: boolean
  grade: OfferGrade
  grade_label: string
  grade_note: string
  /** 评级被上层判定降级时的来源：verdict = 底层引擎判不匹配/待核实 */
  demoted_by?: string
  veto_flags: OfferVeto[]
  vetoed: boolean
  missing_items: OfferMissingItem[]
  missing_labels: string[]
  ask_script: string
  /** 二手价 ÷ 同型号二手行情中位数 */
  price_ratio: number | null
  /** 二手价 ÷ 当前全新最低价（含国补/清仓） */
  ratio_used_vs_new: number | null
  market_median: number | null
  new_price_anchor: number | null
  new_price_note: string
}

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
  ai_value_score: number | null
  score_breakdown: { key: string; label: string; value: number }[]
  /** 100 分制绝对分（5 维 + 一票否决），不读 AI，阈值可直接对外解释 */
  offer?: OfferScore
  risk_tags: string[]
  missing_checks: string[]
  criteria: CandidateCriteria[]
  recommended: boolean
  analysis_source: string
  ai_failed: boolean
  /** 底层硬门槛是否否决了这条候选（否决后分数封顶 40，且不会推送） */
  hard_blocked?: boolean
  hard_gates?: { key: string; label: string; detail: string; severity: string }[]
  specs?: {
    model: string
    vram_gb: number | null
    card_class: string
    /** 是否识别为显卡本体（配件、打包件为 false） */
    is_real_gpu?: boolean
    /** 显卡性能评估；非显卡或型号不认识时为 null */
    perf?: {
      score: number
      perf_index: number
      generation: string
      vram_gb: number | null
      label: string
    } | null
  }
  market: {
    avg: number | null
    low: number | null
    high: number | null
    samples: number | null
    label: string | null
    /** 标签被故障判定覆盖时的原因说明 */
    note?: string | null
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
  review_labels: Record<ReviewStatus, string>
  ai_labels: Record<AiVerdict, string>
  /** 当前生效的新鲜度窗口（天），0 表示不限 */
  visible_days?: number
  /** 因为超出窗口而被隐藏的条数（只是没显示，数据库里还在） */
  hidden_stale_count?: number
}

export interface CandidateQuery {
  review_status?: ReviewStatus | 'all'
  ai_verdict?: AiVerdict | 'all'
  task_id?: number
  q?: string
  sort?: 'smart' | 'newest' | 'price_asc' | 'price_desc' | 'score'
  page?: number
  limit?: number
  /** 只看最近几天上架的；0 = 看全部历史 */
  days?: number
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
  /** 「当前电商全新最低价」人工锚点；null = 未配置，性价比分不可判 */
  new_price_anchor?: number | null
  new_price_note?: string | null
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
      task_id: params.task_id,
      q: params.q ?? '',
      sort: params.sort ?? 'smart',
      page: params.page ?? 1,
      limit: params.limit ?? 12,
      days: params.days ?? 5,
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
