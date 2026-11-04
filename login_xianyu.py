"""
闲鱼登录态一键采集脚本
--------------------------------------------------
弹出浏览器窗口 -> 用闲鱼 App 扫码登录 -> 自动把登录态写入 state/<账号名>.json
无需安装 Chrome 扩展。

用法：
    .venv\\Scripts\\python.exe login_xianyu.py [账号名]
默认账号名 acc_1

安全机制：
    1. 单实例锁：已经有一个登录窗口在跑时，再次启动会直接退出，
       不会再开第二个浏览器窗口。
    2. 身份核对：保存后打印真实账号（unb + 昵称），并和 state 下其它
       账号文件比对；如果是同一个号，文件会被改名为 *.json.dup，
       不会污染账号池（两个相同 unb 的账号会互相顶号）。
"""
import asyncio
import json
import socket
import sys
import time
from pathlib import Path
from urllib.parse import unquote

from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parent
STATE_DIR = PROJECT_ROOT / "state"
LOGIN_URL = "https://www.goofish.com"
# 整页版登录界面：右侧是一块大二维码，比首页弹窗更稳定、更醒目
LOGIN_PAGE = "https://www.goofish.com/login"
WAIT_SECONDS = 600  # 最多等 10 分钟
POLL_INTERVAL = 2.0

# 闲鱼登录成功后会下发的关键 cookie（unb = 用户 ID）
REQUIRED_COOKIE = "unb"

# 单实例锁占用的本地端口（进程退出后自动释放，不会残留）
LOCK_PORT = 45991
_lock_socket = None


def log(msg: str) -> None:
    print(msg, flush=True)


