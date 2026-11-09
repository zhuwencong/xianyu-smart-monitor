# 让监控服务在本机跑起来

技能只是「遥控器」，本体是闲鱼智能监控服务。装技能之前，先确认本体能启动。

## 最快的路径

1. 拿到项目（二选一）
   ```bash
   git clone https://github.com/zhuwencong/xianyu-smart-monitor.git
   cd xianyu-smart-monitor
   ```
   或直接下载 Release 里的压缩包解压。

2. 准备配置
   ```bash
   cp .env.example .env
   ```
   至少填三项：
   - `OPENAI_API_KEY`：模型 Key
   - `OPENAI_BASE_URL`：OpenAI 兼容地址
   - `OPENAI_MODEL_NAME`：**必须支持图片输入**的模型

3. 装依赖并启动（Windows 用户可直接双击 `启动闲鱼监控.bat`）
   ```bash
   pip install -r requirements.txt
   python -m playwright install chromium
   python -m src.app
   ```
   看到 `Uvicorn running on http://127.0.0.1:8000` 即成功。

4. 浏览器打开 `http://127.0.0.1:8000`，本机访问会直接进工作台。
   去「闲鱼账号管理」导入登录态（Chrome 扩展导出 JSON 后粘贴），再建任务。

5. 回到对话，跑一次
   ```bash
   python scripts/xy.py status
   ```
   能返回 JSON 就说明技能已接上。

## 常见卡点

| 卡点 | 原因 | 处理 |
|---|---|---|
| `Uvicorn running` 但浏览器打不开 | 端口被占用或改了 `SERVER_PORT` | 用 `--base-url http://127.0.0.1:<port>` |
| 启动报「缺少前端构建产物」 | 根目录 `dist/` 不存在 | `cd web-ui && npm install && npm run build`，再把 `web-ui/dist` 复制成根目录 `dist` |
| 任务跑起来立刻结束 | 登录态失效 | 工作台账号页重新扫码 |
| AI 分析全部失败 | 模型不支持图片 / Key 无效 | 看 `logs/task_<id>.log`，换多模态模型 |
| 启动提示拒绝使用默认密码 | 绑定了 `0.0.0.0` 但密码还是 `admin123` | 改 `.env` 里的 `WEB_PASSWORD` |
| 技能报 401 | 开了 `WEB_STRICT_AUTH=true` | 改为 `false`（仅本机），或在浏览器里操作 |

## Docker 方式

```bash
cp .env.example .env
docker compose up -d
docker compose logs -f app
```

注意：容器里服务的地址对外是宿主机的 `8000`，技能仍然用 `http://127.0.0.1:8000` 访问即可。
容器内 `RUN_HEADLESS` 必须为 `true`。

## 数据放在哪里

| 目录 / 文件 | 内容 | 是否可删 |
|---|---|---|
| `data/app.sqlite3` | 任务、候选商品、价格历史、运行记录 | 删了等于清空所有结果 |
| `state/acc_*.json` | 闲鱼登录态（**敏感**） | 删了要重新扫码 |
| `logs/` | 运行日志、熔断状态 | 可删 |
| `images/` | 商品图缓存 | 可删 |
| `.env` | 配置与 Key（**敏感**） | 不要外传 |
