# 插件与技能

这里的两个目录是**同一个本机服务的两种接入方式**，都不打包爬虫，都只跟 `http://127.0.0.1:8000` 说话。

| 目录 | 面向 | 形态 | 上架位置 |
|---|---|---|---|
| [`dsh/`](dsh/) | DeepSeek Harness | npm 组合包（`dsh.bundle`），注册 `xianyu_*` 工具 | DSH 插件市场（`market/index.json`） |
| [`workbuddy/xianyu-monitor/`](workbuddy/xianyu-monitor/) | WorkBuddy | 技能包（`SKILL.md` + `scripts/`） | WorkBuddy 开放平台 |

## 为什么不做成「一装就能爬」的插件

- 爬虫需要 Playwright + Chromium + 登录态，塞进插件只会让安装失败率变高。
- 登录态是用户自己的凭据，不该经过插件的目录。
- 服务已经在跑的时候，桥接层的价值最大；服务没跑时，报错信息比静默失败有用。

## 发布流程

### DSH

```bash
node scripts/build-market-index.mjs          # 生成 market/index.json
node scripts/validate-market-index.mjs market/index.json
```

然后把 `market/` 目录托管到任意静态站点（GitHub Pages 即可），索引 URL 为 `<站点>/index.json`。
用户侧：插件页 → 实验性插件 → 更多 → 自定义插件市场 → 添加索引源。

### WorkBuddy

```bash
node scripts/package-workbuddy-skill.mjs     # 输出 release/xianyu-monitor.zip
```

然后到 WorkBuddy 开放平台 → 技能 → 添加技能 → 上传 zip。

## 版本同步

三处版本号必须一致，`scripts/check-plugin-versions.mjs` 会检查：

- `plugins/dsh/package.json` 的 `version`
- `plugins/workbuddy/xianyu-monitor/SKILL.md` frontmatter 的 `version`
- `market/index.json` 里对应版本的 `version`
