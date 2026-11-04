"""任务结束原因，与已处理商品数量分开传递。"""


class ScrapeTaskError(RuntimeError):
    """采集失败；不得当作正常的零新增。"""


class BrowserClosedError(ScrapeTaskError):
    """浏览器意外关闭，本轮应停止。"""


class TaskSkippedError(RuntimeError):
    """任务因冷却而跳过，既不成功也不累计一次失败。"""
