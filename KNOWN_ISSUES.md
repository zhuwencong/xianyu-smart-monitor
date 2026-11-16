# 已知问题 / Known Issues

这里记录**已经被真实踩到、且容易误判**的问题，以及当前的处置方式。
每条都标注状态，方便你在升级后回头确认是否还需要按规避方案操作。

> 提问前请先扫一眼这里。Issue 模板里也要求你确认过本文件。
>
> 编号规则：`KI-xxx` 不复用、不删除。已修复的条目保留，只改状态。

## 速查表

| 编号 | 现象 | 状态 | 对应版本 |
|---|---|---|---|
| [KI-001](#ki-001) | 抓取正常但 AI 分析全部失败 / 通知收不到 | 已修复（含兜底） | 1.0.0 |
| [KI-002](#ki-002) | 服务或 `pytest` 启动时卡死，日志停在临时目录探测 | 已缓解（2s 超时 + `.tmp` 兜底） | 1.0.0 |
| [KI-003](#ki-003) | clone 后前端构建报 `Failed to resolve import .../data/goofishRegions.json` | 已修复 | 1.0.0 |
| [KI-004](#ki-004) | 点「添加账号」后扫码窗口没出来 / 被关掉 | 有规避方案 | 1.0.0 |
| [KI-005](#ki-005) | 抓取时遇到滑动验证码，任务直接失败 | 需手动处理 | — |
| [KI-006](#ki-006) | Windows 上 `pytest` 报 `collected 0 items` 或 `underlying buffer has been detached` | 有规避方案 | — |
| [KI-007](#ki-007) | CI 在 UTC 机器上时间断言必红 | 已修复 | 1.0.0 |
| [KI-008](#ki-008) | 登录态与默认口令是明文，多用户共用有风险 | 设计如此（见 SECURITY） | — |

---

<a id="ki-001"></a>
## KI-001 抓取正常，但 AI 分析全部失败 / 通知收不到

**现象**
任务能抓到商品、图片也下载了，但每条都是「AI 分析失败」，日志里只有
`APIConnectionError: Connection error.`；或者任务跑成功了但 PushPlus / Bark 一直没消息。

**原因**
服务和爬虫进程从父 shell / 桌面会话 / 已退出的启动器继承了 `HTTP_PROXY`、
`HTTPS_PROXY`、`ALL_PROXY`，指向一个已经停掉的本地代理（如 `127.0.0.1:7897`）。
- `httpx`（openai SDK）和 `requests` 都读这些变量 → AI 与推送直接连不上；
- Playwright / Chromium **不读**这些变量（走系统代理）→ 抓取看起来完全正常。

这种组合非常容易误判成「模型服务挂了」或「Key 失效」。

**处置**
- 1.0.0 起，`src/app.py`、`spider_v2.py`、`launch_server.py` 启动时会调用
  `src/core/proxy_env.py::strip_inherited_proxy_env()` 清掉继承来的代理变量；
  若 `.env` 里显式配置了 `PROXY_URL`，则视为有意为之，不做清理。
- 通知发送改为**优先直连**（`trust_env=False`），失败再回退系统代理，
  因为 `requests` 还会从注册表读系统代理，清环境变量治不了这条。
- 你自己排查时：看启动日志有没有 `[启动] 已清理父进程继承的代理环境变量: ...`。

---

<a id="ki-002"></a>
## KI-002 启动或 `pytest` 卡死，停在临时目录探测

**现象**
`python -m src.app` 或 `pytest` 长时间无输出、不报错、CPU 也不高。

**原因**
某些受限环境（组策略、杀软、沙箱）里写 `%TEMP%` 不是返回 `EPERM`，
而是让 `os.open` **无限阻塞**。1.0.0 之前的可写性探测是同步的，
正好卡在这一步。

**处置**
- 探测改为 **2 秒超时**的守护线程，超时即判定不可用并回退到项目内 `.tmp`；
- 探测从 `src/app.py` 的 import 阶段挪到 `lifespan()`，import 不再有文件系统副作用；
- 副作用：`tempfile.gettempdir()` 在受影响环境里会回落到仓库根目录，
  pytest 的 `tmp_path` 会生成 `pytest-of-<user>/`，已被 `.gitignore` 忽略。

**还能做什么**
如果你确认 `%TEMP%` 可用但首次启动仍慢 2 秒以上，说明探测在被拦和可用之间抖动，
可以把 `DEFAULT_PROBE_TIMEOUT_SECONDS` 调小（`src/core/temp_env.py`）。

---

<a id="ki-003"></a>
## KI-003 clone 后前端构建报 `Failed to resolve import .../data/goofishRegions.json`

**现象**
`cd web-ui && npm run build` 报找不到 `src/data/goofishRegions.json`，但文件明明存在。

**原因**
`.gitignore` 里目录规则写成了 `data/` 而不是 `/data/`。
不带前导斜杠的规则会匹配**任意层级**的同名目录，于是 `web-ui/src/data/`
整目录被忽略，clone 下来就缺文件。

**处置**
1.0.0 起所有运行时目录规则都带前导斜杠：`/data/`、`/images/`、`/logs/`、
`/jsonl/`、`/price_history/`、`/state/`。

**自查命令**

```bash
git check-ignore -v web-ui/src/data/goofishRegions.json   # 应该无输出
```

---

<a id="ki-004"></a>
## KI-004 点「添加账号」后扫码窗口没出来，或被误关

**现象**
点了「+ 添加账号」，等了一会儿账号没出现在列表里；或者扫码窗口被手动关掉后无法再拉起。

**原因**
- 闲鱼登录窗口是**独立浏览器进程**，已被关掉时不会自动复活；
- 如果上一次的扫码窗口还残留进程，可能撞上单实例锁；
- 扫码总等待时间超过 5 分钟会主动超时。

**处置**
弹窗里保留两个出口：
1. **重新打开窗口** —— 重新拉起扫码；
2. **手动粘贴 JSON** —— 用 Chrome 扩展导出登录态后粘贴（老流程仍然可用）。

**注意**
扫码成功后登录态写在 `state/acc_N.json`（明文，见 [SECURITY.md](SECURITY.md)），
确认账号出现在列表里再关弹窗。

---

<a id="ki-005"></a>
## KI-005 抓取遇到滑动验证码

**现象**
日志出现 `FAIL_SYS_USER_VALIDATE` 或页面被重定向到验证页，本轮抓取失败。

**原因**
请求频率、账号环境或平台风控触发。**本项目不做也不能做验证码绕过。**

**处置**
- 降低频率：调大 `SCRAPE_SPEED_FACTOR`（越大越慢）、`SCRAPE_COOLDOWN_EVERY`，
  缩短 `SCRAPE_MAX_RUNTIME_MINUTES`；
- 需要人工过验证码时，把 `RUN_HEADLESS=false`，让浏览器有界面，手动滑一次；
- 冷却期内不要反复重试，`RISK_CONTROL_PAUSE_SECONDS` 默认 2 小时，硬闯只会加重风控。

---

<a id="ki-006"></a>
## KI-006 Windows 上 `pytest` 报 `collected 0 items` 或 `underlying buffer has been detached`

**现象**
测试一条都没收集到，或者跑完在退出阶段抛 `ValueError: underlying buffer has been detached`。

**原因**
pytest 的输出捕获与部分 Windows 终端 / 管道组合不兼容，与被测代码无关。

**处置**

```bash
pytest -q -s                      # 关闭捕获
# 或
pytest -q -p no:cacheprovider -s
```

---

<a id="ki-007"></a>
## KI-007 CI 在 UTC 机器上时间断言必红

**现象**
本地全绿，GitHub Actions 上时间相关的断言失败，差 8 小时。

**原因**
测试里用了「本地时间」构造期望值，而 CI runner 默认 `TZ=UTC`。

**处置**
1.0.0 起测试统一使用 `ZoneInfo("Asia/Shanghai")` 构造固定时间，不依赖机器时区。

---

<a id="ki-008"></a>
## KI-008 登录态与默认口令是明文

**现象**
`state/acc_*.json` 是明文登录态；`WEB_PASSWORD` 默认 `admin123`。

**原因**
单机自用工具的设计取舍：登录态必须能被 Playwright 直接加载，加密反而增加故障面。

**处置**
- 一定改掉默认口令；绑定 `0.0.0.0` 时程序会拒绝以默认密码启动；
- 不要把 `state/` 放进任何同步盘；
- 不要把 `state/`、`.env` 分享或截图；
- 细则见 [SECURITY.md](SECURITY.md)。

---

## 提交新的已知问题

如果你踩到了不在上面、且**容易被误判**的坑，欢迎：
1. 先开 Issue 描述现象（用 Bug 模板，日志记得脱敏）；
2. 维护者确认后，在本文件追加 `KI-xxx` 条目（编号顺延，不复用）。

**不建议**把「我这边环境特有的偶发问题」写进来——那更适合留在 Issue 里。
