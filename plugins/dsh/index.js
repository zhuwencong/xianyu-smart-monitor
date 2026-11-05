/**
 * 闲鱼智能监控 × DeepSeek Harness
 *
 * 这个插件不打包爬虫，它是一个**桥接层**：把本机运行的监控服务
 * （`python -m src.app`，默认 http://127.0.0.1:8000）的只读查询与少量控制
 * 能力注册成 DSH 工具，让模型可以直接读候选商品、看任务状态、翻运行记录。
 *
 * 设计约定：
 * - 只连 localhost，不外传任何数据
 * - 所有可调参数都来自 `cordis.patch.yml` 的 config，不硬编码
 * - 网络/服务不可用时抛出可读错误，不静默返回空结果
 */
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'dsh-plugin-xianyu-monitor'
export const inject = ['tools']

const DEFAULT_CONFIG = {
  baseUrl: 'http://127.0.0.1:8000',
  timeoutMs: 15000,
  defaultLimit: 12,
}

/* ------------------------------------------------------------------ */
/* HTTP 客户端                                                         */
/* ------------------------------------------------------------------ */

function resolveConfig(raw) {
  const config = { ...DEFAULT_CONFIG, ...(raw || {}) }
  const baseUrl = String(config.baseUrl || '').trim().replace(/\/+$/, '')
  if (!/^https?:\/\//i.test(baseUrl)) {
    throw new Error(
      `[xianyu-monitor] baseUrl 必须以 http:// 或 https:// 开头，当前值：${config.baseUrl}`,
    )
  }
  const timeoutMs = Number(config.timeoutMs)
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new Error(`[xianyu-monitor] timeoutMs 必须是正数，当前值：${config.timeoutMs}`)
  }
  const defaultLimit = Math.min(Math.max(Number(config.defaultLimit) || 12, 1), 60)
  return { baseUrl, timeoutMs, defaultLimit }
}

function combinedSignal(timeoutMs, outerSignal) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  if (typeof timer.unref === 'function') timer.unref()

  const forward = () => controller.abort()
  if (outerSignal) {
    if (outerSignal.aborted) controller.abort()
    else outerSignal.addEventListener('abort', forward, { once: true })
  }

  return {
    signal: controller.signal,
    dispose() {
      clearTimeout(timer)
      if (outerSignal) outerSignal.removeEventListener('abort', forward)
    },
  }
}

