from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.web_auth import COOKIE_NAME, install_web_auth, validate_web_binding
from src.api.routes import websocket


@pytest.fixture
def auth_context():
    settings = SimpleNamespace(
        server_host="127.0.0.1", web_username="owner", web_password="test-password",
        web_session_seconds=43200, web_strict_auth=True,
    )
    app = FastAPI()
    auth = install_web_auth(app, lambda: settings)
    app.include_router(websocket.router)

    @app.api_route("/api/private", methods=["GET", "POST", "DELETE"])
    def private():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "healthy"}

    with TestClient(app, base_url="http://localhost") as client:
        yield client, auth, settings


def _auto_app():
    settings = SimpleNamespace(
        server_host="127.0.0.1", web_username="owner", web_password="test-password",
        web_session_seconds=43200, web_strict_auth=False,
    )
    app = FastAPI()
    auth = install_web_auth(app, lambda: settings)

    @app.api_route("/api/private", methods=["GET", "POST", "DELETE"])
    def private():
        return {"ok": True}

    return app, auth, settings


@pytest.fixture
def auto_context():
    app, auth, settings = _auto_app()
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        yield client, auth, settings


def login(client):
    return client.post("/auth/status", json={"username": "owner", "password": "test-password"})


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/private"), ("POST", "/api/private"), ("DELETE", "/api/private"),
    ("GET", "/docs"), ("GET", "/openapi.json"), ("GET", "/api/accounts/acc_1"),
])
def test_anonymous_requests_are_rejected(auth_context, method, path):
    client, _, _ = auth_context
    assert client.request(method, path).status_code == 401
    assert client.get("/health").status_code == 200


def test_login_sets_cookie_and_logout_revokes_replayed_token(auth_context):
    client, _, _ = auth_context
    response = login(client)
    assert response.status_code == 200
    cookie_header = response.headers["set-cookie"].lower()
    assert "httponly" in cookie_header and "samesite=strict" in cookie_header
    token = client.cookies[COOKIE_NAME]
    assert client.get("/api/private").status_code == 200
    assert client.get("/auth/session").json()["username"] == "owner"
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/api/private", headers={"cookie": f"{COOKIE_NAME}={token}"}).status_code == 401


def test_expired_session_and_password_change_invalidate_access(auth_context):
    client, auth, settings = auth_context
    login(client)
    auth.sessions[client.cookies[COOKIE_NAME]].expires_at = 0
    assert client.get("/api/private").status_code == 401
    assert login(client).status_code == 200
    settings.web_password = "changed-password"
    assert client.get("/api/private").status_code == 401


def test_login_prunes_expired_sessions_without_mutating_iteration(auth_context):
    client, auth, _ = auth_context
    login(client)
    auth.sessions[client.cookies[COOKIE_NAME]].expires_at = 0
    assert login(client).status_code == 200
    assert len(auth.sessions) == 1


def test_cross_site_and_rebound_host_are_rejected(auth_context):
    client, _, _ = auth_context
    assert login(client).status_code == 200
    assert client.post("/api/private", headers={"origin": "https://evil.example"}).status_code == 403
    assert client.post("/auth/status", json={"username": "owner", "password": "test-password"},
                       headers={"origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/private", headers={"host": "evil.example"}).status_code == 400
    assert client.post("/api/private", headers={"origin": "http://localhost"}).status_code == 200


def test_failed_login_is_rate_limited(auth_context):
    client, _, _ = auth_context
    for _ in range(5):
        assert client.post("/auth/status", json={"username": "owner", "password": "wrong"}).status_code == 401
    assert login(client).status_code == 429


def test_websocket_requires_session_and_rejects_revoked_cookie(auth_context):
    client, _, _ = auth_context
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("ws://localhost/ws"):
            pass
    login(client)
    token = client.cookies[COOKIE_NAME]
    with client.websocket_connect("ws://localhost/ws") as ws:
        ws.send_text("ping")
        client.portal.call(websocket.broadcast_message, "test", {"ok": True})
        assert ws.receive_json() == {"type": "test", "data": {"ok": True}}
        client.post("/auth/logout")
        client.portal.call(websocket.broadcast_message, "private", {"secret": "must not arrive"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("ws://localhost/ws", headers={"cookie": f"{COOKIE_NAME}={token}"}):
            pass


def test_public_binding_rejects_default_password():
    settings = SimpleNamespace(server_host="0.0.0.0", web_password="admin123")
    with pytest.raises(ValueError, match="WEB_PASSWORD"):
        validate_web_binding(settings)
    settings.web_password = "strong-test-password"
    validate_web_binding(settings)


def test_real_app_protects_account_route_without_starting_lifespan():
    import src.app as app_module
    client = TestClient(app_module.app, base_url="http://localhost")
    assert client.get("/api/accounts/acc_1").status_code == 401
    assert client.get("/api/tasks").status_code == 401


def test_local_loopback_is_auto_authenticated(auto_context):
    client, auth, _ = auto_context
    assert client.get("/api/private").status_code == 200
    assert client.post("/api/private").status_code == 200
    session = client.get("/auth/session").json()
    assert session == {"authenticated": True, "username": "local", "auto": True}
    # 免登录不产生真实会话，也不下发 cookie
    assert auth.sessions == {}
    assert COOKIE_NAME not in client.cookies


def test_strict_mode_restores_login_for_local_access(auto_context):
    client, auth, settings = auto_context
    settings.web_strict_auth = True
    assert client.get("/api/private").status_code == 401
    assert client.get("/auth/session").status_code == 401
    assert client.post("/auth/status", json={"username": "owner", "password": "test-password"}).status_code == 200
    assert client.get("/api/private").status_code == 200
    assert client.get("/auth/session").json() == {"authenticated": True, "username": "owner"}


def test_auto_mode_still_blocks_cross_site_requests(auto_context):
    client, _, _ = auto_context
    assert client.get("/api/private", headers={"origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/private", headers={"host": "evil.example"}).status_code == 400


def test_remote_client_gets_no_auto_session():
    app, _, _ = _auto_app()
    with TestClient(app, base_url="http://127.0.0.1", client=("203.0.113.9", 50000)) as client:
        assert client.get("/api/private").status_code == 401
        assert client.get("/auth/session").status_code == 401


def test_auto_mode_requires_loopback_server_binding():
    app, _, settings = _auto_app()
    settings.server_host = "0.0.0.0"
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        assert client.get("/api/private").status_code == 401
