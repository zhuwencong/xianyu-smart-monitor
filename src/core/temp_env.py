"""临时目录兜底。

Windows 上如果进程继承了不可写的 TEMP/TMP（例如从受限会话、沙箱或已失效的
用户环境里启动），Playwright 启动浏览器时会直接报：

    BrowserType.launch: EPERM: operation not permitted, mkdtemp 'C:\\...\\Temp\\playwright-artifacts-XXXXXX'

这类失败跟账号登录态毫无关系，但会让整轮抓取当场退出，而且旧版账号页会把它
误报成「最近运行正常」。启动时先探一次临时目录，不可写就换到项目内的 `.tmp`。

探测本身必须**有超时**：被组策略 / 杀软 / 沙箱拦截的目录不一定返回 EPERM，
也可能让 ``os.open`` 直接挂住（实测某些受限环境下写入 %TEMP% 会无限阻塞）。
如果探测同步执行，这个兜底反而会把服务启动和测试收集一起卡死。
"""
from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

_PROBE_PREFIX = ".temp-probe-"

# 单次探测的等待上限。超过就当作不可用，宁可退回项目内 `.tmp`，也不阻塞启动。
DEFAULT_PROBE_TIMEOUT_SECONDS = 2.0


def _probe_once(path: str) -> bool:
    """真正落地一次建/删文件；可能长时间阻塞，必须由 ``_is_writable`` 包超时。"""
    try:
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(prefix=_PROBE_PREFIX, dir=str(target))
        os.close(handle)
        os.remove(name)
        return True
    except Exception:
        return False


def _is_writable(path: str | None, *, timeout: float | None = None) -> bool:
    """带超时的可写性探测。

    返回 True 当且仅当探测在 ``timeout`` 内完成且成功。探测线程是 daemon：
    如果底层 I/O 卡死，它会被留在后台，但不影响调用方继续兜底。
    """
    if not path:
        return False

    budget = DEFAULT_PROBE_TIMEOUT_SECONDS if timeout is None else timeout
    outcome = {"ok": False}

    def _run() -> None:
        outcome["ok"] = _probe_once(path)

    worker = threading.Thread(target=_run, name="temp-dir-probe", daemon=True)
    worker.start()
    worker.join(budget)
    # 没跑完就返回 False —— 即使它稍后成功，也不能让调用方多等。
    return bool(outcome["ok"]) and not worker.is_alive()


def ensure_writable_temp_dir(
    project_dir: str | None = None,
    *,
    timeout: float | None = None,
) -> str:
    """返回一个确认可写的临时目录；必要时把 TEMP/TMP 切到项目内 `.tmp`。"""
    current = os.environ.get("TEMP") or os.environ.get("TMP") or tempfile.gettempdir()
    if _is_writable(current, timeout=timeout):
        return current

    fallback = Path(project_dir or os.getcwd()) / ".tmp"
    fallback.mkdir(parents=True, exist_ok=True)
    resolved = str(fallback)
    os.environ["TEMP"] = resolved
    os.environ["TMP"] = resolved
    tempfile.tempdir = resolved
    print(f"[环境] 临时目录不可写（{current}），已切换到 {resolved}")
    return resolved
