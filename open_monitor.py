"""桌面快捷方式入口：确保服务在跑，然后打开 Web UI。

由 .venv\\Scripts\\pythonw.exe 运行（无控制台窗口），所以所有异常都必须自己
记日志，不能让崩溃变成"双击没反应"。

行为：
1. 8000 端口已在监听 → 直接开浏览器；
2. 否则以 DETACHED_PROCESS 拉起 `-m src.app`，最多等 90 秒，服务起来再开浏览器。

日志：logs/shortcut.log
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG_FILE = BASE / "logs" / "shortcut.log"

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}/"
WAIT_SECONDS = 90

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

# 本机历史上有残留的死代理，会把子进程的抓图和模型调用全部带崩
PROXY_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    "PROXY_URL", "proxy_url",
)


def log(message: str) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp}  {message}\n")
    except Exception:
        pass


def port_open(timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=timeout):
            return True
    except OSError:
        return False


def python_exe() -> Path:
    for name in ("pythonw.exe", "python.exe"):
        candidate = BASE / ".venv" / "Scripts" / name
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def start_server() -> None:
    env = {k: v for k, v in os.environ.items() if k not in PROXY_KEYS}
    exe = python_exe()
    log(f"starting server with {exe}")

    out = (BASE / "logs" / "server.out").open("ab")
    try:
        proc = subprocess.Popen(
            [str(exe), "-m", "src.app"],
            cwd=str(BASE),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=out,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
        log(f"server pid = {proc.pid}")
    finally:
        out.close()


def main() -> int:
    os.chdir(BASE)
    log("shortcut invoked")

    if not port_open():
        if not (BASE / ".venv" / "Scripts").exists():
            log("ERROR .venv missing")
            return 1
        start_server()

        for second in range(1, WAIT_SECONDS + 1):
            time.sleep(1)
            if port_open():
                log(f"server ready after {second}s")
                break
        else:
            log(f"ERROR server not ready after {WAIT_SECONDS}s")
            return 2
    else:
        log("server already running")

    webbrowser.open(URL)
    log(f"browser opened -> {URL}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log("FATAL\n" + traceback.format_exc())
        sys.exit(1)
