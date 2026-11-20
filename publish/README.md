# 上架材料总览（DSH 插件市场 + WorkBuddy 技能）

这个目录只放**提交格式**相关的东西，不放构建产物（zip 在 `release/`，已被 gitignore）。
两个渠道的权威口径都来自官方文档，正文里给了出处，别凭记忆改字段。

## 一页对照

| 目标 | 格式本体 | 本目录里的文件 | 产物 / 动作 |
|---|---|---|---|
| **DSH 官方精选目录**（内置市场、发现页） | 一个 YAML 条目：`data/plugins/<owner>__<repo>[--path].yml` | `awesome-dsh-plugin/data/plugins/zhuwencong__xianyu-smart-monitor--plugins-dsh.yml` | 向 `awesome-dsh-plugin/awesome-dsh-plugin` 提 PR |
| DSH 自建索引源（备用渠道） | `format: 1` 的 `index.json` | 仓库根 `market/index.json`（脚本生成） | 静态托管后让用户「添加索引源」 |
| **WorkBuddy 技能市场** | 技能包 zip：根目录下是 `xianyu-monitor/SKILL.md` + `references/` + `scripts/` | `workbuddy/UPLOAD.md`（字段对照） | 上传 `release/xianyu-monitor.zip` 到开放平台 |

两条 DSH 渠道是**互补**的：精选目录面向「搜得到」，自建索引面向「不依赖审核的兜底」。

## 阅读顺序

1. `awesome-dsh-plugin/PR.md` —— 官方目录的条目规则、逐条 CI 对照、PR 命令、常见打回原因
2. `workbuddy/UPLOAD.md` —— 技能包结构、frontmatter 必填字段、开放平台提交流程、解析失败排查
3. 仓库根 `PUBLISHING.md` —— 开源、Release、Pages、合规这些上游动作

## 一条命令自检

```bash
node scripts/package-workbuddy-skill.mjs --out release/xianyu-monitor.zip
node scripts/check-publish-artifacts.mjs
```

`check-publish-artifacts.mjs` 会核对：

- 精选目录条目的**文件名 ↔ url ↔ name** 三者是否自洽，`category` 是否在枚举里，
  `description.en` 是否以句点结尾、含 `: ` 时有没有加引号；
- `plugins/dsh/package.json` 是否声明 `dsh.bundle`（只声明 `dsh.client` 是典型被拒原因）、
  patch 文件是否存在、`@deepseek-ai/*` 是否误放进 `dependencies`；
- WorkBuddy 技能 frontmatter 的 8 个必填字段、`name` 是否符合连字符规范、版本是否与插件一致；
- 打出来的 zip：根目录是否只有一层技能目录、是否混进 `__pycache__` / `.pyc`、每个条目的 CRC 是否对得上。

CI 的 `hygiene` job 已经接上这一步；`node scripts/check-plugin-versions.mjs` 继续负责三处版本号同步。

## 发布节奏（建议）

```
改代码 → 三处版本号同步 → 打包 + 自检 → 提 PR（一个 YAML 文件）
                                   ↘ 开放平台上传新 zip（WorkBuddy）
```
