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

> **本轮核对（2026-11-20，二次）**：对照上游 `contributing.md` 与 `.github/pull_request_template.md`
> 修正了两处**已经过期的说法**——
> 1. README 不再由提交者维护：合并后由 `main` 自动生成，手改必冲突；
> 2. 截图改为在**自己仓库**的 `plugins/dsh/screenshots.json` 声明，不再合并进目录仓库的 `data/screenshots.json`。
>
> 因此提交物收敛为**一个 YAML 文件**（见第 1 节）。仓库状态：插件版本 **0.1.2**，`v1.0.0` tag 已打。

## 1. 已经备好的文件

**提交物只有一个文件。** 目录仓库的 README 由维护者在合并后自动生成，**不要**手改，也不用提交
（官方 PR 模板原话：*"The READMEs are regenerated on `main` after merge: don't edit them by hand,
and you don't need to commit them either"*）。

| 本目录下的文件 | 目标仓库里的路径 | 必需？ |
|---|---|---|
| `data/plugins/zhuwencong__xianyu-smart-monitor--plugins-dsh.yml` | `data/plugins/zhuwencong__xianyu-smart-monitor--plugins-dsh.yml` | ✅ 必需 |

> **截图不在这个 PR 里加。** 官方现在要求把 `screenshots.json` 放在**插件自己的**目录里
> （即本仓库 `plugins/dsh/screenshots.json`，紧挨 `package.json`），1–8 张、路径相对该文件；
> 以后换图不用再提 PR。当前这份指向 `../../static/img*.png`，拍的是监控服务 Web UI，
> 建议之后补 1–2 张 DSH 里 `xianyu_status` 调用的实拍再替换。
> `scripts/check-publish-artifacts.mjs` 会校验它的张数、相对路径与文件是否存在。

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
| `tarball` | 可选，GitHub Release 托管的 `https` `.tgz`；有它就优先走预构建安装 | 0.1.2 的 tgz 已打好（见 2.1），**上传到 Release 后**再填这一行 |

⚠️ **值里出现 `: `（冒号+空格）必须整体加引号**，否则 YAML 会把它读成嵌套键、CI 直接红。
本文件用的是双引号，改文案时**别把引号删了**。

### 2.1 可选但推荐：挂一个预构建 tarball

仓库已经有 `v1.0.0` tag，把插件单独打包挂上去，市场会优先给「下载即装」，省掉源码构建和 `allowBuilds` 授权：

```bash
cd plugins/dsh
npm pack --pack-destination ../../release
# → release/dsh-plugin-xianyu-monitor-0.1.2.tgz
#   4 个文件：package.json / index.js / cordis.patch.yml / README.md（10.6 kB）
```

1. 在 GitHub 上编辑已有的 `v1.0.0` Release，把 tgz 作为附件上传（不要改名）；
2. 上传成功后，在条目末尾加一行：

```yaml
tarball: https://github.com/zhuwencong/xianyu-smart-monitor/releases/latest/download/dsh-plugin-xianyu-monitor-0.1.2.tgz
```

**没上传就别填**——填了会把用户带到 404，比不填更糟。版本号变了要重新 pack、重新上传，并同步改这一行。
`latest/download` 指向最新的 Release；如果之后用 `v1.1.0` 发布，把文件名里的版本号一起换掉即可。

## 3. 提交步骤

```bash
# 1) fork 并 clone 目录仓库（fork 只能在网页上点，没有 gh 也能走完）
gh repo fork awesome-dsh-plugin/awesome-dsh-plugin --clone
cd awesome-dsh-plugin
git checkout -b add/xianyu-smart-monitor

# 2) 放条目（在本仓库根目录执行）——整个提交只有这一个文件
cp ../ai-goofish-monitor/publish/dsh/data/plugins/zhuwencong__xianyu-smart-monitor--plugins-dsh.yml \
   data/plugins/

# 3) 想先看 README 效果再跑生成；提交时不要带上它
npm ci
node scripts/generate-readme.mjs

# 4) 提交：只 add 条目本身
git add data/plugins/zhuwencong__xianyu-smart-monitor--plugins-dsh.yml
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
| 仓库创建满 1 天 | ✅ 2026-11-04 创建（提交数下限已于 2026-09-03 取消，不再卡 ≥10） |
| 仓库有 `dsh-plugin` topic | ⚠️ 待打（Settings → Topics）；自动检查不校验，但 PR 模板里是人工勾选项 |
| 描述属实、无营销词 | ✅ 描述里的「ten tools」与 `index.js` 里 10 个 `xianyu_*` 工具一致 |
| `@deepseek-ai/*` 用 `peerDependencies` 而非 `dependencies` | ✅ 已是 peer + dev |
| 只改自己那一条，不动别人 | ✅ 只新增 `data/plugins/zhuwencong__xianyu-smart-monitor--plugins-dsh.yml` 一个文件；不提交 README |
| 截图 | ✅ 放在本仓库 `plugins/dsh/screenshots.json`（4 张，相对路径），无需进这个 PR |

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
