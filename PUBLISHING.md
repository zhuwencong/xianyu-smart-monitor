# 发布手册：开源 → WorkBuddy 市场 → DSH 插件市场

这份文档是给**维护者**看的操作手册，按顺序做完三件事：

1. 把仓库安全地开源出去（GitHub）
2. 上架 WorkBuddy 技能市场
3. 上架 DeepSeek Harness 插件市场

每一步都写清「命令 / 字段 / 会被打回的原因」。

---

## 0. 开工前的现状体检

我已经在仓库里做完了这些准备，你只需要确认：

| 项目 | 状态 | 说明 |
|---|---|---|
| `.gitignore` 加固 | ✅ | 运行时数据、登录态、备份、临时文件全部排除 |
| `.gitattributes` | ✅ | 换行统一，`.bat` 保持 CRLF |
| 仓库卫生检查 | ✅ | 已删除/忽略 3 处敏感残留（见下） |
| `LICENSE` | ✅ 保留 | 上游 MIT 声明原样保留（法律要求） |
| `NOTICE` | ✅ 新增 | 衍生关系、上游署名、改动清单、商标声明 |
| `SECURITY.md` | ✅ 新增 | 私密报告渠道 + 部署者必读的信任边界 |
| `CONTRIBUTING.md` | ✅ 新增 | 开发环境、提交前自检、Commit 规范 |
| `CODE_OF_CONDUCT.md` | ✅ 新增 | 行为准则 |
| `CHANGELOG.md` | ✅ 新增 | 相对上游的逐条变更 |
| Issue / PR 模板 | ✅ 新增 | Bug、功能、PR 三套 |
| CI | ✅ 新增 | 敏感信息扫描 + pytest + 前端构建 + Docker + 插件校验 |
| 插件与市场 | ✅ 新增 | `plugins/dsh`、`plugins/workbuddy`、`market/`、发布脚本 |
| 测试基线 | ✅ 修复 | 本地 5 个失败用例已处理（3 个环境隔离、1 个 Windows 专属、1 个断言过时），当前 **216 passed / 5 skipped** |
| 临时目录兜底 | ✅ 加固 | `TEMP` 不可写或被拦截时自动切 `.tmp`；探测带超时，不会把启动/测试卡死 |

### 已处理的三处敏感残留

| 文件 | 风险 | 处理 |
|---|---|---|
| `.env.bak_1102/1103/…` | 含真实 `OPENAI_API_KEY`，原 `.gitignore` 只忽略 `.env` | 新规则 `.env.*` 覆盖 |
| `state/acc_*.json` | 闲鱼登录态，等于账号被接管 | 原本已忽略，保留 |
| `.backups/`（含 `app.sqlite3`） | 含商品与卖家数据 | 新增忽略 |

**提交前请再跑一遍**：

```bash
git status --short --ignored | grep -E '\.env|state/|data/|\.sqlite3|cookies'
# 应该全部带 !! 前缀（ignored），不能出现在 untracked/staged 里
```

---

## 1. 开源发布到 GitHub

### 1.1 初始化仓库

```bash
cd ai-goofish-monitor
git init -b main
git add -A
git status --short          # ★ 逐行看一眼，确认没有 .env / state/ / data/
git commit -m "chore: 初始开源版本 1.0.0"
```

### 1.2 填充仓库身份（把占位符换成你的）

README、package.json、市场索引里现在是 `zhuwencong` 和 `xianyu-smart-monitor`。

```bash
# 普通用户（仓库名用默认的 xianyu-smart-monitor）
pwsh -File scripts/replace-placeholders.ps1 -GitHubUser yourname

# 想换仓库名 / 署名 / 安全邮箱
pwsh -File scripts/replace-placeholders.ps1 `
  -GitHubUser yourname `
  -Repo xianyu-monitor `
  -Author "你的名字" `
  -SecurityEmail you@example.com
```

先预演一次看会改哪些文件：加 `-DryRun`。

替换后重新生成市场索引与校验：

```bash
node scripts/build-market-index.mjs --repo-url https://github.com/yourname/xianyu-smart-monitor
node scripts/check-plugin-versions.mjs
```

### 1.3 建远程仓库并推送

```bash
git remote add origin https://github.com/yourname/your-repo.git
git push -u origin main
```

推送后再跑一次索引生成（这样 commit SHA 与远端一致）：

```bash
node scripts/build-market-index.mjs
git add market/index.json && git commit -m "chore: 刷新市场索引" && git push
```

### 1.4 仓库设置（5 分钟，但很关键）

| 设置 | 位置 | 值 |
|---|---|---|
| Description | Settings → General | 闲鱼多任务智能监控：AI 判断候选商品、价格洞察、多账号轮换 |
| Topics | 同上 | `xianyu` `playwright` `fastapi` `vue3` `ai` `secondhand` `dsh-plugin` |
| Private vulnerability reporting | Settings → Code security | **开启**（`SECURITY.md` 里承诺了） |
| Actions 权限 | Settings → Actions → General | 默认 `Read repository contents` 即可 |
| Pages | Settings → Pages | Source = Deploy from a branch，分支 `main`，目录 `/`（下一步用 `market/`） |
| Releases | — | 打 `v1.0.0` tag，附 zip 与 CHANGELOG 摘要 |

