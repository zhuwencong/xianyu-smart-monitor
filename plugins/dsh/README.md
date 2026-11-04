# dsh-plugin-xianyu-monitor

把本机运行的**闲鱼智能监控**服务接进 [DeepSeek Harness](https://deepseek-harness.github.io/deepseek-harness/)。
插件本身不含爬虫，只做 HTTP 桥接：模型可以读候选商品、看任务与运行记录，也能启动/停止任务。

## 前提

本机已经跑着监控服务：

```bash
python -m src.app          # http://127.0.0.1:8000
```

服务没起来时，工具会返回一句明确的错误，而不是空结果。

## 安装

```bash
# 从 npm（发布后）
dsh plugin --profile demo add dsh-plugin-xianyu-monitor

# 从本地源码目录
dsh plugin --profile demo add ./plugins/dsh

# 从 Git（锁定 commit 更安全）
dsh plugin --profile demo add github:<GITHUB_USER>/xianyu-smart-monitor#<commit>
```

验证这一层被加载：

```bash
dsh --profile demo --dump-config   # 应出现 "# == dsh-plugin-xianyu-monitor"
dsh --profile demo
```

## 配置

组合包的默认值写在 `cordis.patch.yml`，可在自己的 profile patch 里覆盖同 id 的行：

```yaml
- id: xianyu-monitor
  name: dsh-plugin-xianyu-monitor
  config:
    baseUrl: http://127.0.0.1:8000
    timeoutMs: 15000
    defaultLimit: 12
```

| 字段 | 默认 | 说明 |
|---|---|---|
| `baseUrl` | `http://127.0.0.1:8000` | 监控服务地址；必须是 http(s) |
| `timeoutMs` | `15000` | 单次请求超时；候选很多时调大 |
| `defaultLimit` | `12` | `xianyu_list_candidates` 未传 limit 时的条数，上限 60 |

> 覆盖整行时要把所有需要的键重写一遍：patch 是**替换** `config`，不是深合并。

## 工具

| 工具 | 作用 |
|---|---|
| `xianyu_status` | 任务数、运行中、今日新增、待处理异常、账号健康、AI/通知是否配置 |
| `xianyu_list_candidates` | 候选商品，可按人工状态 / AI 判断 / 任务 / 搜索 / 排序 / 分页筛选 |
| `xianyu_list_tasks` | 任务列表与状态（运行中 / 等待 / 冷却 / 暂停）、最近一轮、下次运行 |
| `xianyu_task_runs` | 某任务最近若干轮运行记录与异常原因 |
| `xianyu_issues` | 需要人工处理的异常（账号失效、连续失败、AI 失败过多） |
| `xianyu_set_candidate_status` | 标记候选为未查看 / 已收藏 / 已处理（按闲鱼 `item_id`） |
| `xianyu_start_task` | 立即运行任务（**会真实访问闲鱼**） |
| `xianyu_stop_task` | 停止任务 |
| `xianyu_create_task` | 创建任务：`keyword` 模式同步创建，`ai` 模式返回后台 job |
| `xianyu_generation_job` | 查询 AI 创建任务的后台进度 |

典型提问：

- 「闲鱼监控现在怎么样，有要处理的吗？」→ `xianyu_status` → `xianyu_issues`
- 「今天有什么值得看的？」→ `xianyu_list_candidates` + `ai_verdict=recommend`
- 「显卡任务为什么没结果？」→ `xianyu_list_tasks` → `xianyu_task_runs`
- 「把这条标成已收藏」→ `xianyu_set_candidate_status`

## 安全边界

- 只与 `127.0.0.1` 通信，不外传任何数据。
- 不读取 `.env`、`state/` 或数据库文件，所有数据经由服务端 API。
- `xianyu_start_task` 会消耗账号风控额度；默认提示词建议模型在调用前确认。

## 开发

```bash
node --check plugins/dsh/index.js
node scripts/validate-market-index.mjs market/index.json
```

插件是纯 ESM、无构建步骤，`main` 直接指向 `index.js`，因此从 Git 安装时不需要 `prepare` 授权。
`@deepseek-ai/dsh-tools` 与 `@deepseek-ai/cordis` 声明在 `peerDependencies` + `devDependencies`，由宿主提供实例。

## 许可

MIT，见仓库根目录 [LICENSE](../../LICENSE)。
