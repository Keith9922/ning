from __future__ import annotations

import os
import secrets
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


bearer_scheme = HTTPBearer(auto_error=False)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def get_session_ttl_seconds() -> int:
    try:
        return int(os.getenv("SESSION_TTL_SECONDS", "604800"))  # 7 days
    except Exception:
        return 604800


async def require_token(creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> str:
    if creds is None or not creds.scheme.lower().startswith("bearer"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = creds.credentials.strip()
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return token