### 1.5 首个 Release

```bash
git tag -a v1.0.0 -m "1.0.0 首个公开版本"
git push origin v1.0.0
```

Release 正文直接贴 `CHANGELOG.md` 里 `## [1.0.0]` 一节。
附件建议只放：源码 zip（GitHub 自动生成）+ `release/xianyu-monitor.zip`。

---

## 2. 上架 WorkBuddy 技能市场

### 2.1 打包

```bash
node scripts/package-workbuddy-skill.mjs
```

产物：`release/xianyu-monitor.zip`，结构必须是**根目录下就是技能目录**：

```
xianyu-monitor/
├── SKILL.md
├── references/api.md
├── references/install.md
└── scripts/xy.py
```

### 2.2 必填字段（已写在 `SKILL.md` frontmatter）

| 字段 | 当前值 | 说明 |
|---|---|---|
| `name` | `xianyu-monitor` | 技能标识，小写连字符 |
| `display_name` | 闲鱼智能监控 | 市场中文名 |
| `display_name_en` | Xianyu Smart Monitor | 市场英文名 |
| `description` | 一段带触发词的描述 | 决定被召回的概率，写清「闲鱼/二手/捡漏/候选商品」 |
| `description_zh` / `description_en` | 详情页简介 | 一句话 |
| `version` | `0.1.0` | 与 DSH 插件同步 |
| `author` | 闲鱼智能监控 Contributors | 换成你的署名 |
| `allowed-tools` | `Bash, Read` | 只需要执行脚本与读参考文件 |
| `examples_zh` / `examples_en` | 各 4 条 | 展示在详情页「试试这样用」 |

### 2.3 提交

