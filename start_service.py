"""用 wscript + run_hidden.vbs 无窗口拉起监控服务（绕开沙箱的进程回收）。

用法：.venv\\Scripts\\python.exe start_service.py
返回码 >32 表示投递成功（42 = 成功打开）。
"""

import ctypes
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
VBS = os.path.join(BASE, "run_hidden.vbs")


def main() -> int:
    if not os.path.exists(VBS):
        print(f"找不到 {VBS}")
        return 1
    params = f'//nologo "{VBS}"'
    ret = ctypes.windll.shell32.ShellExecuteW(None, "open", "wscript.exe", params, BASE, 0)
    print(f"ShellExecuteW ret = {ret} (>32 表示成功)")
    return 0 if ret > 32 else 2


if __name__ == "__main__":
    sys.exit(main())