async function request(config, path, { method = 'GET', body, exec } = {}) {
  const url = `${config.baseUrl}${path}`
  const { signal, dispose } = combinedSignal(config.timeoutMs, exec && exec.signal)
  try {
    const response = await fetch(url, {
      method,
      headers: {
        accept: 'application/json',
        ...(body === undefined ? {} : { 'content-type': 'application/json' }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })

    const raw = await response.text()
    let payload = null
    if (raw) {
      try {
        payload = JSON.parse(raw)
      } catch {
        payload = { raw }
      }
    }

    if (!response.ok) {
      const detail = payload && (payload.detail || payload.message)
      throw new Error(
        `监控服务返回 ${response.status}：${typeof detail === 'string' ? detail : raw.slice(0, 300)}`,
      )
    }
    return payload
  } catch (error) {
    if (error && error.name === 'AbortError') {
      throw new Error(
        `请求 ${path} 超时或被取消（${config.timeoutMs}ms）。若任务列表很大，可在 cordis.patch.yml 调大 timeoutMs。`,
      )
    }
    if (error instanceof TypeError) {
      throw new Error(
        `连不上监控服务 ${config.baseUrl}。请确认它已在本机启动（python -m src.app），且 baseUrl 配置正确。`,
      )
    }
    throw error
  } finally {
    dispose()
  }
}

/* ------------------------------------------------------------------ */
/* 展示辅助                                                            */
/* ------------------------------------------------------------------ */

const text = (value) => [{ type: 'text', text: value }]

function money(value) {
  return typeof value === 'number' ? `¥${value}` : '价格未知'
}

function truncate(value, limit) {
  const raw = String(value == null ? '' : value).trim()
  return raw.length > limit ? `${raw.slice(0, limit - 1)}…` : raw
}

/** 闲鱼链接带一大串追踪参数，对人和模型都是噪声，只保留 item?id=xxx。 */
function cleanLink(link) {
  const raw = String(link || '').trim()
  if (!raw) return ''
  const match = raw.match(/[?&]id=(\d+)/)
  return match ? `https://www.goofish.com/item?id=${match[1]}` : raw.split('?')[0]
}

/** 把硬门槛的 block 条目拼成一句人话；warn 不参与否决，不在这里出现。 */
function gateSummary(item) {
  const blocks = (item.hard_gates || []).filter((hit) => hit && hit.severity === 'block')
  if (blocks.length === 0) return ''
  return blocks
    .map((hit) => (hit.detail ? `${hit.label}：${hit.detail}` : hit.label))
    .join('；')
}

function renderCandidates(value) {
  const lines = [
    `候选商品：共 ${value.total} 条，第 ${value.page} 页（每页 ${value.limit} 条）。`,
  ]
  if (!value.items || value.items.length === 0) {
    lines.push('本页没有符合条件的候选。可以放宽筛选，或先运行一次任务。')
    return lines.join('\n')
  }
  for (const item of value.items) {
    const score = item.ai_score == null ? '—' : item.ai_score
    const specs =
      item.specs && item.specs.model
        ? `｜${item.specs.model}${item.specs.vram_gb ? ` ${item.specs.vram_gb}G` : ''}`
        : ''
    // 只有同型号（或同型号族）样本才配叫「市场价」，其它口径一律不展示。
    const market =
      item.market && item.market.comparable && item.market.avg
        ? `｜同型号中位 ${money(item.market.avg)}（${item.market.samples ?? '?'} 样本）`
        : ''
    const verdict = item.hard_blocked ? '不匹配 · 硬门槛否决' : item.ai_label || item.ai_verdict
    lines.push(
      [
        `- [${verdict}] ${item.title}`,
        `  ${money(item.price)}｜评分 ${score}｜${item.task_name}${specs}${market}`,
        item.hard_blocked
          ? `  否决原因：${gateSummary(item) || '命中底层硬门槛（详见 hard_gates）'}`
          : item.ai_summary
            ? `  依据：${truncate(item.ai_summary, 160)}`
            : '',
        item.link ? `  ${cleanLink(item.link)}` : '',
      ]
        .filter(Boolean)
        .join('\n'),
    )
  }
  if (value.counts) {
    lines.push(
      `状态计数：未查看 ${value.counts.unseen ?? 0}｜已收藏 ${value.counts.favorite ?? 0}｜已处理 ${value.counts.handled ?? 0}`,
    )
  }
  return lines.join('\n')
}

function renderStatus(value) {
  const accounts = value.accounts || []
  const needsUpdate = accounts.filter((item) => item.status === 'needs_update')
  const runFailed = accounts.filter((item) => item.status === 'warning')
  const lines = [
    `任务 ${value.task_count} 个（启用 ${value.enabled_task_count}，运行中 ${value.running_count}）`,
    `今日新增候选 ${value.today_count} 条｜待处理 ${value.pending_count} 项`,
    `账号 ${value.account_count} 个，异常 ${value.account_alert_count} 个`,
  ]
  if (needsUpdate.length > 0) {
    lines.push(`需要重新扫码：${needsUpdate.map((item) => item.name).join('、')}`)
  }
  if (runFailed.length > 0) {
    lines.push(
      `登录态正常但上次运行失败：${runFailed.map((item) => item.name).join('、')}（查任务日志，不用重扫）`,
    )
  }
  lines.push(
    `AI：${value.ai_configured ? `已配置（${value.ai_model || '未命名模型'}）` : '未配置'}`,
    `通知：${value.notification_configured ? '已配置渠道' : '未配置任何渠道'}`,
    value.daily_report_enabled ? `每日日报：${value.daily_report_hour} 点` : '每日日报：关闭',
  )
  return lines.join('\n')
}

function renderTasks(value) {
  const items = value.items || []
  if (items.length === 0) return '还没有监控任务。'
  const lines = [`监控任务：共 ${items.length} 个。`]
  for (const item of items) {
    lines.push(
      `- [${item.status_label}] ${item.task_name}（ID ${item.id}）｜关键词「${item.keyword}」｜预算 ${item.budget}` +
        `｜最近运行：${item.latest_run ? item.latest_run.status_label : '暂无'}｜下次：${item.next_run_label}`,
    )
  }
  return lines.join('\n')
}

/* ------------------------------------------------------------------ */
/* 插件主体                                                            */
/* ------------------------------------------------------------------ */

export function apply(ctx, rawConfig) {
  const config = resolveConfig(rawConfig)

  const register = (tool) => ctx.tools.register(tool)

  register(
    defineTool({
      name: 'xianyu_status',
      description:
        '查看闲鱼监控工作台的整体状态：任务数、运行中任务、今日新增候选、待处理异常、账号健康与 AI/通知是否配置。用户问「闲鱼监控现在怎么样」「有没有异常」时先调这个。',
      parameters: {},
      output: {
        schema: {
          type: 'object',
          additionalProperties: true,
          properties: {
            task_count: { type: 'number' },
            running_count: { type: 'number' },
            today_count: { type: 'number' },
            pending_count: { type: 'number' },
            account_alert_count: { type: 'number' },
            ai_configured: { type: 'boolean' },
            ai_model: { type: 'string' },
            notification_configured: { type: 'boolean' },
          },
        },
        render: (_args, value) => text(renderStatus(value)),
      },
      async execute(_args, exec) {
        return request(config, '/api/workbench/summary', { exec })
      },
    }),
  )

  register(
    defineTool({
      name: 'xianyu_list_candidates',
      description:
        '列出闲鱼监控抓到的候选商品，支持按人工处理状态、AI 判断、任务、关键词、排序方式筛选。返回里 hard_blocked=true 表示被底层硬门槛一票否决（分数封顶、不会推送），market.comparable=false 表示没有同型号样本、不能拿来比价。用户问「有什么值得看的」「今天抓到了什么」「把需核实的列出来」时使用。',
      parameters: {
        review_status: {
          type: 'string',
          description: '人工处理状态：all（默认）/ unseen / favorite / handled',
        },
        ai_verdict: {
          type: 'string',
          description: 'AI 判断：all（默认）/ recommend（建议关注）/ verify（需核实）/ mismatch / failed',
        },
        task_id: { type: 'number', description: '只看某个监控任务的结果' },
        q: { type: 'string', description: '按标题、任务名、卖家搜索' },
        sort: {
          type: 'string',
          description: '排序：smart（默认，综合评分）/ score / newest / price_asc / price_desc',
        },
        page: { type: 'number', description: '页码，从 1 开始' },
        limit: { type: 'number', description: '每页条数，默认 12，上限 60' },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: true,
          properties: {
            total: { type: 'number' },
            page: { type: 'number' },
            limit: { type: 'number' },
            items: { type: 'array' },
            counts: { type: 'object', additionalProperties: true },
          },
        },
        render: (_args, value) => text(renderCandidates(value)),
      },
      presentCall: (args) => ({
        card: 'generic',
        title: `闲鱼候选商品${args && args.q ? ` · 搜索「${args.q}」` : ''}`,
      }),
      async execute(args, exec) {
        const params = new URLSearchParams()
        if (args.review_status) params.set('review_status', String(args.review_status))
        if (args.ai_verdict) params.set('ai_verdict', String(args.ai_verdict))
        if (args.task_id != null) params.set('task_id', String(args.task_id))
        if (args.q) params.set('q', String(args.q))
        if (args.sort) params.set('sort', String(args.sort))
        if (args.page != null) params.set('page', String(args.page))
        params.set(
          'limit',
          String(Math.min(Math.max(Number(args.limit) || config.defaultLimit, 1), 60)),
        )
        return request(config, `/api/workbench/candidates?${params.toString()}`, { exec })
      },
    }),
  )

  register(
    defineTool({
      name: 'xianyu_list_tasks',
      description:
        '列出所有监控任务及其状态：运行中/等待/冷却/暂停、最近一轮结果、下次运行时间、预算区间。用户问「有哪些任务」「任务跑了吗」「下次什么时候跑」时使用。',
      parameters: {},
      output: {
        schema: {
          type: 'object',
          additionalProperties: true,
          properties: { items: { type: 'array' }, counts: { type: 'object', additionalProperties: true } },
        },
        render: (_args, value) => text(renderTasks(value)),
      },
      async execute(_args, exec) {
        return request(config, '/api/workbench/tasks', { exec })
      },
    }),
  )

  register(
    defineTool({
      name: 'xianyu_task_runs',
      description:
        '查看某个监控任务的最近运行记录（每轮开始/结束时间、保存条数、状态、异常原因）。排查「为什么没抓到东西」「任务是不是失败了」时使用。',
      parameters: {
        task_id: { type: 'number', required: true, description: '任务 ID，来自 xianyu_list_tasks' },
        limit: { type: 'number', description: '返回最近几轮，默认 5，上限 20' },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: true,
          properties: {
            task_id: { type: 'number' },
            task_name: { type: 'string' },
            runs: { type: 'array' },
          },
        },
        render: (_args, value) => {
          const runs = value.runs || []
          if (runs.length === 0) return text(`任务「${value.task_name}」还没有运行记录。`)
          const lines = [`任务「${value.task_name}」最近 ${runs.length} 轮运行：`]
          for (const run of runs) {
            lines.push(
              `- ${run.started_at || '时间未知'}｜${run.status_label || run.status}｜保存 ${run.saved_count ?? 0} 条` +
                (run.summary ? `｜${truncate(run.summary, 120)}` : ''),
            )
          }
          return text(lines.join('\n'))
        },
      },
      async execute(args, exec) {
        if (!args.task_id) throw new Error('task_id 必填，请先用 xianyu_list_tasks 查任务 ID。')
        const limit = Math.min(Math.max(Number(args.limit) || 5, 1), 20)
        return request(config, `/api/workbench/tasks/${Number(args.task_id)}/runs?limit=${limit}`, {
          exec,
        })
      },
    }),
  )

  register(
    defineTool({
      name: 'xianyu_issues',
      description:
        '列出当前需要人工处理的异常：账号登录失效、任务连续失败、AI 分析失败过多等。用户问「有什么要处理的」「为什么没消息」时使用。',
      parameters: {},
      output: {
        schema: {
          type: 'object',
          additionalProperties: true,
          properties: { pending_count: { type: 'number' }, issues: { type: 'array' } },
        },
        render: (_args, value) => {
          if (!value.issues || value.issues.length === 0) return text('当前没有待处理的异常。')
          const lines = [`待处理 ${value.pending_count} 项：`]
          for (const issue of value.issues) {
            lines.push(`- [${issue.level || issue.kind || '提示'}] ${issue.title || issue.message || '未命名异常'}`)
          }
          return text(lines.join('\n'))
        },
      },
      async execute(_args, exec) {
        return request(config, '/api/workbench/issues', { exec })
      },
    }),
  )

  register(
    defineTool({
      name: 'xianyu_set_candidate_status',
      description:
        '把某条候选商品标记为已收藏 / 已处理 / 未查看。用户说「这条收藏了」「标记为已处理」时使用。需要闲鱼商品 ID（不是数据库自增 ID）。',
      parameters: {
        item_id: {
          type: 'string',
          required: true,
          description: '闲鱼商品 ID，即候选列表里的 item_id 字段',
        },
        review_status: {
          type: 'string',
          required: true,
          description: '目标状态：unseen / favorite / handled',
        },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: true,
          properties: { message: { type: 'string' }, review_status: { type: 'string' } },
        },
        render: (_args, value) => text(`已更新为「${value.review_status}」：${value.message}`),
      },
      async execute(args, exec) {
        const allowed = new Set(['unseen', 'favorite', 'handled'])
        if (!allowed.has(String(args.review_status))) {
          throw new Error(`review_status 只能是 unseen / favorite / handled，收到：${args.review_status}`)
        }
        return request(config, `/api/workbench/candidates/${encodeURIComponent(String(args.item_id))}`, {
          method: 'PATCH',
          body: { review_status: String(args.review_status) },
          exec,
        })
      },
    }),
  )

  register(
    defineTool({
      name: 'xianyu_start_task',
      description:
        '立即启动一个监控任务的抓取（会真实访问闲鱼，请遵守频率限制）。用户说「现在跑一次」「立刻抓一下」时使用。',
      parameters: {
        task_id: { type: 'number', required: true, description: '任务 ID' },
      },
      output: {
        schema: { type: 'object', additionalProperties: true },
        render: (args, value) =>
          text(`任务 ${args.task_id} 已启动。${value.message ? `（${value.message}）` : ''}`),
      },
      async execute(args, exec) {
        if (!args.task_id) throw new Error('task_id 必填。')
        return request(config, `/api/tasks/start/${Number(args.task_id)}`, { method: 'POST', exec })
      },
    }),
  )

  register(
    defineTool({
      name: 'xianyu_stop_task',
      description: '停止正在运行的监控任务。用户说「停下来」「先别抓了」时使用。',
      parameters: {
        task_id: { type: 'number', required: true, description: '任务 ID' },
      },
      output: {
        schema: { type: 'object', additionalProperties: true },
        render: (args, value) =>
          text(`任务 ${args.task_id} 已停止。${value.message ? `（${value.message}）` : ''}`),
      },
      async execute(args, exec) {
        if (!args.task_id) throw new Error('task_id 必填。')
        return request(config, `/api/tasks/stop/${Number(args.task_id)}`, { method: 'POST', exec })
      },
    }),
  )

  register(
    defineTool({
      name: 'xianyu_create_task',
      description:
        '创建一个新的监控任务。关键词模式（decision_mode=keyword）同步创建，需要提供 keyword_rules；AI 模式（decision_mode=ai）需要提供 description 详细需求，返回后台 job 供后续查询。价格与筛选条件都可选。',
      parameters: {
        task_name: { type: 'string', required: true, description: '任务名，例如「显卡监控」' },
        keyword: { type: 'string', required: true, description: '搜索关键词，例如「GTX 1070」' },
        decision_mode: {
          type: 'string',
          description: 'keyword（默认，按规则命中）或 ai（调用模型判断）',
        },
        keyword_rules: {
          type: 'string',
          description: 'decision_mode=keyword 时必填，多个关键词用逗号分隔',
        },
        description: {
          type: 'string',
          description: 'decision_mode=ai 时必填，用自然语言写清想要什么',
        },
        min_price: { type: 'string', description: '最低价，例如 "500"' },
        max_price: { type: 'string', description: '最高价，例如 "1500"' },
        max_pages: { type: 'number', description: '每轮最多翻几页，默认 3' },
        free_shipping: { type: 'boolean', description: '是否只看包邮' },
        region: { type: 'string', description: '区域筛选，例如「浙江/杭州」；留空表示不限' },
        new_publish_option: { type: 'string', description: '发布时间范围，例如 "1天内"' },
        cron: { type: 'string', description: '定时表达式，例如 "0 */6 * * *"' },
        account_state_file: { type: 'string', description: '绑定的账号登录态文件名，例如 "acc_1.json"' },
        title_include_keywords: { type: 'string', description: '标题必须包含的词，逗号分隔' },
        title_exclude_keywords: { type: 'string', description: '标题命中即排除的词，逗号分隔' },
      },
      output: {
        schema: { type: 'object', additionalProperties: true },
        render: (_args, value) => {
          if (value.job) {
            return text(
              `AI 判定标准生成已开始：job_id=${value.job.job_id}（用 xianyu_generation_job 查询进度）。`,
            )
          }
          const task = value.task || {}
          return text(`任务已创建：ID ${task.id}，名称「${task.task_name}」。`)
        },
      },
      async execute(args, exec) {
        const splitKeywords = (raw) =>
          String(raw || '')
            .split(/[\n,，]+/)
            .map((item) => item.trim())
            .filter(Boolean)

        const mode = String(args.decision_mode || 'keyword').toLowerCase()
        const payload = {
          task_name: String(args.task_name),
          keyword: String(args.keyword),
          decision_mode: mode,
          max_pages: Number(args.max_pages) || 3,
          free_shipping: args.free_shipping == null ? true : Boolean(args.free_shipping),
          min_price: args.min_price == null ? null : String(args.min_price),
          max_price: args.max_price == null ? null : String(args.max_price),
          region: args.region ? String(args.region) : null,
          new_publish_option: args.new_publish_option ? String(args.new_publish_option) : null,
          cron: args.cron ? String(args.cron) : null,
          account_state_file: args.account_state_file ? String(args.account_state_file) : null,
          title_include_keywords: splitKeywords(args.title_include_keywords),
          title_exclude_keywords: splitKeywords(args.title_exclude_keywords),
        }

        if (mode === 'keyword') {
          const rules = splitKeywords(args.keyword_rules)
          if (rules.length === 0) {
            throw new Error('decision_mode=keyword 时 keyword_rules 不能为空。')
          }
          payload.keyword_rules = rules
          payload.description = args.description ? String(args.description) : ''
        } else if (mode === 'ai') {
          const description = String(args.description || '').trim()
          if (!description) throw new Error('decision_mode=ai 时 description（详细需求）不能为空。')
          payload.description = description
          payload.keyword_rules = splitKeywords(args.keyword_rules)
        } else {
          throw new Error(`decision_mode 只能是 keyword 或 ai，收到：${args.decision_mode}`)
        }

        return request(config, '/api/tasks/generate', { method: 'POST', body: payload, exec })
      },
    }),
  )

  register(
    defineTool({
      name: 'xianyu_generation_job',
      description: '查询 AI 任务创建（xianyu_create_task 的 ai 模式）的后台进度与结果。',
      parameters: {
        job_id: { type: 'string', required: true, description: '创建任务时返回的 job_id' },
      },
      output: {
        schema: { type: 'object', additionalProperties: true },
        render: (_args, value) => {
          const job = value.job || {}
          return text(
            `job ${job.job_id || ''}：${job.status || '未知状态'}` +
              (job.error ? `\n错误：${job.error}` : '') +
              (job.message ? `\n${job.message}` : ''),
          )
        },
      },
      async execute(args, exec) {
        if (!args.job_id) throw new Error('job_id 必填。')
        return request(config, `/api/tasks/generate-jobs/${encodeURIComponent(String(args.job_id))}`, {
          exec,
        })
      },
    }),
  )
}
