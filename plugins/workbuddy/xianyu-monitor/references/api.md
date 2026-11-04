# 监控服务接口速查（技能用到的部分）

所有接口都在本机 `http://127.0.0.1:8000` 下，返回 JSON。
默认配置（`WEB_STRICT_AUTH=false` + 绑定回环地址）下，本机请求无需登录。

## 工作台

### `GET /api/workbench/summary`

整体概况。

```json
{
  "task_count": 4,
  "enabled_task_count": 0,
  "running_count": 0,
  "today_count": 1,
  "pending_count": 2,
  "issues": [{ "id": "account-acc_3", "type": "account", "title": "账号 acc_3 登录失效", "detail": "...", "severity": "warning" }],
  "accounts": [{ "name": "acc_3", "status": "needs_update", "last_failure_at": "2026-11-04T12:07:38" }],
  "account_count": 4,
  "account_alert_count": 1,
  "ai_configured": true,
  "ai_model": "deepseek-flash",
  "notification_channels": ["pushplus"],
  "daily_report_enabled": true,
  "daily_report_hour": 21
}
```

### `GET /api/workbench/candidates`

| 查询参数 | 取值 | 说明 |
|---|---|---|
| `review_status` | `all` / `unseen` / `favorite` / `handled` | 人工处理状态 |
| `ai_verdict` | `all` / `recommend` / `verify` / `mismatch` / `failed` | AI 判断 |
| `task_id` | 整数 | 只看某个任务 |
| `q` | 字符串 | 标题 / 任务名 / 卖家搜索 |
| `sort` | `smart` / `score` / `newest` / `price_asc` / `price_desc` | 排序 |
| `page` | ≥1 | 页码 |
| `limit` | 1-60 | 每页条数 |

返回：

```json
{
  "total": 37, "page": 1, "limit": 12,
  "counts": { "unseen": 372, "favorite": 2, "handled": 0 },
  "items": [{
    "id": 39,
    "item_id": "1097810856010",
    "title": "...",
    "price": 208.0,
    "price_display": "¥208",
    "ai_verdict": "recommend",
    "ai_label": "建议关注",
    "ai_score": 89,
    "ai_value_score": 88,
    "ai_summary": "当前售价 208 元，远低于市场均价…",
    "ai_reason": "...",
    "missing_checks": ["专业卡游戏性能较弱"],
    "risk_tags": ["显存仅2GB"],
    "criteria": [{ "key": "price", "label": "价格合理度", "status": "PASS", "comment": "..." }],
    "seller": { "name": "强毅中和", "credit": "卖家信用优秀", "rating": "100.00%", "location": "湖南" },
    "task_id": 1, "task_name": "显卡监控（AI）", "keyword": "显卡",
    "crawl_time": "2026-11-02T00:32:51", "crawl_label": "11-02 00:32",
    "location": "湖南", "link": "https://www.goofish.com/item?id=1097810856010",
    "review_status": "unseen", "review_label": "未查看",
    "market": { "avg": 526.98, "low": 300, "high": 700, "samples": 12, "label": "明显低于均价" }
  }]
}
```

注意 `id`（数据库自增）与 `item_id`（闲鱼商品 ID）不是一回事。`mark` 用的是 `item_id`。

### `PATCH /api/workbench/candidates/{item_id}`

```json
{ "review_status": "favorite" }
```

返回 `{"message": "处理状态已更新", "review_status": "favorite"}`。
`review_status` 只接受 `unseen` / `favorite` / `handled`，其它值返回 400。

### `GET /api/workbench/tasks`

```json
{
  "counts": { "all": 4, "running": 0, "waiting": 0, "cooldown": 0, "paused": 4 },
  "items": [{
    "id": 1,
    "task_name": "显卡监控（AI）",
    "keyword": "显卡",
    "budget": "≤¥1000",
    "enabled": false,
    "is_running": false,
    "cron": "0 */6 * * *",
    "next_run_at": null,
    "next_run_label": "未排程",
    "status": "paused",
    "status_label": "已暂停",
    "status_detail": "不会自动运行",
    "paused_until": null,
    "latest_run": { "status": "failed", "status_label": "异常退出", "started_at": "...", "saved_count": 0, "summary": "登录态失效，任务被重定向到登录页。" },
    "recent_runs": []
  }]
}
```

`status` 取值：`running` / `waiting` / `cooldown` / `paused`。

### `GET /api/workbench/tasks/{task_id}/runs?limit=5`

```json
{
  "task_id": 1,
  "task_name": "显卡监控（AI）",
  "runs": [{
    "id": "run-1",
    "status": "completed",
    "status_label": "已完成",
    "started_at": "2026-11-04T12:00:01",
    "finished_at": "2026-11-04T12:06:30",
    "saved_count": 3,
    "summary": "本轮新增 3 条候选",
    "timeline": [{ "at": "2026-11-04T12:00:01", "text": "开始执行监控任务" }]
  }]
}
```

`status` 取值：`completed` / `partial` / `no_new` / `failed` / `stopped` / `running`。

### `GET /api/workbench/issues`

```json
{ "pending_count": 2, "issues": [{ "type": "account", "title": "...", "severity": "warning" }] }
```

### `GET /api/workbench/accounts`

账号健康度：`status` 为 `ok` / `needs_update`。

## 任务控制

| 接口 | 说明 |
|---|---|
| `GET /api/tasks` | 全部任务（原始字段，含 `ai_prompt_criteria_file` 等） |
| `GET /api/tasks/{id}` | 单个任务 |
| `POST /api/tasks/start/{id}` | 立即启动，返回 `{"message": "..."}` |
| `POST /api/tasks/stop/{id}` | 停止 |
| `POST /api/tasks/generate` | 创建任务；`decision_mode=ai` 返回 202 + `job`，`keyword` 直接返回 `task` |
| `GET /api/tasks/generate-jobs/{job_id}` | 查 AI 创建进度 |

`POST /api/tasks/generate` 请求体（字段均可选，除标注）：

```json
{
  "task_name": "显卡监控",
  "keyword": "显卡",
  "decision_mode": "keyword",
  "keyword_rules": ["3060", "3070"],
  "description": "",
  "min_price": "500",
  "max_price": "1500",
  "max_pages": 3,
  "free_shipping": true,
  "region": "浙江/杭州",
  "new_publish_option": "1天内",
  "cron": "0 */6 * * *",
  "account_state_file": "acc_1.json",
  "title_include_keywords": [],
  "title_exclude_keywords": []
}
```

校验规则：
- `decision_mode=keyword` 时 `keyword_rules` 不能为空
- `decision_mode=ai` 时 `description` 不能为空
- `cron` 必须是合法的 5 段 cron 表达式
- `min_price` / `max_price` 是**字符串**

## 错误约定

FastAPI 默认结构：

```json
{ "detail": "任务未找到" }
```

技能脚本会把 `detail` 提取出来放进 `{"ok": false, "error": "..."}`，并以退出码 1 结束。
