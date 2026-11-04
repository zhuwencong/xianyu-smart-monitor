---
name: xianyu-monitor
display_name: 闲鱼智能监控
display_name_en: Xianyu Smart Monitor
description: 查询本机闲鱼监控的候选商品、任务状态与运行异常，并把商品标记为收藏/已处理。当用户提到闲鱼、二手、捡漏、监控任务、显卡/手机收盘价、候选商品、登录失效时使用。
description_zh: 把本机闲鱼智能监控抓到的候选商品、任务与运行记录带进对话，支持筛选、解读与标记处理。
description_en: Bring candidates, task status and run logs from a locally running Xianyu monitor into the conversation.
examples_zh:
  - "今天闲鱼监控抓到什么值得看的？"
  - "显卡那个任务为什么两天没出结果？"
  - "把评分 85 以上的候选列出来，帮我看哪几个值得联系卖家"
  - "第二条收藏了，别再推给我"
examples_en:
  - "What did my Xianyu monitor find today?"
  - "Why has the GPU task produced nothing for two days?"
allowed-tools: Bash, Read
version: 0.1.0
author: 闲鱼智能监控 Contributors
---

# 闲鱼智能监控

这个技能把**本机正在运行的闲鱼监控服务**（FastAPI，默认 `http://127.0.0.1:8000`）接到对话里。
服务负责抓取与 AI 分析，本技能只负责**查**和**少量控制**。

## 先决条件（每次会话先做一次）

1. 确认服务在线。运行 `status` 命令：
   ```bash
   python scripts/xy.py status
   ```
2. 如果返回 `连不上监控服务 ...`，说明后端没起来。告诉用户：
   > 需要先启动监控服务：在项目目录执行 `python -m src.app`（或双击 `启动闲鱼监控.bat`），
   > 然后回到对话里说「好了」。
   不要尝试自己安装依赖或改配置。
3. 如果服务在别的端口，用 `--base-url http://127.0.0.1:<port>` 覆盖，不要改脚本。

> Windows 上如果 `python` 不可用，把命令里的 `python` 换成 `py -3`。脚本只用标准库，不需要虚拟环境。

## 命令

所有命令默认输出精简 JSON（已经裁掉无关字段），加 `--raw` 才是服务端原始结构。

| 用户意图 | 命令 |
|---|---|
| 整体状态、有没有要处理的 | `python scripts/xy.py status` |
| 列出待处理异常 | `python scripts/xy.py issues` |
| 有哪些任务、跑没跑、下次何时 | `python scripts/xy.py tasks` |
| 最近抓到的候选商品 | `python scripts/xy.py candidates --limit 10` |
| 只看 AI 建议关注的 | `python scripts/xy.py candidates --verdict recommend` |
| 只看需要核实的 | `python scripts/xy.py candidates --verdict verify` |
| 按关键词找 | `python scripts/xy.py candidates --query "3060"` |
| 按价格排序 | `python scripts/xy.py candidates --sort price_asc` |
| 某个任务的历史结果 | `python scripts/xy.py candidates --task-id 3` |
| 某任务最近几轮运行 | `python scripts/xy.py runs --task-id 3 --limit 5` |
| 标记收藏 / 已处理 / 未查看 | `python scripts/xy.py mark --item-id 1097810856010 --status favorite` |
| 立即跑一轮 | `python scripts/xy.py start --task-id 3` |
| 停止任务 | `python scripts/xy.py stop --task-id 3` |
| 新建任务（关键词模式） | `python scripts/xy.py create --task-name "显卡监控" --keyword "显卡" --mode keyword --keyword-rules "3060,3070" --max-price 1500` |
| 新建任务（AI 模式） | `python scripts/xy.py create --task-name "真我手机" --keyword "真我GT8Pro" --mode ai --description "只要个人自用、无拆修、带原盒，价格 3000 以内"` |

接口细节见 [@references/api.md](references/api.md)，启动与部署见 [@references/install.md](references/install.md)。

## 怎么读结果

`ai_label` 是 AI 对商品的最终判断，只有四个值：

- **建议关注**：AI 认为符合需求且价格合理，优先呈现给用户。
- **需核实**：方向对但缺关键信息（如电池健康、维修史、烤机图），要提醒用户「买前必问」。
- **不匹配**：不符合需求，除非用户明确要放宽条件，否则不要推荐。
- **AI 分析失败**：模型调用出错，**不代表商品不合格**，不要把它当作「不好」来汇报。

`ai_score` 是 0-100 的综合评分（匹配 / 价格 / 卖家 / 凭证四维加权）。排序默认 `smart`，已经按评分与判断优先级排好，通常不需要重排。

`missing_checks` 是 AI 明确指出的「待核实项」，回答「这个能不能买」时必须引用它，而不是自己编理由。
`risk_tags` 是风险标签，出现「无购买凭证」「无烤机测试图」「成色伊拉克」这类标签时要主动提示。

`review_status` 是**用户**的人工状态（`unseen` / `favorite` / `handled`），与 AI 判断无关。

## 回答风格

- 先给结论（今天有几条值得看、最值得看的是哪条），再列明细。
- 每条候选必须带：标题（可截断）、价格、AI 判断、**一句**理由、待核实项、链接。
- 不要复述 JSON 字段名，翻译成人话。
- 没有候选时不要道歉式空转，直接说明可能原因：任务暂停 / 登录态失效 / 筛选太严 / 今天确实没新货，并给出对应的下一步命令。

## 边界（重要）

- **`start` 会真实访问闲鱼并消耗账号风控额度**。用户没明确说「现在跑一次」时不要调用；同一任务 10 分钟内不要重复 `start`。
- **不要为了「多抓点」去改抓取频率、翻页数或代理**。这些参数属于项目配置，不属于本技能。
- 不要读取、打印或转述 `state/` 下的登录态文件、`.env` 里的 Key。技能只需要 HTTP 接口。
- `mark` 会改动用户数据，执行前用一句话确认（例如「已把第二条标记为收藏」），但不需要反问。
- 如果用户问的东西技能覆盖不到（比如「帮我自动砍价」），直接说明不支持，不要拼凑。

## 故障排查

| 现象 | 处理 |
|---|---|
| `连不上监控服务` | 服务未启动，或端口不同（`--base-url`） |
| `HTTP 401` | 用户开了 `WEB_STRICT_AUTH=true`；本技能不带登录态，请让用户关闭严格模式或在浏览器里操作 |
| `HTTP 422` | `create` 参数不合法（AI 模式缺 description、关键词模式缺 keyword-rules、cron 表达式错） |
| `HTTP 404` 且是 `task_id` 相关 | 任务 ID 不存在，先跑 `tasks` 确认 |
| 输出中文乱码 | 该环境不支持 UTF-8 控制台；用 `--raw` 前先 `chcp 65001`，或让用户直接在 Web UI 看 |
