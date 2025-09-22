from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from passlib.hash import bcrypt

import app.core.runtime as runtime
from ....core.security import generate_token, get_session_ttl_seconds, require_token
from ....schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    UserPublic,
)


router = APIRouter()


def _now_iso() -> str:
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()


async def _get_user_by_username(username: str) -> Optional[dict[str, Any]]:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")
    uid = await runtime.redis_client.get(f"user:byname:{username}")
    if not uid:
        return None
    data = await runtime.redis_client.hgetall(f"user:{uid}")
    return data or None


@router.post("/register", response_model=UserPublic)
async def register(payload: RegisterRequest) -> UserPublic:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")

    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username required")

    # Generate new id first; if username exists we won't reuse the id (acceptable for now)
    user_id = await runtime.redis_client.incr("users:seq")
    created_at = _now_iso()
    password_hash = bcrypt.hash(payload.password)

    ok = await runtime.redis_client.set(f"user:byname:{username}", user_id, nx=True)
    if not ok:
        raise HTTPException(status_code=409, detail="Username already exists")

    await runtime.redis_client.hset(
        f"user:{user_id}",
        mapping={
            "id": str(user_id),
            "username": username,
            "password_hash": password_hash,
            "created_at": created_at,
        },
    )

    return UserPublic(id=str(user_id), username=username)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")
    username = payload.username.strip()
    user = await _get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not bcrypt.verify(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = generate_token()
    ttl = get_session_ttl_seconds()
    uid = user["id"]
    await runtime.redis_client.setex(f"session:{token}", ttl, uid)
    await runtime.redis_client.sadd(f"user:sessions:{uid}", token)
    return LoginResponse(token=token)


async def _resolve_user_from_token(token: str) -> dict[str, Any]:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")
    uid = await runtime.redis_client.get(f"session:{token}")
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user = await runtime.redis_client.hgetall(f"user:{uid}")
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


@router.get("/me", response_model=UserPublic)
async def me(token: str = Depends(require_token)) -> UserPublic:
    user = await _resolve_user_from_token(token)
    return UserPublic(id=str(user["id"]), username=user["username"])


@router.post("/logout")
async def logout(token: str = Depends(require_token)) -> dict[str, Any]:
    if runtime.redis_client is None:
        raise HTTPException(status_code=500, detail="Redis not initialized")
    uid = await runtime.redis_client.get(f"session:{token}")
    if uid:
        await runtime.redis_client.delete(f"session:{token}")
        await runtime.redis_client.srem(f"user:sessions:{uid}", token)
    return {"ok": True}



