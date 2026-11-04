# DSH 插件市场索引

这个目录就是可以直接托管的「插件市场」：一个 `index.json` 加一个 `icons/` 目录。

格式说明见 [DSH 文档 · 插件市场](https://deepseek-harness.github.io/deepseek-harness/guide/plugin-market.md)。

## 生成

```bash
node scripts/build-market-index.mjs
node scripts/validate-market-index.mjs market/index.json
```

生成器会从 `plugins/dsh/package.json` 读版本与 `dsh.bundle` 声明，从 git 读该目录最近一次提交的
SHA 与时间戳，从 `git remote get-url origin` 读仓库地址。

## 托管（三选一）

### 1. GitHub Pages（推荐，免费且 https）

仓库 Settings → Pages → Source 选 `Deploy from a branch`，分支 `main`，目录 `/docs` 或 `/root`。
如果选根目录，索引 URL 就是：

```
https://<GITHUB_USER>.github.io/xianyu-smart-monitor/market/index.json
```

`market/icons/xianyu-monitor.svg` 会被相对路径自动解析，无需额外配置。

### 2. 任意对象存储

把 `market/` 整个目录上传到 OSS / COS / R2 / S3，确保：

- 索引返回 2xx 且**不经过重定向**
- `Content-Type: application/json`
- 同一目录下的 `icons/` 可公开读

### 3. 自建静态服务

```bash
npx serve market      # 仅本地验证用
```

本地 `http://` 索引也能加，但只应加自己控制的源。

## 用户怎么加进来

DSH → 插件 → 实验性插件旁的「更多」→ 打开 **自定义插件市场** → 已安装旁边的 **发现** 标签页 →
**添加索引源** → 粘贴索引 URL。

## 发布新版本时

1. 改 `plugins/dsh/package.json` 的 `version`
2. 提交（索引要写 commit SHA，未提交的改动不会被正确引用）
3. 重跑生成器与校验器
4. 推送，等待 Pages 生效（通常 1 分钟内）

## 注意

- 索引里的 `source.type: git` 需要 **40 位 commit SHA**；生成器已自动处理。
- 图标最大 32 KiB；`icons/xianyu-monitor.svg` 目前约 2 KiB。
- 索引本身最大 128 MiB，单插件市场远用不到。
