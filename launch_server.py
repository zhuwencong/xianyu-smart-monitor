"""后台常驻启动器：由 pythonw.exe 调用，把 src.app 拉起到独立进程并重定向日志。

为什么要这么绕：
- 本项目在 Windows 上不能依赖 `cmd /c`（会被安全策略拦），VBS 里直接调 cmd 会静默失败；
- 沙箱内直接 Popen 的进程会随会话被回收，所以统一由 wscript.exe 投递，
  再在这里用 DETACHED_PROCESS 让服务进程脱离父进程树常驻。

用法：
    .venv\\Scripts\\pythonw.exe launch_server.py
"""

import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(BASE, "logs")
LOG_FILE = os.path.join(LOGS, "server.out")

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

# 2026-11-09：本机启动会话可能残留 HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:1097，
# 该代理早已不存在，会让子进程抓图/调大模型全部 ProxyError（连不上代理）。
# 服务本身直连外网即可，所以起服务前统一清空代理环境变量，避免被父会话污染。
PROXY_ENV_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    "PROXY_URL", "proxy_url",
)


def _strip_proxy_env() -> list[str]:
    cleared = []
    for key in PROXY_ENV_KEYS:
        if os.environ.pop(key, None) is not None:
            cleared.append(key)
    return cleared


def main() -> int:
    os.makedirs(LOGS, exist_ok=True)
    os.chdir(BASE)
    cleared = _strip_proxy_env()

    exe = os.path.join(BASE, ".venv", "Scripts", "pythonw.exe")
    if not os.path.exists(exe):
        exe = os.path.join(BASE, ".venv", "Scripts", "python.exe")
    if not os.path.exists(exe):
        exe = sys.executable

    with open(LOG_FILE, "ab") as out:
        out.write(b"\n===== launch_server: start =====\n")
        if cleared:
            out.write(f"cleared proxy env: {', '.join(cleared)}\n".encode())
        out.flush()
        proc = subprocess.Popen(
            [exe, "-m", "src.app"],
            cwd=BASE,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=out,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
        out.write(f"server pid = {proc.pid}\n".encode())
        out.flush()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback

        try:
            os.makedirs(LOGS, exist_ok=True)
            with open(os.path.join(LOGS, "launch_error.log"), "a", encoding="utf-8") as fh:
                fh.write(f"\n===== {sys.version} =====\n")
                fh.write(traceback.format_exc())
        except Exception:
            pass
        sys.exit(1)
