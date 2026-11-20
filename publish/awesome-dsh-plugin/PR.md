# 上架 DSH 官方精选目录（awesome-dsh-plugin）

> 面向维护者。做完这一步，插件会出现在 **DeepSeek Harness 内置的「插件市场 / 发现」页**里，
> 而不是只藏在「自定义索引源」后面。

## 0. 先分清两条渠道

| 渠道 | 入口 | 数据来自 | 用户怎么看到 |
|---|---|---|---|
| **官方精选目录**（本文） | dsh-market「插件市场 / 发现」 | `awesome-dsh-plugin.com/plugins.json`，由 [`awesome-dsh-plugin/awesome-dsh-plugin`](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin) 仓库生成 | 搜索即见，无需任何配置 |
| **自建索引源** | 「发现 → 索引源 → 添加」 | 本仓库 `market/index.json`（format 1） | 用户手动粘贴索引 URL 后可见 |

两条渠道互不影响：官方目录被拒，自建索引仍然可用；反过来也一样。

**关键一点**：dsh-market 仓库本身**不收**条目——[它的 README 说得很直白](https://github.com/dsh-market/dsh-market#提交你的插件)，
插件列表来自精选目录，想上架就得去 `awesome-dsh-plugin` 提 PR，加**一个 YAML 文件**。

## 1. 已经备好的文件

| 本目录下的文件 | 目标仓库里的路径 | 必需？ |
|---|---|---|
| `data/plugins/zhuwencong__xianyu-smart-monitor--plugins-dsh.yml` | `data/plugins/zhuwencong__xianyu-smart-monitor--plugins-dsh.yml` | ✅ 必需 |
| `data/screenshots.json` | 内容合并进 `data/screenshots.json` | 可选（推荐） |

> ⚠️ 截图说明：`data/screenshots.json` 里用的是仓库 `static/img*.png`，拍的是**监控服务的 Web UI**
> （候选商品列表），不是 DSH 对话框里的 `xianyu_status` 输出。市场详情页会把它当作「这个插件的截图」展示，
> 所以**建议先补 1–2 张 DSH 里工具调用的截图**（`assets/` 下新图 + 改这份 JSON 的路径）再提 PR，
> 否则审稿人可能问「截图和插件不是一回事」。不补也能提，只是展示效果打折。

文件名规则来自 [contributing.md](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/blob/main/contributing.md)：

```
data/plugins/<owner>__<repo>.yml                       # 仓库根就是插件
data/plugins/<owner>__<repo>--<子包路径用-连接>.yml     # monorepo 子包
```

本插件是 monorepo 子包（`plugins/dsh`），所以文件名是
`zhuwencong__xianyu-smart-monitor--plugins-dsh.yml`。

## 2. 条目字段（每个都别改坏）

```yaml
url: https://github.com/zhuwencong/xianyu-smart-monitor/tree/main/plugins/dsh
name: zhuwencong/xianyu-smart-monitor#dsh
category: tools
description:
  en: "..."
  zh: "..."
```

| 字段 | 规则 | 当前值为什么这么写 |
|---|---|---|
| `url` | **必须与仓库完全一致**；子包要指到子目录（`/tree/main/<path>`） | 插件在 `plugins/dsh`，CI 会从 `plugins/` 子包里读 `dsh.bundle` |
| `name` | `owner/repo`，子包是 `owner/repo#<标签>`；这是列表里的链接文字 | `#dsh` 只是显示标签，不参与路径解析 |
| `category` | 取自固定枚举，**贴合实际功能**即可，选偏了维护者会改、不会打回 | `tools`（Tools & Capabilities）：插件注册的是 10 个 `xianyu_*` 工具 |
| `description.en` | **唯一必填的描述**；一句话、以 `.` 结尾、只讲功能、不带营销词；能被代码核对 | 逐个核对过 `plugins/dsh/index.js` 的工具名，数量与动作都对得上 |
| `description.zh` | 可选，维护者会补；写了就同样以 `。` 结尾 | 与英文一一对应 |
| `tarball` | 可选，GitHub Release 托管的 `https` `.tgz` | 本插件无构建步骤、源码可直接装，先不填 |

⚠️ **值里出现 `: `（冒号+空格）必须整体加引号**，否则 YAML 会把它读成嵌套键、CI 直接红。
本文件用的是双引号，改文案时**别把引号删了**。

## 3. 提交步骤

```bash
# 1) fork 并 clone 目录仓库
gh repo fork awesome-dsh-plugin/awesome-dsh-plugin --clone
cd awesome-dsh-plugin
git checkout -b add/xianyu-smart-monitor

# 2) 放条目（在本仓库根目录执行）
mkdir -p ../awesome-dsh-plugin/data/plugins
cp publish/awesome-dsh-plugin/data/plugins/zhuwencong__xianyu-smart-monitor--plugins-dsh.yml \
   ../awesome-dsh-plugin/data/plugins/

# 3) 可选：截图。把 publish/awesome-dsh-plugin/data/screenshots.json 里的键值
#    合并进 ../awesome-dsh-plugin/data/screenshots.json（不要整份覆盖）

# 4) 重新生成两个 README —— 必须，且不要手改 README
cd ../awesome-dsh-plugin
npm ci
node scripts/generate-readme.mjs

# 5) 提交
git add data/plugins data/screenshots.json README.md README.zh.md
git commit -m "Add zhuwencong/xianyu-smart-monitor"
git push -u origin add/xianyu-smart-monitor
```

PR 正文用仓库的 `.github/pull_request_template.md`，逐条勾上即可；建议再补一段
「插件做什么 / 需要本机有服务在跑 / 数据只走 127.0.0.1」——审稿人第一条就看这个。

## 4. 现在能不能过 CI：逐条对照

| 要求（来自 contributing.md / PR 模板） | 本仓库当前状态 |
|---|---|
| `package.json` 声明 `dsh.bundle`（只声明 `dsh.client` 会被拒） | ✅ `plugins/dsh/package.json` → `dsh.bundle.patch: ./cordis.patch.yml`，文件存在 |
| 子包位置在根 / `packages/` / `plugins/` / `apps/` | ✅ `plugins/dsh` |
| 仓库创建满 1 天、提交数 ≥ 10 | ✅ 2026-11-04 创建，当前 14 个提交 |
| 仓库有 `dsh-plugin` topic | ⚠️ 待打（Settings → Topics） |
| 描述属实、无营销词 | ✅ 描述里的「ten tools」与 `index.js` 里 10 个 `xianyu_*` 工具一致 |
| `@deepseek-ai/*` 用 `peerDependencies` 而非 `dependencies` | ✅ 已是 peer + dev |
| 只改自己那一条，不动别人 | ✅ 本 PR 只新增一个文件 |

CI 通过只是**前置条件**，合入前维护者会真读代码（`contributing.md` 明确写了这一点）。

## 5. 最常见的打回原因（按概率）

1. **只声明 `dsh.client`** — 本仓库不是这个情况，别在后续改动里删掉 `dsh.bundle`。
2. **描述夸大** — 别写「支持自动砍价 / 全平台」；写了就要在代码里找得到。
3. **YAML 没引号** — `: ` 触发解析失败。
4. **手改 README** — README 是生成的，改了也会被 `generate-readme.mjs` 覆盖并导致 diff 冲突。
5. **仓库太新 / 提交太少** — 自动检查，不达标就先把活干完再来。

## 6. 合并之后

- 站点与 `plugins.json` 自动重建，通常一天内出现在 dsh-market 的「发现」页。
- 同一份目录也以 `dsh-plugin-catalog` 发到 npm，所以国内网络也能搜到。
- 自建索引源（`market/index.json`）**继续保留**：它是镜像/备份，也是不经目录审核的兜底。

## 7. 两个预发布版本的坑（先知道，别踩）

当前桌面端宿主是 **DSH 0.2.1-rc.2**，而 `plugins/dsh/package.json` 写的是：

```jsonc
"engines": { "dsh": ">=0.2.0" },
"peerDependencies": { "@deepseek-ai/cordis": "*", "@deepseek-ai/dsh-tools": "*" }
```

node-semver 的规则是：**预发布版本只有落在「同 major.minor.patch 且自身带预发布标签」的比较符上才算满足**。
于是 `>=0.2.0`、`*` 这类范围都**不匹配** `0.2.1-rc.2`。实际影响分两处：

- **市场侧**：dsh-market 把这种「预发布 vs `*`」的结论当作 *unknown* 处理（`lib/compatibility.js` 的头注释写了），
  只会显示「未声明/未知」，不会把插件从列表里隐藏，所以**不影响被搜到**。
- **安装侧**：dsh 用 pnpm，默认 `strict-peer-dependencies=false`，只会告警。
  但 npm 用户/以后改成 `dependencies` 就会撞 `ERESOLVE`。

真要用范围而不是 `*`，照 dsh-market 自己的写法逐条列预发布分支（每个 minor 一条，`-0` 收尾）：

```jsonc
"peerDependencies": {
  "@deepseek-ai/dsh-tools": "^0.2.0-rc.1 || ^0.2.1-rc.1"
}
```

> 结论：**这次先不改**，只把规则记下来；等确定要长期维护版本范围时再动，避免为了格式把能装的插件改成装不上。
