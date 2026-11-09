"""代理环境变量清理的回归测试。

背景：服务从桌面会话拉起时会继承失效的 HTTP_PROXY，导致 AI 调用全部
``Connection error.``。行为约束：默认清掉继承值，但 ``.env`` 里显式配了
``PROXY_URL`` 时不能动（显式配置优先）。
"""
import src.core.proxy_env as proxy_env


def test_strips_inherited_proxy_env(monkeypatch, tmp_path):
    monkeypatch.setattr(proxy_env, "_ENV_FILE", tmp_path / "missing.env")
    monkeypatch.delenv("PROXY_URL", raising=False)
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy"):
        monkeypatch.setenv(key, "http://127.0.0.1:1097")

    cleared = proxy_env.strip_inherited_proxy_env(label="test")

    # Windows 的 os.environ 大小写不敏感，http_proxy 与 HTTP_PROXY 是同一个键，
    # 所以按小写比较，不假设保留了哪种写法。
    assert {"http_proxy", "https_proxy"} <= {key.lower() for key in cleared}
    assert "HTTP_PROXY" not in proxy_env.os.environ
    assert "HTTPS_PROXY" not in proxy_env.os.environ


def test_keeps_env_when_proxy_url_configured(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("PROXY_URL=http://127.0.0.1:7890\n", encoding="utf-8")
    monkeypatch.setattr(proxy_env, "_ENV_FILE", env_file)
    monkeypatch.delenv("PROXY_URL", raising=False)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7890")

    assert proxy_env.strip_inherited_proxy_env(label="test") == []
    assert proxy_env.os.environ["HTTP_PROXY"] == "http://127.0.0.1:7890"


def test_noop_when_nothing_set(monkeypatch, tmp_path):
    monkeypatch.setattr(proxy_env, "_ENV_FILE", tmp_path / "missing.env")
    monkeypatch.delenv("PROXY_URL", raising=False)
    for key in proxy_env.PROXY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    assert proxy_env.strip_inherited_proxy_env(label="test") == []
