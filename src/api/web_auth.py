"""Web 管理端会话：凭据只用于登录，后续通过 HttpOnly cookie 认证。

本机免登录（默认）：SERVER_HOST 绑定回环地址、且请求方同样是本机回环时，
中间件直接放行并视为「本机用户」，不要求输入账号密码；登录页在这种情况下
会被前端跳过。设置 WEB_STRICT_AUTH=true 可强制所有访问都走登录页。
"""
from collections import defaultdict, deque
from dataclasses import dataclass
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse


COOKIE_NAME = "goofish_session"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
# 本机免登录模式下对外显示的用户名，不对应任何真实凭据。
LOCAL_AUTO_USERNAME = "local"


@dataclass
class _Session:
    username: str
    credentials: bytes
    expires_at: float


def validate_web_binding(settings) -> None:
    if settings.server_host not in LOOPBACK_HOSTS and settings.web_password in {"", "admin123"}:
        raise ValueError("开放非本机访问前，请先设置非默认的 WEB_PASSWORD。")


class WebAuth:
    def __init__(self, settings_provider, *, clock=time.monotonic):
        self.settings_provider = settings_provider
        self.clock = clock
        self.sessions: dict[str, _Session] = {}
        self.failures: dict[str, deque] = defaultdict(deque)

    def _credentials(self) -> bytes:
        settings = self.settings_provider()
        return hashlib.sha256(
            (settings.web_username + "\0" + settings.web_password).encode("utf-8")
        ).digest()

    def get_session(self, token: str | None) -> _Session | None:
        session = self.sessions.get(token or "")
        if session and (
            session.expires_at <= self.clock()
            or not hmac.compare_digest(session.credentials, self._credentials())
        ):
            self.sessions.pop(token, None)
            return None
        return session

    def token(self, connection: HTTPConnection) -> str | None:
        return connection.cookies.get(COOKIE_NAME)

    def local_auto(self, connection: HTTPConnection) -> bool:
        """本机回环 + 非严格模式时免登录。

        同时校验 Host 与客户端地址：即使服务绑在回环地址上，来自局域网的
        请求或 DNS 重绑定过来的请求都不会被当成本机用户。
        """
        settings = self.settings_provider()
        if getattr(settings, "web_strict_auth", False):
            return False
        if settings.server_host not in LOOPBACK_HOSTS:
            return False
        if connection.url.hostname not in LOOPBACK_HOSTS:
            return False
        client = connection.client
        return getattr(client, "host", None) in LOOPBACK_HOSTS

    def login(self, username: str, password: str, client: str) -> str:
        now = self.clock()
        for key in list(self.failures):
            while self.failures[key] and self.failures[key][0] <= now - 60:
                self.failures[key].popleft()
            if not self.failures[key]:
                self.failures.pop(key, None)
        failures = self.failures[client]
        if len(failures) >= 5:
            raise HTTPException(429, "登录尝试过多，请一分钟后重试。", headers={"Retry-After": "60"})
        settings = self.settings_provider()
        user_ok = hmac.compare_digest(username.encode(), settings.web_username.encode())
        password_ok = hmac.compare_digest(password.encode(), settings.web_password.encode())
        if not (user_ok and password_ok):
            failures.append(now)
            raise HTTPException(401, "认证失败")
        self.failures.pop(client, None)
        self.sessions = {
            token: session for token, session in tuple(self.sessions.items())
            if self.get_session(token) is not None
        }
        token = secrets.token_urlsafe(32)
        self.sessions[token] = _Session(username, self._credentials(), now + settings.web_session_seconds)
        return token


class WebAuthMiddleware:
    def __init__(self, app, auth: WebAuth):
        self.app = app
        self.auth = auth

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        protected = (
            path == "/api" or path.startswith("/api/")
            or path == "/ws" or path.startswith("/ws/")
            or path in {"/docs", "/redoc", "/openapi.json"}
            or path.startswith("/docs/")
        )
        if not protected and not path.startswith("/auth/"):
            return await self.app(scope, receive, send)
        connection = HTTPConnection(scope)
        settings = self.auth.settings_provider()
        # 本机模式同时校验 Host，避免恶意域名通过 DNS 重绑定访问本机接口。
        if settings.server_host in LOOPBACK_HOSTS and connection.url.hostname not in LOOPBACK_HOSTS:
            return await self._reject(scope, receive, send, 400, "不允许的访问地址")
        origin = connection.headers.get("origin")
        if origin:
            try:
                parsed = urlsplit(origin)
            except ValueError:
                return await self._reject(scope, receive, send, 403, "无效的访问来源")
            scheme = {"ws": "http", "wss": "https"}.get(connection.url.scheme, connection.url.scheme)
            if parsed.scheme != scheme or parsed.netloc.lower() != connection.url.netloc.lower():
                return await self._reject(scope, receive, send, 403, "不允许跨站访问")
        elif connection.headers.get("sec-fetch-site") == "cross-site":
            return await self._reject(scope, receive, send, 403, "不允许跨站访问")
        token = self.auth.token(connection)
        session = self.auth.get_session(token)
        auto_local = session is None and self.auth.local_auto(connection)
        if protected and session is None and not auto_local:
            return await self._reject(scope, receive, send, 401, "请先登录")
        scope["web_session_valid"] = lambda: (
            self.auth.get_session(token) is not None or self.auth.local_auto(connection)
        )
        return await self.app(scope, receive, send)

    async def _reject(self, scope, receive, send, status, message):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008, "reason": message})
        else:
            await JSONResponse({"detail": message}, status_code=status)(scope, receive, send)


class LoginRequest(BaseModel):
    username: str
    password: str


def install_web_auth(app, settings_provider) -> WebAuth:
    auth = WebAuth(settings_provider)
    app.add_middleware(WebAuthMiddleware, auth=auth)

    @app.post("/auth/status")
    async def login(payload: LoginRequest, request: Request, response: Response):
        token = auth.login(payload.username, payload.password, request.client.host if request.client else "unknown")
        old_token = auth.token(request)
        auth.sessions.pop(old_token, None)
        response.set_cookie(
            COOKIE_NAME, token, httponly=True, samesite="strict", path="/",
            secure=request.url.scheme == "https", max_age=settings_provider().web_session_seconds,
        )
        response.headers["Cache-Control"] = "no-store"
        return {"authenticated": True, "username": payload.username}

    @app.get("/auth/session")
    async def session_status(request: Request, response: Response):
        session = auth.get_session(auth.token(request))
        if session is None:
            if auth.local_auto(request):
                # 本机免登录：前端据此跳过登录页，但仍可手动访问 /login 查看。
                response.headers["Cache-Control"] = "no-store"
                return {"authenticated": True, "username": LOCAL_AUTO_USERNAME, "auto": True}
            raise HTTPException(401, "请先登录")
        response.headers["Cache-Control"] = "no-store"
        return {"authenticated": True, "username": session.username}

    @app.post("/auth/logout")
    async def logout(request: Request, response: Response):
        auth.sessions.pop(auth.token(request), None)
        response.delete_cookie(COOKIE_NAME, path="/", samesite="strict")
        response.headers["Cache-Control"] = "no-store"
        return {"authenticated": False}

    return auth
