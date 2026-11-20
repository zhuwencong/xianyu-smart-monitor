# 上架 WorkBuddy 技能市场（xianyu-monitor）

> 面向维护者。目标：在 [WorkBuddy 开放平台](https://open.workbuddy.cn/) 上传技能包，过审后出现在
> WorkBuddy 的【专家 · 技能 · 连接器 → 技能】市场里。

## 1. 官方格式（以开放平台文档为准）

来源：[open.workbuddy.cn/docs/skill](https://open.workbuddy.cn/docs/skill)。技能包在 zip 根目录下**只放技能目录**：

```
xianyu-monitor/          ← 目录名 = frontmatter 的 name
├── SKILL.md             ← 必须
├── references/          ← 可选：被 SKILL.md 用 @references/xxx.md 引用
│   ├── api.md
│   └── install.md
├── scripts/             ← 可选：模型通过 Bash 执行
│   └── xy.py
└── templates/           ← 可选：模板类文件（本技能不需要）
```

`SKILL.md` = YAML frontmatter + Markdown 正文。**必填字段**（少一个就解析失败）：

| 字段 | 必填 | 含义 | 本技能当前值 |
|---|---|---|---|
| `name` | ✅ | 技能标识，小写连字符，**必须等于目录名** | `xianyu-monitor` |
| `display_name` | ✅ | 市场里的中文名 | 闲鱼智能监控 |
| `display_name_en` | ✅ | 市场里的英文名 | Xianyu Smart Monitor |
| `description` | ✅ | 一句话说明用途 + 触发词（决定被召回的概率） | 见 `SKILL.md`（含「闲鱼 / 二手 / 捡漏 / 候选商品 / 登录失效」） |
| `description_zh` | ✅ | 详情页短介绍 | 一句话，中文 |
| `description_en` | ✅ | 详情页短介绍 | 一句话，英文 |
| `version` | ✅ | 版本号，与 DSH 插件同步 | `0.1.2`（`package.json` 同值，CI 会校验） |
| `author` | ✅ | **合作方名称**（审核会看） | 闲鱼智能监控 Contributors |
| `examples_zh` / `examples_en` | 可选 | 详情页「试试这样用」 | 各 4 条 |
| `allowed-tools` | 可选 | 工具白名单，逗号分隔 | `Bash, Read` |

> 字段名是**带下划线的**（`display_name`、`description_zh`、`examples_en`），不是 DSH 技能那套。
> 额外字段不要自己发明——校验器只认这几个，多余的关键字在详情页不会展示。

## 2. 打包（不要手动拖 zip）

```bash
# 在本仓库根目录
node scripts/package-workbuddy-skill.mjs --out release/xianyu-monitor.zip
node scripts/check-publish-artifacts.mjs
```

脚本保证三件事，手动压缩最容易坏的就是这三件：

1. zip 根目录下就是 `xianyu-monitor/`（**不能多套一层**，`xianyu-monitor/xianyu-monitor/SKILL.md` 会被判解析失败）；
2. 排除 `__pycache__/`、`*.pyc`、`.DS_Store`、`node_modules/`；
3. 文件名统一 `/` 分隔（Windows 打包常见 `\`，平台侧解析会挂）。

产物：`release/xianyu-monitor.zip`（`release/` 已在 `.gitignore` 里，作为 Release 附件而不是提交进仓库）。

## 3. 提交步骤

1. 打开 https://open.workbuddy.cn/ → **立即入驻**，提交主体信息（个人或企业），等审核通过。
2. 进入 **开发 → 技能** → **添加技能**。
   - 方式 A：**创建技能** —— 按提示把需求补齐，让 WorkBuddy 自己生成骨架；
   - 方式 B：**上传 zip** —— 直接传 `release/xianyu-monitor.zip`（本技能走这条）。
3. 填展示信息：
   - 图标：512×512 PNG（可先用 `web-ui/public/favicon.png` 放大导出，或重新出一版）；
   - 分类 / 标签：效率、自动化、二手交易；
   - 截图：建议 3 张（候选列表、任务状态、对话里的一次问答）；
   - 详情页写清 **数据用途**（见下一节）。
4. 提交审核 → 过审后市场上线，用户在【技能】里点「+」安装。

## 4. 审核大概率会问的三件事（提前写进详情页）

| 问题 | 标准答法 |
|---|---|
| 数据往哪走？ | 只访问本机 `http://127.0.0.1:8000`（用户自己跑的监控服务），**不上传任何数据**，不读取 `state/` 登录态与 `.env` |
| 依赖什么？ | `scripts/xy.py` 只用 Python 标准库，不需要虚拟环境、不装第三方包 |
| 服务没起怎么办？ | 先跑 `status`，连不上就明确提示「请先启动监控服务」，不静默返回空结果 |

另外两条也要在页面上说清，能少一轮来回：

- `start` 会真实访问闲鱼、消耗账号风控额度，所以 SKILL.md 里限定「用户明确要求才跑」；
- 技能没有「自动砍价 / 自动拍下」这类能力，别在文案里暗示。

## 5. 上传后「解析失败」排查表

| 现象 | 原因 | 修法 |
|---|---|---|
| 解析失败 | zip 多套一层目录 | 用本仓库脚本重打，别手压 |
| 解析失败 | 缺 `display_name_en` / `author` / `version` | 对照第 1 节补齐 |
| 解析失败 | frontmatter 里 `description` 含 `<` `>` | 改成文字描述（WorkBuddy 的校验器会直接拒） |
| 装上但跑不动 | 脚本用到了项目 `.venv` 的第三方包 | 保持 `xy.py` 只用标准库 |
| 装上没反应 | `SKILL.md` 里的脚本路径写成了绝对路径 | 一律相对技能目录：`python scripts/xy.py status` |
| 一执行就报连不上 | 用户没启动监控服务 | 保留 SKILL.md 里「先 status、再提示启动」那段 |
| 中文乱码 | 控制台 GBK | `xy.py` 已强制 UTF-8 输出，别改回去 |

## 6. 发新版本

三处版本号必须一致（`node scripts/check-plugin-versions.mjs` 会卡）：

1. `plugins/dsh/package.json` → `version`
2. `plugins/workbuddy/xianyu-monitor/SKILL.md` frontmatter → `version`
3. `market/index.json` → 对应插件的 `versions[0].version`

改完重新打包、重新上传 zip，并在平台上填新的版本号——**平台不会从包名自动升级版本**。