1. 打开 [WorkBuddy 开放平台](https://open.workbuddy.cn/)，入驻并完成主体信息
2. **技能 → 添加技能 → 创建技能**，或直接在控制台上传 zip
3. 填展示信息（图标、分类、截图）、关联 `author`
4. 提交审核

### 2.4 常见「解析失败」原因

| 现象 | 原因 | 修法 |
|---|---|---|
| 上传后解析失败 | zip 里多套了一层目录（`xianyu-monitor/xianyu-monitor/SKILL.md`） | 用本仓库脚本打包，别手动压缩 |
| frontmatter 报错 | 缺 `display_name_en` / `author` / `version` | 对照 2.2 表补全 |
| 技能装上但跑不动 | 脚本用了项目 `.venv` 的依赖 | `scripts/xy.py` 只用标准库，不要加第三方 import |
| 一执行就报连不上 | 用户没启动监控服务 | `SKILL.md` 已要求先跑 `status` 并给出提示，保持这段不要删 |
| 中文输出乱码 | 控制台 GBK | `xy.py` 已强制 UTF-8 输出，别改回去 |
| 审核要求说明数据用途 | 技能会读本机服务 | 在详情页写明「仅访问 127.0.0.1，不上传任何数据」 |

---

## 3. 上架 DeepSeek Harness 插件市场

DSH 的市场本质是**一个 JSON 索引 + 一个图标目录**，托管在任意静态站点。

### 3.1 先决定分发方式

| 方式 | 优点 | 缺点 | 适用 |
|---|---|---|---|
| **Git + commit SHA**（当前默认） | 无需 npm 账号，改动即生效 | 用户首次安装会拉源码；需锁定 SHA | 首发推荐 |
| npm 包 | 安装最快，无 `prepare` 授权问题 | 需要发布流程与 token | 稳定后再切 |

当前 `package.json` 是纯 ESM 且 `main` 直接指向 `index.js`，**没有构建步骤**，所以 Git 安装不需要用户授权 `prepare` 脚本 —— 这是刻意设计的。

### 3.2 生成索引

```bash
node scripts/build-market-index.mjs
node scripts/validate-market-index.mjs market/index.json
node scripts/check-plugin-versions.mjs
```

生成的 `market/index.json` 关键字段：

```json
{
  "format": 1,
  "plugins": [{
    "name": "dsh-plugin-xianyu-monitor",
    "versions": [{
      "version": "0.1.0",
      "publishTimestamp": 1793…,
      "source": { "type": "git", "url": "https://github.com/…", "commit": "40位SHA", "path": "plugins/dsh" },
      "engines": { "dsh": ">=0.2.0" }
    }]
  }]
}
```

**易错点**：
- `commit` 必须是 40 位完整 SHA，短 SHA 会被整份索引拒绝
- `url` 必须是 `https:`；`git@` 形式要先转成 https（生成器已处理）
- `engines.dsh` 要与 `plugins/dsh/package.json` 的 `engines.dsh` 一致，否则安装时二次校验不过
- 改了 `plugins/dsh` 却忘了重新提交 → SHA 指向旧代码

### 3.3 托管索引

**GitHub Pages（推荐）**

1. Settings → Pages → Deploy from a branch → `main` → `/ (root)`
2. 等 1 分钟，访问验证：
   ```
   https://yourname.github.io/your-repo/market/index.json
   ```
3. 索引里的图标是相对路径 `icons/xianyu-monitor.svg`，会自动解析成
   `…/market/icons/xianyu-monitor.svg`，不用改。

**对象存储**（OSS/COS/R2）：把 `market/` 整个目录传上去，确保 JSON 返回 2xx、不被重定向、`Content-Type: application/json`。

### 3.4 用户怎么装

DSH → 插件 → 实验性插件旁的「更多」→ 打开 **自定义插件市场** → **发现** 标签页 →
**添加索引源** → 粘贴 `…/market/index.json` → 在卡片上点安装。

命令行等价：

```bash
dsh plugin --profile demo add github:yourname/your-repo#<commit>
```

### 3.5 发布新版本的循环

```bash
# 1. 改版本号（三处必须同步）
#    plugins/dsh/package.json
#    plugins/workbuddy/xianyu-monitor/SKILL.md  (frontmatter version)
# 2. 提交
git add -A && git commit -m "release: 0.1.1"
# 3. 重新生成索引（会自动写入新 SHA）
node scripts/build-market-index.mjs
node scripts/validate-market-index.mjs market/index.json
node scripts/check-plugin-versions.mjs
# 4. 推送
git add -A && git commit -m "chore: 刷新市场索引 0.1.1" && git push
```

`scripts/check-plugin-versions.mjs` 就是防你漏改三处之一的。

---

## 4. 上架前最后 5 件事（别跳）

- [ ] **改默认密码**：`WEB_PASSWORD` 不要留 `admin123`
- [ ] **清本地数据**：`data/`、`state/`、`logs/`、`images/` 在你的机器上留着，但确认没进 git
- [ ] **换占位符**：`scripts/replace-placeholders.ps1`，然后 `grep -r 'zhuwencong' .` 应为空
- [ ] **CI 绿灯**：推送后看 Actions，四个 job 全过
- [ ] **README 截图是新的**：`static/img*.png` 如果是上游旧图，读者会觉得货不对版

---

## 5. 合规风险（开源这类工具必须知道）

| 风险 | 说明 | 我已做的 | 你还需要做 |
|---|---|---|---|
| 衍生作品署名 | MIT 要求保留原版权声明 | `LICENSE` 原样保留 + `NOTICE` 说明 | 不要删这两处 |
| 商标 | 「闲鱼」是阿里商标 | `NOTICE` 声明非官方、无关联 | 仓库名/应用名不要暗示官方 |
| 用户协议 | 抓取可能违反闲鱼条款 | README/DISCLAIMER 明示仅供学习 | 不要加「提高频率」「绕过验证码」类功能 |
| 个人数据 | 数据库含卖家昵称、商品信息 | `.gitignore` 排除 `data/` | 不要把 `app.sqlite3` 传到任何地方 |
| 凭据 | `.env` 与 `state/` 是账号命门 | 已忽略，`SECURITY.md` 写明 | 一旦误传，**立刻换号改密**并 `git filter-repo` 清历史 |
| 平台审核 | 市场可能要求说明数据流向 | 插件只连 127.0.0.1 | 详情页写清「不上传数据」 |

---

## 6. 一张图看全流程

```
本地仓库
  │  git init / commit（先确认没敏感文件）
  ├─→ GitHub ──→ Actions CI 绿 ──→ Release v1.0.0
  │        │
  │        ├─→ Pages 托管 market/index.json ──→ DSH 插件市场「发现」可搜到
  │        │
  │        └─→ 源码 zip / release/xianyu-monitor.zip
  │                     │
  │                     └─→ WorkBuddy 开放平台「技能」上传 → 审核 → 市场可见
  │
  └─→ 用户：clone → .env → python -m src.app → 装插件 → 对话里查候选
```

---

## 7. 出问题先看哪里

| 问题 | 先看 |
|---|---|
| CI 红了 | Actions 日志里是 `hygiene` 还是 `backend`；`hygiene` 多半是敏感文件或索引格式 |
| 市场里能看到但装不上 | 索引 `commit` 是否在远端存在、`engines.dsh` 是否匹配当前 DSH |
| 插件加载了但工具不出现 | `dsh --profile demo --dump-config` 是否出现 `# == dsh-plugin-xianyu-monitor` |
| 工具调用全失败 | 本机服务没起，或 `baseUrl` 配错 |
| WorkBuddy 技能装上没反应 | 脚本路径是否相对技能目录；`SKILL.md` 里的命令前缀 |
