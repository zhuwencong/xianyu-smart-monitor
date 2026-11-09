"""清理父进程遗留的代理环境变量。

Windows 上从桌面会话 / 沙箱 / 已退出的启动器里拉起服务时，子进程会继承
一条早已失效的 ``HTTP_PROXY`` / ``HTTPS_PROXY``（例如 http://127.0.0.1:1097，
CLash/V2Ray 之类退出后端口不再监听）。后果非常有迷惑性：

- httpx（openai SDK）和 requests 都读这些变量 → AI 调用直接
  ``APIConnectionError: Connection error.``，图片下载报 ``ProxyError``；
- Playwright/Chromium **不读** 这些变量（走系统代理设置）→ 抓取照样正常。

于是表现为「商品抓到了一大堆，AI 分析全部失败」，日志里只有一句
``Connection error.``，很难看出是代理的问题。

本项目需要代理时用 ``.env`` 里的 ``PROXY_URL``（``AIClient`` 会自己设置环境
变量）。所以启动时把继承来的代理变量清掉是安全的：**显式配置优先于继承**。
"""
from __future__ import annotations

import os
from pathlib import Path

PROXY_ENV_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
)

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _explicit_proxy_configured() -> bool:
    """``.env`` 里显式配了 ``PROXY_URL`` 时，不要清掉继承来的代理变量。"""
    try:
        for raw in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == "PROXY_URL" and value.strip().strip("\"'"):
                return True
    except OSError:
        pass
    return bool(str(os.environ.get("PROXY_URL") or "").strip())


def strip_inherited_proxy_env(*, label: str = "启动") -> list[str]:
    """清空继承来的代理环境变量，返回被清掉的键名（幂等）。"""
    if _explicit_proxy_configured():
        return []

    cleared = [key for key in PROXY_ENV_KEYS if os.environ.pop(key, None) is not None]
    if cleared:
        print(f"[{label}] 已清理父进程继承的代理环境变量: {', '.join(cleared)}")
    return cleared