def force_foreground(keyword: str = "闲鱼", keep_topmost: int = 60) -> None:
    """把标题含 keyword 的窗口强制置顶到最前（Windows）。

    Playwright 的 bring_to_front 只在页面层面生效，压不住用户已有的一堆窗口，
    这里直接调 Win32：SW_RESTORE + HWND_TOPMOST + SetForegroundWindow。
    keep_topmost 秒后自动取消置顶，免得一直挡着别的窗口。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return

    user32 = ctypes.windll.user32
    found = []
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if not user32.IsWindowVisible(hwnd):
            return True
        # 只要闲鱼相关窗口，但排除 Edge 上的监控后台（标题里也带“闲鱼”）
        if keyword in title and "Microsoft" not in title and "Edge" not in title:
            found.append((hwnd, title))
        return True

    try:
        user32.EnumWindows(EnumProc(_cb), 0)
    except Exception:
        return

    def _release_later(hwnd, delay):
        def _run():
            time.sleep(delay)
            try:
                # HWND_NOTOPMOST = -2，恢复正常层级
                user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002)
            except Exception:
                pass

        import threading

        threading.Thread(target=_run, daemon=True).start()

    for hwnd, title in found:
        try:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)  # TOPMOST
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            log(f"[窗口] 已置顶: {title}")
            if keep_topmost:
                _release_later(hwnd, keep_topmost)
        except Exception:
            continue

    # 响一声，提醒窗口出来了
    try:
        import winsound

        winsound.MessageBeep(0x40)
    except Exception:
        pass


def acquire_single_instance() -> bool:
    """用本地端口 bind 做单实例锁。已有一个在跑则返回 False。"""
    global _lock_socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # 注意：不能设 SO_REUSEADDR，否则多个实例都能绑定成功
        sock.bind(("127.0.0.1", LOCK_PORT))
        sock.listen(1)
    except OSError:
        try:
            sock.close()
        except Exception:
            pass
        return False
    _lock_socket = sock
    return True


def identify(state_file: Path) -> tuple:
    """读取账号文件，返回 (unb, 昵称)。"""
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return ("", "")
    cookies = {c.get("name"): c.get("value", "") for c in data.get("cookies", [])}
    return (cookies.get("unb", ""), unquote(cookies.get("tracknick", "")))


def check_duplicate(out_path: Path) -> None:
    """保存后核对账号身份，并和已有账号比对是否重复。"""
    unb, nick = identify(out_path)
    log("")
    log(f"[账号] unb = {unb or '(未取到)'}    昵称 = {nick or '(未取到)'}")

    dup_names = []
    for other in sorted(STATE_DIR.glob("*.json")):
        if other.resolve() == out_path.resolve():
            continue
        o_unb, o_nick = identify(other)
        if o_unb and o_unb == unb:
            dup_names.append(f"{other.name}({o_nick or o_unb})")

    if not dup_names:
        log(f"[OK] 新账号，和现有账号不重复。已保存 -> {out_path.name}")
        return

    dup_path = out_path.with_name(out_path.name + ".dup")
    try:
        out_path.replace(dup_path)
    except Exception:
        dup_path = out_path

    log("!" * 60)
    log(f"[重复] 抓到的账号和 {', '.join(dup_names)} 是同一个号！")
    log("       扫码时手机闲鱼 App 里登录的就是这个账号。")
    log(f"       该文件已改名，不计入账号池：{dup_path.name}")
    log("       请在那个 App 里切换到另一个账号，再重新运行本脚本。")
    log("!" * 60)


async def collect(account_name: str) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = STATE_DIR / f"{account_name}.json"

    log("正在启动浏览器，请稍候……")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--window-position=60,30",
                "--window-size=1400,940",
            ],
        )
        context = await browser.new_context(
            viewport=None,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            color_scheme="light",
        )
        page = await context.new_page()
        # 直接打开整页版登录界面（有界面模式下不会被判「非法访问」）
        try:
            await page.goto(LOGIN_PAGE, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:  # 网络慢不影响后续手动操作
            log(f"[warn] 打开登录页较慢: {exc}")
        await page.wait_for_timeout(3000)

        # 万一被判非法访问，回退到首页（首页会自动弹登录框）
        blocked = False
        try:
            body_text = await page.inner_text("body")
            blocked = "非法访问" in body_text
        except Exception:
            pass
        if blocked:
            log("[warn] 登录页被拦，回退到首页弹窗方式……")
            try:
                await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(3000)
                try:
                    await page.locator("text=登录").first.click(timeout=5000, force=True)
                except Exception:
                    pass
                await page.wait_for_timeout(2500)
            except Exception as exc:
                log(f"[warn] 回退首页也失败: {exc}")

        # 把窗口顶到最前面，避免被其他窗口盖住找不到
        try:
            await page.bring_to_front()
        except Exception:
            pass
        # 强制置顶（Win32 层面），并在 60 秒后自动恢复正常层级
        await page.wait_for_timeout(1200)
        force_foreground("闲鱼", keep_topmost=60)

        qr_ready = not blocked

        log("")
        log("=" * 60)
        log(f" 目标账号名：{account_name}")
        if qr_ready:
            log("")
            log("  >>> 二维码已经出现在浏览器窗口里 <<<")
            log("")
            log("      位置：窗口中间偏右，大字「手机扫码安全登录」")
            log("            下面那个黑白方格就是二维码")
            log("      （左边是短信登录，不用管它）")
            log("")
            log("  怎么扫：打开【手机闲鱼 App】（不是微信！）")
            log("         点 App 首页左上角的「扫一扫」→ 对准电脑屏幕")
            log("")
            log("  [!] 扫码前先确认 App 里登录的是你要抓的那个号，")
            log("      否则抓到的还是同一个账号，脚本会拦下来。")
        else:
            log("")
            log("  自动打开登录界面没成功。请手动操作：")
            log("   1. 在浏览器窗口右上角找到「登录」并点击")
            log("   2. 弹窗右侧出现「手机扫码安全登录」二维码")
            log("   3. 用手机闲鱼 App 的「扫一扫」扫它")
        log("")
        log(f" 登录成功会自动保存，最多等待 {WAIT_SECONDS // 60} 分钟。")
        log(" 想取消：直接关掉浏览器窗口即可。")
        log("=" * 60)
        log("")

        started = time.time()
        saved = False
        while time.time() - started < WAIT_SECONDS:
            if page.is_closed():
                log("[x] 浏览器窗口已关闭，未保存登录态。")
                return 2
            try:
                cookies = await context.cookies()
            except Exception:
                break
            names = {c.get("name") for c in cookies}
            if REQUIRED_COOKIE in names:
                await page.wait_for_timeout(2500)  # 等其余 cookie 落盘
                await context.storage_state(path=str(out_path))
                count = len(await context.cookies())
                log(f"[OK] 登录成功，已保存 {count} 条 cookie -> {out_path.name}")
                saved = True
                break
            await page.wait_for_timeout(int(POLL_INTERVAL * 1000))

        if not saved:
            log("[x] 超时未检测到登录状态，请重新运行本脚本。")
            await browser.close()
            return 1

        await page.wait_for_timeout(1200)
        await browser.close()

    check_duplicate(out_path)
    return 0


def main() -> int:
    if not acquire_single_instance():
        log("")
        log("=" * 58)
        log(" 已经有一个登录窗口在运行了，本窗口直接退出。")
        log(" 请回到刚才那个浏览器窗口扫码，不要重复启动。")
        log(" （如果找不到那个窗口，先在任务管理器里结束残留的")
        log("   chrome.exe / python.exe 后再试）")
        log("=" * 58)
        log("")
        return 3

    account_name = sys.argv[1] if len(sys.argv) > 1 else "acc_1"
    if not account_name.replace("_", "").replace("-", "").isalnum():
        log("账号名只能包含字母、数字、下划线或短横线。")
        return 1
    log(f"目标账号名：{account_name}")
    return asyncio.run(collect(account_name))


if __name__ == "__main__":
    raise SystemExit(main())
