"""
闲鱼账号管理路由
"""
import json
import os
import re
import subprocess
import sys
from typing import List

import aiofiles
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.infrastructure.config.env_manager import env_manager
from src.services.workbench_service import list_account_health


router = APIRouter(prefix="/api/accounts", tags=["accounts"])

ACCOUNT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,50}$")


class AccountCreate(BaseModel):
    name: str
    content: str


class AccountUpdate(BaseModel):
    content: str


class LoginLaunchRequest(BaseModel):
    account: str | None = None


def _strip_quotes(value: str) -> str:
    if not value:
        return value
    if value.startswith(("\"", "'")) and value.endswith(("\"", "'")):
        return value[1:-1]
    return value


def _state_dir() -> str:
    raw = env_manager.get_value("ACCOUNT_STATE_DIR", "state") or "state"
    return _strip_quotes(raw.strip())


def _ensure_state_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _validate_name(name: str) -> str:
    trimmed = name.strip()
    if not trimmed or not ACCOUNT_NAME_RE.match(trimmed):
        raise HTTPException(status_code=400, detail="账号名称只能包含字母、数字、下划线或短横线。")
    return trimmed


def _account_path(name: str) -> str:
    filename = f"{name}.json"
    return os.path.join(_state_dir(), filename)


def _validate_json(content: str) -> None:
    try:
        json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="提供的内容不是有效的JSON格式。")


@router.get("", response_model=List[dict])
async def list_accounts():
    state_dir = _state_dir()
    if not os.path.isdir(state_dir):
        return []
    files = [f for f in os.listdir(state_dir) if f.endswith(".json")]
    accounts = []
    for filename in sorted(files):
        name = filename[:-5]
        accounts.append({
            "name": name,
            "path": os.path.join(state_dir, filename),
        })
    return accounts


@router.post("/login/launch")
async def launch_login(payload: LoginLaunchRequest):
    """启动闲鱼扫码登录窗口；不传账号时优先选择最近失效的账号。"""
    target = (payload.account or "").strip()
    if not target:
        health = list_account_health()
        target = next(
            (item["name"] for item in health if item["status"] == "needs_update"),
            "",
        )
    if not target:
        raise HTTPException(status_code=400, detail="当前没有需要重新登录的账号，请指定账号名。")
    account_name = _validate_name(target)

    script_path = os.path.join(os.getcwd(), "login_xianyu.py")
    if not os.path.exists(script_path):
        raise HTTPException(status_code=500, detail="找不到 login_xianyu.py 登录脚本。")

    os.makedirs("logs", exist_ok=True)
    log_path = os.path.join("logs", f"login_{account_name}.log")
    creationflags = 0
    if sys.platform == "win32":
        creationflags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    try:
        with open(log_path, "ab") as log_handle:
            subprocess.Popen(
                [sys.executable, "login_xianyu.py", account_name],
                cwd=os.getcwd(),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
                close_fds=True,
            )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"启动扫码登录失败: {exc}") from exc

    return {
        "message": f"已打开 {account_name} 的扫码登录窗口，请用对应手机扫码。",
        "account": account_name,
        "log_path": log_path,
    }


@router.get("/{name}", response_model=dict)
async def get_account(name: str):
    account_name = _validate_name(name)
    path = _account_path(account_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="账号不存在")
    async with aiofiles.open(path, "r", encoding="utf-8") as f:
        content = await f.read()
    return {"name": account_name, "path": path, "content": content}


@router.post("", response_model=dict)
async def create_account(data: AccountCreate):
    account_name = _validate_name(data.name)
    _validate_json(data.content)
    state_dir = _state_dir()
    _ensure_state_dir(state_dir)
    path = _account_path(account_name)
    if os.path.exists(path):
        raise HTTPException(status_code=409, detail="账号已存在")
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(data.content)
    return {"message": "账号已添加", "name": account_name, "path": path}


@router.put("/{name}", response_model=dict)
async def update_account(name: str, data: AccountUpdate):
    account_name = _validate_name(name)
    _validate_json(data.content)
    state_dir = _state_dir()
    _ensure_state_dir(state_dir)
    path = _account_path(account_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="账号不存在")
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(data.content)
    return {"message": "账号已更新", "name": account_name, "path": path}


@router.delete("/{name}", response_model=dict)
async def delete_account(name: str):
    account_name = _validate_name(name)
    path = _account_path(account_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="账号不存在")
    os.remove(path)
    return {"message": "账号已删除"}
