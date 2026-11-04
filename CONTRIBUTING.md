# 贡献指南 / Contributing

感谢你愿意为这个项目出力。这个项目本质上是一个「会持续改网页选择器的爬虫 + 一个需要长期维护的 Web 工作台」，所以最有价值的贡献是**让它在一段时间不维护的情况下仍然不崩**。

## 在动手之前

- 先搜 Issue 和 PR，避免重复劳动；有疑问先开 **Discussion** 或 **Feature Request**，不要直接写大改。
- 涉及抓取频率、代理、验证码、账号池的改动**不会被合并**。这是硬边界，见 [SECURITY.md](SECURITY.md)。
- 涉及 UI 的改动请附截图（改前 / 改后）。

## 开发环境

```bash
git clone https://github.com/<GITHUB_USER>/xianyu-smart-monitor.git
cd xianyu-smart-monitor
cp .env.example .env          # 至少填 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL_NAME
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
cd web-ui && npm install && npm run build && cd ..
python -m src.app             # http://127.0.0.1:8000
```

## 提交前自检

```bash
# 后端
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest
# 前端
cd web-ui && npm run build
# 敏感信息（必须为空）
git grep -nE 'sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}'
git status --short --ignored | grep -E '\.env$|state/|data/' && echo "危险：有敏感文件被加入暂存区"
```

CI 会跑同样的三件事。**本地过不了就不要提 PR**。

## 代码约定

- 分层：`API (src/api/routes)` → `services` → `domain` → `infrastructure`，不要跨层调用。
- Python 3.10+ 语法；测试文件 `tests/**/test_*.py`，函数 `test_*`；默认同步测试。
- 前端 Vue 3 + Vite + shadcn-vue + Tailwind，组件放 `web-ui/src/components/`，页面放 `web-ui/src/views/`。
- 新增面向用户的配置项，必须同时更新 `.env.example` 与 README 配置表。
- 新增接口，请在 `src/api/routes/` 内保持 REST 风格，并在 PR 描述里列出入参/返回。
- 抓取相关变更必须说明**对请求量的影响**（每轮请求数、翻页次数、并发度）。

## Commit 规范

采用 Conventional Commits：

```
feat(workbench): 候选商品支持按卖家信用排序
fix(scraper): 修复翻页到最后一页时的空转重试
docs(readme): 补充 DSH 插件安装方式
chore(deps): 升级 playwright 到 1.5x
```

一次 commit 只做一件事；格式化改动单独一次 commit，避免掩盖真实 diff。

## Pull Request

- 标题同样用 Conventional Commits。
- 描述里写清：变更范围、影响模块、验证方式、是否涉及配置/数据迁移。
- 关联 Issue（`Closes #123`）。
- 新逻辑请补针对性用例；修 bug 请先补一个能复现的失败用例。
- Draft PR 完全 OK，早开早对齐。

## 文档与翻译

- 中文 README 是主文档，`README_EN.md` 需要同步更新关键章节。
- 翻译请保持术语一致：任务 / 结果 / 候选商品 / 账号 / 运行记录。
- 不要为了「看起来更专业」而把中文改写成官腔，保持可读。

## 许可

提交 PR 即表示你同意以 [MIT License](LICENSE) 授权你的贡献，并同意在 [NOTICE](NOTICE) 中记录你的署名。
